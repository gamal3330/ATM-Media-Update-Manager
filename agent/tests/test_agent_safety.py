import hashlib
import json
import socket
import threading
import zipfile
from types import SimpleNamespace

import pytest

from backup_manager import create_backup, restore_backup
from checksum import sha256_file
from cash_monitoring_module import CashMonitoringModule
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


def test_remote_config_rejects_paths_outside_atm_root():
    with pytest.raises(ValueError, match="media_path must be under"):
        validate_managed_path("C:/Windows/System32", "media_path")


class FakeApi:
    def __init__(self):
        self.snapshots = []

    def check_update(self):
        return None

    def cash_snapshot(self, payload):
        self.snapshots.append(payload)


def remote_payload(media_enabled=True, cash_enabled=True):
    return {
        "atm_id": "ATM001",
        "config_version": 2,
        "heartbeat_interval_seconds": 60,
        "config_sync_interval_seconds": 120,
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
                "provider": "mock",
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
    assert config.cash_monitoring.provider == "mock"
    assert config.cash_monitoring.cash_layout[2].currency == "USD"
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


def test_cash_monitoring_module_mock_provider_sends_snapshot():
    api = FakeApi()
    logger = __import__("logging").getLogger("test")
    module = CashMonitoringModule(api, "ATM001", logger)
    config = parse_remote_config(remote_payload(cash_enabled=True))
    module.configure(config)
    module.tick(999999.0)

    assert len(api.snapshots) == 1
    assert api.snapshots[0]["atm_id"] == "ATM001"
    assert api.snapshots[0]["source"] == "mock"
    assert api.snapshots[0]["atm_cash_mode"] == "DISPENSE_ONLY"
    assert api.snapshots[0]["cash_units"][0]["cassette_no"] == 1
    assert api.snapshots[0]["cash_units"][2]["reported_currency"] == "USD"
    assert api.snapshots[0]["reject_retract"]["retract_count"] == 1


def test_cash_monitoring_xfs_provider_sends_dispense_only_snapshot(monkeypatch):
    def fake_read_cash_units(logical_service):
        assert logical_service == "MediaDispenser1"
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


def test_cash_monitoring_xfs_provider_normalizes_grg_cash_units(monkeypatch):
    def fake_read_cash_units(logical_service):
        assert logical_service == "MediaDispenser1"
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
