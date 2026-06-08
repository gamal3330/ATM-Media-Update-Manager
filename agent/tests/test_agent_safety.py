import hashlib
import json
import socket
import sys
import threading
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import agent_self_update
import agent_updater
import atm_agent
from backup_manager import create_backup, restore_backup
from atm_agent import choose_run_mode, powershell_executable, scheduled_task_not_found, write_hidden_task_runner
from checksum import sha256_file
from cash_monitoring_module import CashMonitoringModule
from cash_monitoring_module import DispenseCashUnit
from config_manager import load_local_config, parse_remote_config
from module_runner import ModuleRunner
from network_probe import tcp_connect_probe
from path_policy import validate_managed_path
from safe_zip import extract_safe_zip
from xfs_cdm_diagnostics import diagnose_xfs_cdm, format_diagnostics


def make_zip(path, members):
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)


def test_sha256_file(tmp_path):
    target = tmp_path / "image.png"
    target.write_bytes(b"sample-image")

    assert sha256_file(target) == hashlib.sha256(b"sample-image").hexdigest()


def test_rejects_script_file_in_zip(tmp_path):
    package = tmp_path / "bad.zip"
    make_zip(package, {"bad.ps1": "Write-Host bad"})

    with pytest.raises(ValueError, match="Executable or script file"):
        extract_safe_zip(package, tmp_path / "staging", {"jpg", "jpeg", "png", "bmp", "gif"})


def test_rejects_path_traversal_in_zip(tmp_path):
    package = tmp_path / "bad.zip"
    make_zip(package, {"../escape.png": b"bad"})

    with pytest.raises(ValueError, match="Unsafe path"):
        extract_safe_zip(package, tmp_path / "staging", {"jpg", "jpeg", "png", "bmp", "gif"})


def test_backup_and_rollback_restore_existing_media(tmp_path):
    media = tmp_path / "media"
    backup_root = tmp_path / "backups"
    media.mkdir()
    (media / "screen.png").write_text("old", encoding="utf-8")

    backup = create_backup(media, backup_root, "ATM001")
    (media / "screen.png").write_text("new", encoding="utf-8")

    restore_backup(media, backup)

    assert (media / "screen.png").read_text(encoding="utf-8") == "old"


def test_local_config_contains_connection_data_only(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "server_url": "https://server.local",
                "atm_id": "ATM001",
                "api_key": "secret",
            }
        ),
        encoding="utf-8",
    )

    config = load_local_config(config_path)

    assert config.server_url == "https://server.local"
    assert not hasattr(config, "media_path")


def test_install_auto_run_mode_uses_scheduled_task_for_grg():
    payload = {"modules": {"cash_monitoring": {"xfs_profile": "GRG"}}}

    assert choose_run_mode("auto", payload) == "scheduled-task"
    assert choose_run_mode("service", payload) == "service"


def test_install_auto_run_mode_keeps_service_for_non_grg():
    payload = {"modules": {"cash_monitoring": {"xfs_profile": "ncr_aptra"}}}

    assert choose_run_mode("auto", payload) == "service"


def test_hidden_task_runner_quotes_program_files_paths(tmp_path):
    exe = tmp_path / "Program Files (x86)" / "ATM Agent" / "atm-agent.exe"
    config = tmp_path / "Program Files (x86)" / "ATM Agent" / "config.json"
    install_dir = tmp_path / "install"
    install_dir.mkdir()

    runner = write_hidden_task_runner(exe, config, install_dir)
    content = runner.read_text(encoding="ascii")

    assert 'shell.Run """' in content
    assert '"" run --config ""' in content
    assert '""", 0, False' in content


def test_agent_updater_replaces_current_agent_and_keeps_backup(tmp_path):
    current = tmp_path / "atm-agent.exe"
    new = tmp_path / "atm-agent-new.exe"
    backup_dir = tmp_path / "backups"
    current.write_bytes(b"old-agent")
    new.write_bytes(b"new-agent")

    result = agent_updater.perform_update(
        agent_updater.UpdateOptions(
            current_path=current,
            new_path=new,
            mode="none",
            backup_dir=backup_dir,
            timeout_seconds=5,
        )
    )

    assert result["ok"] is True
    assert current.read_bytes() == b"new-agent"
    assert not new.exists()
    backups = list(backup_dir.glob("*.bak"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == b"old-agent"


def test_agent_updater_rejects_sha256_mismatch_without_replacing(tmp_path):
    current = tmp_path / "atm-agent.exe"
    new = tmp_path / "atm-agent-new.exe"
    current.write_bytes(b"old-agent")
    new.write_bytes(b"new-agent")

    with pytest.raises(ValueError, match="SHA256 mismatch"):
        agent_updater.perform_update(
            agent_updater.UpdateOptions(
                current_path=current,
                new_path=new,
                mode="none",
                expected_sha256="0" * 64,
                timeout_seconds=5,
            )
        )

    assert current.read_bytes() == b"old-agent"
    assert new.read_bytes() == b"new-agent"


def test_agent_updater_uses_scheduled_task_commands(tmp_path):
    current = tmp_path / "atm-agent.exe"
    new = tmp_path / "atm-agent-new.exe"
    current.write_bytes(b"old-agent")
    new.write_bytes(b"new-agent")
    commands = []

    def fake_runner(args, ignore_errors=False):
        commands.append((args, ignore_errors))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    result = agent_updater.perform_update(
        agent_updater.UpdateOptions(
            current_path=current,
            new_path=new,
            mode="scheduled-task",
            task_name="QIB ATM Manager Agent",
            process_name="atm-agent.exe",
            backup_dir=tmp_path / "backups",
            timeout_seconds=5,
        ),
        runner=fake_runner,
    )

    assert result["started"] is True
    assert [item[0] for item in commands] == [
        ["schtasks.exe", "/End", "/TN", "QIB ATM Manager Agent"],
        ["taskkill.exe", "/IM", "atm-agent.exe", "/F"],
        ["schtasks.exe", "/Run", "/TN", "QIB ATM Manager Agent"],
    ]
    assert commands[0][1] is True
    assert commands[1][1] is True
    assert commands[2][1] is False


class FakeSelfUpdateApi:
    def __init__(self, update=None, downloads=None):
        self.update = update
        self.downloads = downloads or {}
        self.progresses = []
        self.results = []

    def check_agent_update(self):
        return self.update

    def download_package(self, download_url, output):
        payload = self.downloads[download_url]
        output.write(payload)
        return len(payload), len(payload)

    def agent_update_progress(self, *args, **kwargs):
        self.progresses.append((args, kwargs))

    def report_agent_update_result(self, *args, **kwargs):
        self.results.append((args, kwargs))


def test_agent_self_update_downloads_verified_files_and_launches_updater(tmp_path):
    current = tmp_path / "atm-agent.exe"
    config_path = tmp_path / "config.json"
    current.write_bytes(b"old-agent")
    config_path.write_text("{}", encoding="utf-8")
    agent_payload = b"new-agent"
    updater_payload = b"updater"
    update = {
        "agent_package_id": 7,
        "version": "2.0.7",
        "agent_download_url": "/agent.exe",
        "updater_download_url": "/updater.exe",
        "agent_sha256": hashlib.sha256(agent_payload).hexdigest(),
        "updater_sha256": hashlib.sha256(updater_payload).hexdigest(),
        "agent_size_bytes": len(agent_payload),
        "updater_size_bytes": len(updater_payload),
    }
    api = FakeSelfUpdateApi(update, {"/agent.exe": agent_payload, "/updater.exe": updater_payload})
    launched = []

    def fake_launcher(command, cwd):
        launched.append((command, cwd))

    manager = agent_self_update.AgentSelfUpdateManager(
        api,
        current_version="2.0.6",
        config_path=config_path,
        startup_mode="scheduled-task",
        current_exe=current,
        launcher=fake_launcher,
    )

    assert manager.check_and_apply() is True

    assert len(launched) == 1
    command, cwd = launched[0]
    assert cwd == tmp_path
    assert command[0].endswith("agent-updater.exe")
    assert command[command.index("--current") + 1] == str(current)
    assert command[command.index("--mode") + 1] == "scheduled-task"
    assert command[command.index("--agent-package-id") + 1] == "7"
    assert command[command.index("--version") + 1] == "2.0.7"
    assert command[command.index("--expected-sha256") + 1] == update["agent_sha256"]
    assert (tmp_path / "agent_updates" / "package-7" / "atm-agent.exe").read_bytes() == agent_payload
    assert api.progresses[-1][0][:4] == (7, "applying", 90, "Agent updater launched")


def test_agent_self_update_reports_pending_updater_result(tmp_path):
    current = tmp_path / "atm-agent.exe"
    config_path = tmp_path / "config.json"
    current.write_bytes(b"current")
    config_path.write_text("{}", encoding="utf-8")
    result_path = tmp_path / "update-result.json"
    result_path.write_text(
        json.dumps(
            {
                "ok": True,
                "agent_package_id": 9,
                "version": "2.0.8",
                "updated_at": "2026-06-07T10:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    api = FakeSelfUpdateApi()
    manager = agent_self_update.AgentSelfUpdateManager(
        api,
        current_version="2.0.8",
        config_path=config_path,
        startup_mode="none",
        current_exe=current,
    )

    assert manager.report_pending_result() is True
    assert api.results == [
        (
            (9, "2.0.8", "success", "Agent update applied"),
            {"finished_at": "2026-06-07T10:00:00+00:00"},
        )
    ]
    assert not result_path.exists()
    assert (tmp_path / "update-result.reported.json").exists()


def test_agent_self_update_marks_same_version_applied_without_launch(tmp_path):
    current = tmp_path / "atm-agent.exe"
    config_path = tmp_path / "config.json"
    current.write_bytes(b"current")
    config_path.write_text("{}", encoding="utf-8")
    api = FakeSelfUpdateApi({"agent_package_id": 12, "version": "2.0.6"})
    launched = []
    manager = agent_self_update.AgentSelfUpdateManager(
        api,
        current_version="2.0.6",
        config_path=config_path,
        startup_mode="scheduled-task",
        current_exe=current,
        launcher=lambda command, cwd: launched.append((command, cwd)),
    )

    assert manager.check_and_apply() is False
    assert launched == []
    assert api.results[0][0][:4] == (
        12,
        "2.0.6",
        "success",
        "Agent is already running the requested version",
    )


def test_powershell_executable_prefers_sysnative_for_32_bit_agent(tmp_path, monkeypatch):
    windir = tmp_path / "Windows"
    sysnative = windir / "Sysnative" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    system32 = windir / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    sysnative.parent.mkdir(parents=True)
    system32.parent.mkdir(parents=True)
    sysnative.write_text("", encoding="ascii")
    system32.write_text("", encoding="ascii")

    monkeypatch.setattr(atm_agent.os, "name", "nt")
    monkeypatch.setenv("WINDIR", str(windir))

    assert powershell_executable() == str(sysnative)


def test_scheduled_task_not_found_accepts_schtasks_missing_file_message():
    assert scheduled_task_not_found("ERROR: The system cannot find the file specified.")


def test_remote_config_rejects_paths_outside_atm_root():
    with pytest.raises(ValueError, match="media_path must be under"):
        validate_managed_path("C:/Windows/System32", "media_path")


class FakeApi:
    def __init__(self):
        self.snapshots = []
        self.switch_snapshots = []
        self.logs = []

    def check_update(self):
        return None

    def cash_snapshot(self, payload):
        self.snapshots.append(payload)

    def report_switch_probe_snapshot(self, status, latency_ms, error_message, host, port):
        self.switch_snapshots.append(
            {
                "status": status,
                "latency_ms": latency_ms,
                "error_message": error_message,
                "host": host,
                "port": port,
            }
        )

    def log(self, level, message, details=None):
        self.logs.append({"level": level, "message": message, "details": details})


def remote_payload(media_enabled=True, cash_enabled=True):
    return {
        "atm_id": "ATM001",
        "config_version": 2,
        "heartbeat_interval_seconds": 60,
        "config_sync_interval_seconds": 120,
        "switch_probe_host": "172.16.25.75",
        "switch_probe_port": 10200,
        "switch_probe_interval_seconds": 30,
        "modules": {
            "media_update": {
                "enabled": media_enabled,
                "media_path": "C:/ATM/Media",
                "backup_path": "C:/ATM/Backups",
                "temp_path": "C:/ATM/Temp",
                "check_interval_seconds": 300,
                "allowed_extensions": ["jpg", "jpeg", "png", "bmp", "gif"],
            },
            "cash_monitoring": {
                "enabled": cash_enabled,
                "atm_cash_mode": "DISPENSE_ONLY",
                "provider": "xfs_cdm",
                "xfs_profile": "ncr_aptra",
                "xfs_logical_service": "MediaDispenser1",
                "read_interval_seconds": 30,
                "cash_layout": [
                    {
                        "cassette_no": 1,
                        "currency": "YER",
                        "denomination": 1000,
                        "max_capacity": 2000,
                        "low_threshold": 300,
                        "critical_threshold": 100,
                    },
                    {
                        "cassette_no": 2,
                        "currency": "YER",
                        "denomination": 1000,
                        "max_capacity": 2000,
                        "low_threshold": 300,
                        "critical_threshold": 100,
                    },
                    {
                        "cassette_no": 3,
                        "currency": "USD",
                        "denomination": 100,
                        "max_capacity": 2000,
                        "low_threshold": 100,
                        "critical_threshold": 30,
                    },
                    {
                        "cassette_no": 4,
                        "currency": "SAR",
                        "denomination": 100,
                        "max_capacity": 2000,
                        "low_threshold": 100,
                        "critical_threshold": 30,
                    },
                ],
                "stale_after_minutes": 10,
            },
        },
    }


def test_core_parse_remote_config_modules():
    config = parse_remote_config(remote_payload())

    assert config.media_update.enabled is True
    assert config.cash_monitoring.enabled is True
    assert config.cash_monitoring.atm_cash_mode == "DISPENSE_ONLY"
    assert config.cash_monitoring.provider == "xfs_cdm"
    assert config.cash_monitoring.xfs_profile == "ncr_aptra"
    assert config.cash_monitoring.xfs_logical_service == "MediaDispenser1"
    assert config.cash_monitoring.cash_layout[2].currency == "USD"
    assert config.switch_probe_host == "172.16.25.75"
    assert config.switch_probe_port == 10200
    assert config.switch_probe_interval_seconds == 30
    assert "gif" in config.media_update.allowed_extensions


def test_module_runner_runs_enabled_modules_only():
    logger = __import__("logging").getLogger("test")
    runner = ModuleRunner(logger)

    class StubModule:
        def __init__(self, name):
            self.name = name
            self.status = "created"
            self.ticks = 0

        def configure(self, config):
            self.status = "running"

        def tick(self, now):
            self.ticks += 1

    media = StubModule("media_update")
    cash = StubModule("cash_monitoring")
    runner.register(media)
    runner.register(cash)
    runner.configure(parse_remote_config(remote_payload(media_enabled=True, cash_enabled=False)))
    runner.tick(999999.0)

    assert media.ticks == 1
    assert cash.ticks == 0
    assert runner.module_statuses()["cash_monitoring"] == "disabled"


def test_module_failure_does_not_stop_other_modules():
    logger = __import__("logging").getLogger("test")
    runner = ModuleRunner(logger)

    class BrokenModule:
        name = "media_update"
        status = "running"

        def configure(self, config):
            pass

        def tick(self, now):
            raise RuntimeError("boom")

    class HealthyModule:
        name = "cash_monitoring"
        status = "running"

        def __init__(self):
            self.ticks = 0

        def configure(self, config):
            pass

        def tick(self, now):
            self.ticks += 1

    broken = BrokenModule()
    healthy = HealthyModule()
    runner.register(broken)
    runner.register(healthy)
    runner.configure(parse_remote_config(remote_payload()))
    runner.tick(123.0)

    assert runner.module_statuses()["media_update"] == "error"
    assert healthy.ticks == 1


def test_cash_monitoring_xfs_provider_sends_dispense_only_snapshot(monkeypatch):
    def fake_read_cash_units(logical_service, **kwargs):
        assert logical_service == "MediaDispenser1"
        assert kwargs["msxfs_path"] is None
        assert kwargs["version_range"] == int("0x00031E03", 0)
        return SimpleNamespace(
            cash_units=[
                SimpleNamespace(
                    cassette_no=1,
                    unit_type="BILL_CASSETTE",
                    cassette_name="Cash Bin 1",
                    unit_id="1",
                    denomination=5,
                    initial_count=3000,
                    current_count=1014,
                    reject_count=1,
                    max_capacity=0,
                    status="OK",
                    dispensed_count=1986,
                    presented_count=1985,
                    retracted_count=0,
                ),
                SimpleNamespace(
                    cassette_no=2,
                    unit_type="BILL_CASSETTE",
                    cassette_name="Cash Bin 2",
                    unit_id="2",
                    denomination=10,
                    initial_count=3000,
                    current_count=50,
                    reject_count=1,
                    max_capacity=0,
                    status="LOW",
                    dispensed_count=1985,
                    presented_count=1984,
                    retracted_count=0,
                ),
                SimpleNamespace(
                    cassette_no=5,
                    unit_type="REJECT_CASSETTE",
                    cassette_name="Reject Bin",
                    unit_id="0",
                    denomination=0,
                    initial_count=0,
                    current_count=2,
                    reject_count=0,
                    max_capacity=215,
                    status="OK",
                    dispensed_count=0,
                    presented_count=0,
                    retracted_count=0,
                ),
            ]
        )

    monkeypatch.setattr("cash_monitoring_module.read_cash_units", fake_read_cash_units)
    api = FakeApi()
    logger = __import__("logging").getLogger("test")
    module = CashMonitoringModule(api, "ATM001", logger)
    payload = remote_payload(cash_enabled=True)
    payload["modules"]["cash_monitoring"]["provider"] = "xfs_cdm"
    module.configure(parse_remote_config(payload))
    module.tick(999999.0)

    snapshot = api.snapshots[0]
    assert snapshot["source"] == "xfs_cdm"
    assert len(snapshot["cash_units"]) == 2
    assert snapshot["cash_units"][0]["reported_currency"] == "YER"
    assert snapshot["cash_units"][0]["reported_denomination"] == 1000
    assert snapshot["cash_units"][1]["status"] == "LOW"
    assert snapshot["reject_retract"]["reject_count"] == 2


def test_cash_monitoring_xfs_provider_uses_configured_currency_and_denomination(monkeypatch):
    def fake_read_cash_units(logical_service, **kwargs):
        return SimpleNamespace(
            cash_units=[
                SimpleNamespace(
                    cassette_no=1,
                    unit_type="BILL_CASSETTE",
                    cassette_name="Cash Bin 1",
                    unit_id="1",
                    currency="USD",
                    denomination=100,
                    initial_count=2000,
                    current_count=900,
                    reject_count=0,
                    max_capacity=2000,
                    status="OK",
                    dispensed_count=1100,
                    presented_count=1100,
                    retracted_count=0,
                )
            ]
        )

    monkeypatch.setattr("cash_monitoring_module.read_cash_units", fake_read_cash_units)
    api = FakeApi()
    logger = __import__("logging").getLogger("test")
    module = CashMonitoringModule(api, "ATM001", logger)
    payload = remote_payload(cash_enabled=True)
    payload["modules"]["cash_monitoring"]["provider"] = "xfs_cdm"
    module.configure(parse_remote_config(payload))
    module.tick(999999.0)

    snapshot = api.snapshots[0]
    assert snapshot["cash_units"][0]["reported_currency"] == "YER"
    assert snapshot["cash_units"][0]["reported_denomination"] == 1000


def test_cash_monitoring_xfs_provider_normalizes_grg_cash_units(monkeypatch):
    def fake_read_cash_units(logical_service, **kwargs):
        assert logical_service == "CDM"
        assert kwargs["msxfs_path"] == r"C:\Windows\SysWOW64\msxfs.dll"
        assert kwargs["version_range"] == int("0x00031E03", 0)
        return SimpleNamespace(
            cash_units=[
                SimpleNamespace(
                    cassette_no=1,
                    unit_type="REJECT_CASSETTE",
                    cassette_name="",
                    unit_id="S0_I0",
                    denomination=0,
                    initial_count=0,
                    current_count=1,
                    reject_count=0,
                    max_capacity=170,
                    status="OK",
                    dispensed_count=0,
                    presented_count=0,
                    retracted_count=1207553650,
                ),
                SimpleNamespace(
                    cassette_no=2,
                    unit_type="COUPON",
                    cassette_name="",
                    unit_id="S0_I1",
                    denomination=0,
                    initial_count=0,
                    current_count=0,
                    reject_count=0,
                    max_capacity=150,
                    status="OK",
                    dispensed_count=0,
                    presented_count=0,
                    retracted_count=1177363481,
                ),
                SimpleNamespace(
                    cassette_no=3,
                    unit_type="BILL_CASSETTE",
                    cassette_name="",
                    unit_id="00001",
                    denomination=1000,
                    initial_count=1500,
                    current_count=1281,
                    reject_count=0,
                    max_capacity=2000,
                    status="OK",
                    dispensed_count=0,
                    presented_count=0,
                    retracted_count=1177560082,
                ),
                SimpleNamespace(
                    cassette_no=4,
                    unit_type="BILL_CASSETTE",
                    cassette_name="",
                    unit_id="00002",
                    denomination=1000,
                    initial_count=1500,
                    current_count=1280,
                    reject_count=1,
                    max_capacity=2000,
                    status="OK",
                    dispensed_count=0,
                    presented_count=0,
                    retracted_count=1197600389,
                ),
                SimpleNamespace(
                    cassette_no=5,
                    unit_type="BILL_CASSETTE",
                    cassette_name="",
                    unit_id="00003",
                    denomination=100,
                    initial_count=100,
                    current_count=92,
                    reject_count=0,
                    max_capacity=2000,
                    status="OK",
                    dispensed_count=0,
                    presented_count=0,
                    retracted_count=1199566571,
                ),
                SimpleNamespace(
                    cassette_no=6,
                    unit_type="BILL_CASSETTE",
                    cassette_name="",
                    unit_id="00004",
                    denomination=100,
                    initial_count=100,
                    current_count=100,
                    reject_count=0,
                    max_capacity=2000,
                    status="OK",
                    dispensed_count=0,
                    presented_count=0,
                    retracted_count=1195241129,
                ),
            ]
        )

    monkeypatch.setattr("cash_monitoring_module.read_cash_units", fake_read_cash_units)
    api = FakeApi()
    logger = __import__("logging").getLogger("test")
    module = CashMonitoringModule(api, "ATM001", logger)
    payload = remote_payload(cash_enabled=True)
    payload["modules"]["cash_monitoring"]["provider"] = "xfs_cdm"
    payload["modules"]["cash_monitoring"]["xfs_profile"] = "grg"
    payload["modules"]["cash_monitoring"]["xfs_msxfs_path"] = r"C:\Windows\SysWOW64\msxfs.dll"
    del payload["modules"]["cash_monitoring"]["xfs_logical_service"]
    module.configure(parse_remote_config(payload))
    module.tick(999999.0)

    snapshot = api.snapshots[0]
    assert [unit["cassette_no"] for unit in snapshot["cash_units"]] == [1, 2, 3, 4]
    assert [unit["cassette_id"] for unit in snapshot["cash_units"]] == ["00001", "00002", "00003", "00004"]
    assert snapshot["cash_units"][0]["current_count"] == 1281
    assert snapshot["cash_units"][2]["reported_currency"] == "USD"
    assert snapshot["cash_units"][3]["reported_currency"] == "SAR"
    assert snapshot["reject_retract"]["reject_count"] == 1
    assert snapshot["reject_retract"]["retract_count"] == 0


def test_cash_monitoring_reports_cassette_remove_and_insert_events():
    api = FakeApi()
    logger = __import__("logging").getLogger("test")
    module = CashMonitoringModule(api, "ATM001", logger)
    present = DispenseCashUnit(
        cassette_no=1,
        cassette_id="CST1",
        cassette_name="Cash Bin 1",
        reported_currency="YER",
        reported_denomination=1000,
        initial_count=1000,
        current_count=900,
        reject_count=0,
        retract_count=0,
        dispensed_count=100,
        presented_count=100,
        status="OK",
        physical_status="PRESENT",
    )
    missing = DispenseCashUnit(**{**present.__dict__, "status": "MISSING", "physical_status": "MISSING"})

    module._report_cassette_status_changes([present])
    module._report_cassette_status_changes([missing])
    module._report_cassette_status_changes([present])

    assert [item["details"]["event_type"] for item in api.logs] == [
        "CASH_CASSETTE_REMOVED",
        "CASH_CASSETTE_INSERTED",
    ]


def test_xfs_cdm_diagnostics_detects_ncr_aptra_files(tmp_path):
    aptra = tmp_path / "NCR APTRA"
    cdm = aptra / "XFS CDM Service Provider"
    manager = aptra / "XFS Manager"
    cdm.mkdir(parents=True)
    manager.mkdir()
    (cdm / "NCR_CDM2SP.DLL").write_bytes(b"dll")
    (cdm / "NCR_CDMSP.DLL").write_bytes(b"dll")
    (manager / "xfs1.cab").write_bytes(b"cab")

    result = diagnose_xfs_cdm(str(aptra))
    output = format_diagnostics(result)

    assert result.read_only is True
    assert result.aptra_root == str(aptra)
    assert any(entry.path.endswith("NCR_CDM2SP.DLL") for entry in result.cdm_provider_files)
    assert any(entry.path.endswith("xfs1.cab") for entry in result.xfs_manager_files)
    assert "READ ONLY" in output


def test_tcp_connect_probe_uses_socket_without_shell():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def accept_once():
        conn, _ = server.accept()
        conn.close()
        server.close()

    thread = threading.Thread(target=accept_once)
    thread.start()
    result = tcp_connect_probe("127.0.0.1", port, timeout_seconds=2)
    thread.join(timeout=2)

    assert result.success is True
    assert result.latency_ms is not None


def test_agent_runs_periodic_switch_probe_on_configured_interval(monkeypatch):
    api = FakeApi()
    agent = SimpleNamespace(
        remote_config=parse_remote_config(remote_payload()),
        last_periodic_switch_probe=0.0,
        api=api,
        logger=__import__("logging").getLogger("test"),
    )

    def fake_probe(host, port, timeout_seconds=5):
        assert host == "172.16.25.75"
        assert port == 10200
        assert timeout_seconds == 5
        return SimpleNamespace(success=False, latency_ms=5000, error_message="timed out")

    monkeypatch.setattr(atm_agent, "tcp_connect_probe", fake_probe)

    atm_agent.AtmAgent.handle_periodic_switch_probe(agent, 10.0)
    assert api.switch_snapshots == []

    atm_agent.AtmAgent.handle_periodic_switch_probe(agent, 31.0)
    assert api.switch_snapshots == [
        {
            "status": "failed",
            "latency_ms": 5000,
            "error_message": "timed out",
            "host": "172.16.25.75",
            "port": 10200,
        }
    ]
