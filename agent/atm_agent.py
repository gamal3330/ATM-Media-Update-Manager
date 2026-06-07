from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from api_client import ApiClient
from agent_self_update import AgentSelfUpdateManager
from cash_monitoring_module import CashMonitoringModule
from config_manager import LocalConfig, RemoteConfig, load_local_config, write_local_config
from logger import setup_logger
from media_update_module import MediaUpdateModule
from module_runner import ModuleRunner
from network_probe import tcp_connect_probe
from xfs_cdm_diagnostics import diagnose_xfs_cdm, format_diagnostics
from xfs_cdm_reader import read_cash_units, format_read_result

AGENT_VERSION = "2.0.8"
DEFAULT_INSTALL_DIR = Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "QIB ATM Manager Agent"
DEFAULT_CONFIG = DEFAULT_INSTALL_DIR / "config.json"
SERVICE_NAME = "ATMUnifiedAgent"
LEGACY_SERVICE_NAMES = ["ATMMediaAgent"]
SERVICE_DISPLAY_NAME = "QIB ATM Manager Agent Service"
SCHEDULED_TASK_NAME = "QIB ATM Manager Agent"
HIDDEN_TASK_RUNNER = "run-agent-hidden.vbs"

ARGS_THAT_MAY_START_WITH_DASH = {"--api-key"}
KNOWN_OPTION_ARGS = {
    "--server-url",
    "--atm-id",
    "--api-key",
    "--install-dir",
    "--config",
    "--local-log-path",
    "--fallback-check-interval-seconds",
    "--fallback-heartbeat-interval-seconds",
    "--fallback-config-sync-interval-seconds",
    "--run-mode",
    "--task-user",
    "--aptra-root",
    "--xfs-root",
    "--msxfs-path",
    "--logical-service",
    "--version-range",
    "--timeout-ms",
    "--json",
    "--once",
}


def normalize_dash_prefixed_cli_values(argv: list[str]) -> list[str]:
    normalized: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        next_token = argv[index + 1] if index + 1 < len(argv) else None
        if (
            token in ARGS_THAT_MAY_START_WITH_DASH
            and next_token
            and next_token.startswith("-")
            and next_token not in KNOWN_OPTION_ARGS
        ):
            normalized.append(f"{token}={next_token}")
            index += 2
            continue
        normalized.append(token)
        index += 1
    return normalized


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def state_path(config: LocalConfig) -> Path:
    return Path(config.local_log_path) / "state.json"


def read_state(config: LocalConfig) -> dict:
    path = state_path(config)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def write_state(config: LocalConfig, **updates) -> None:
    path = state_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    state = read_state(config)
    state.update(updates)
    state["updated_at"] = utc_now_iso()
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def validate_server_credentials(config: LocalConfig) -> dict:
    session = requests.Session()
    session.headers.update({"X-ATM-ID": config.atm_id, "X-API-Key": config.api_key})
    try:
        response = session.get(f"{config.server_url}/api/agent/config", timeout=20)
    except requests.RequestException as exc:
        raise SystemExit(f"Could not reach server during install: {exc}") from exc

    if response.status_code != 200:
        try:
            details = response.json()
        except json.JSONDecodeError:
            details = response.text
        raise SystemExit(
            f"Server rejected ATM credentials during install. "
            f"HTTP {response.status_code}: {details}"
        )

    return response.json()


def run_sc(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["sc.exe", *args], capture_output=True, text=True, check=False)


def same_path(left: Path, right: Path) -> bool:
    left_text = os.path.normcase(os.path.abspath(str(left)))
    right_text = os.path.normcase(os.path.abspath(str(right)))
    return left_text == right_text


def is_service_installed(name: str = SERVICE_NAME) -> bool:
    if os.name != "nt":
        return False
    return run_sc("query", name).returncode == 0


def stop_existing_service(name: str = SERVICE_NAME, timeout_seconds: int = 45) -> None:
    if os.name != "nt" or not is_service_installed(name):
        return

    status = service_status(name)
    if "STOPPED" in status:
        return

    print(f"Stopping existing service {name}...")
    run_sc("stop", name)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        status = service_status(name)
        if "STOPPED" in status or status == "not installed":
            return
        time.sleep(1)

    raise SystemExit(
        f"Could not stop existing service {name} within {timeout_seconds} seconds. "
        f"Close any running atm-agent.exe process, or run: sc.exe stop {name}"
    )


def delete_existing_service(name: str = SERVICE_NAME, timeout_seconds: int = 45) -> None:
    if os.name != "nt" or not is_service_installed(name):
        return

    print(f"Deleting existing service {name} registration...")
    run_sc("delete", name)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not is_service_installed(name):
            return
        time.sleep(1)

    raise SystemExit(
        f"Could not delete existing {SERVICE_DISPLAY_NAME} service within {timeout_seconds} seconds. "
        "Restart Windows, then run install again."
    )


def remove_previous_agent(target_exe: Path, source_exe: Path) -> None:
    if os.name != "nt":
        return

    for service_name in [SERVICE_NAME, *LEGACY_SERVICE_NAMES]:
        stop_existing_service(service_name)
        delete_existing_service(service_name)
    remove_existing_scheduled_task()

    if same_path(source_exe, target_exe):
        print("Existing service was removed. Using current executable from install directory.")
        return

    if target_exe.exists():
        try:
            target_exe.unlink()
            print(f"Removed previous agent executable: {target_exe}")
        except PermissionError as exc:
            raise SystemExit(
                f"Could not remove previous agent executable because it is still in use: {target_exe}. "
                "Restart Windows, then run install again."
            ) from exc


def start_windows_service_or_explain(config_path: Path) -> None:
    result = run_sc("start", SERVICE_NAME)
    if result.returncode == 0:
        print(f"Installed and started {SERVICE_DISPLAY_NAME}.")
        return

    bootstrap_log = config_path.parent / "logs" / "service-bootstrap.log"
    agent_log = config_path.parent / "logs" / "agent.log"
    details = "\n".join(part.strip() for part in [result.stdout, result.stderr] if part.strip())
    raise SystemExit(
        f"Installed {SERVICE_DISPLAY_NAME}, but Windows could not start it.\n"
        f"sc.exe start returned exit code {result.returncode}.\n"
        f"{details}\n\n"
        "Run these commands on the ATM to diagnose:\n"
        f"  sc.exe query {SERVICE_NAME}\n"
        f"  Get-Content \"{bootstrap_log}\" -Tail 50\n"
        f"  Get-Content \"{agent_log}\" -Tail 50\n"
        f"  .\\atm-agent.exe run --config \"{config_path}\" --once\n"
    )


def cash_xfs_profile_from_remote_config(payload: dict) -> str:
    modules = payload.get("modules") or {}
    cash = modules.get("cash_monitoring") or {}
    return str(cash.get("xfs_profile") or "").strip().lower()


def choose_run_mode(requested_mode: str, remote_config_payload: dict) -> str:
    if requested_mode != "auto":
        return requested_mode
    return "scheduled-task" if cash_xfs_profile_from_remote_config(remote_config_payload) == "grg" else "service"


def current_windows_user() -> str:
    domain = os.environ.get("USERDOMAIN") or "."
    username = os.environ.get("USERNAME") or getpass.getuser()
    if not username:
        raise SystemExit("--task-user is required because the current Windows user could not be detected.")
    return f"{domain}\\{username}" if domain != "." else f".\\{username}"


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def write_hidden_task_runner(target_exe: Path, config_path: Path, install_dir: Path) -> Path:
    runner_path = install_dir / HIDDEN_TASK_RUNNER
    runner_path.write_text(
        'Set shell = CreateObject("WScript.Shell")\n'
        f'shell.Run """{target_exe}"" run --config ""{config_path}""", 0, False\n',
        encoding="ascii",
    )
    return runner_path


def run_powershell(script: str) -> subprocess.CompletedProcess[str]:
    executable = powershell_executable()
    return subprocess.run(
        [executable, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    )


def powershell_executable() -> str:
    if os.name != "nt":
        return "powershell.exe"

    windows_dir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    candidates = [
        windows_dir / "Sysnative" / "WindowsPowerShell" / "v1.0" / "powershell.exe",
        windows_dir / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return "powershell.exe"


def windows_tool_executable(name: str) -> str:
    if os.name != "nt":
        return name

    windows_dir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    candidates = [
        windows_dir / "Sysnative" / name,
        windows_dir / "System32" / name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return name


def run_schtasks(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [windows_tool_executable("schtasks.exe"), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def scheduled_task_status(task_name: str = SCHEDULED_TASK_NAME) -> str:
    if os.name != "nt":
        return "not available outside Windows"
    script = (
        f"$task = Get-ScheduledTask -TaskName {ps_quote(task_name)} -ErrorAction SilentlyContinue; "
        "if ($task) { $task.State } else { 'not installed' }"
    )
    result = run_powershell(script)
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip() or "unknown"


def remove_existing_scheduled_task(task_name: str = SCHEDULED_TASK_NAME) -> None:
    if os.name != "nt":
        return

    task_path = rf"\{task_name}"
    query = run_schtasks("/Query", "/TN", task_path)
    if query.returncode != 0:
        details = "\n".join(part.strip() for part in [query.stdout, query.stderr] if part.strip())
        if scheduled_task_not_found(details):
            return

    script = (
        f"$taskName = {ps_quote(task_name)}; "
        "$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue; "
        "if ($task) { "
        "  Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue; "
        "  Unregister-ScheduledTask -TaskName $taskName -Confirm:$false; "
        "}"
    )
    result = run_powershell(script)
    if result.returncode != 0:
        run_schtasks("/End", "/TN", task_path)
        delete = run_schtasks("/Delete", "/TN", task_path, "/F")
        details = "\n".join(
            part.strip()
            for part in [result.stdout, result.stderr, delete.stdout, delete.stderr]
            if part.strip()
        )
        if delete.returncode == 0 or scheduled_task_not_found(details):
            return
        raise SystemExit(f"Could not remove existing scheduled task {task_name}.\n{details}")


def scheduled_task_not_found(details: str) -> bool:
    text = (details or "").lower()
    return (
        "cannot find the file" in text
        or "cannot find the path" in text
        or "system cannot find" in text
        or "does not exist" in text
        or "no scheduled tasks" in text
    )


def install_scheduled_task(target_exe: Path, config_path: Path, install_dir: Path, task_user: str | None) -> None:
    if os.name != "nt":
        raise SystemExit("Scheduled Task installation is only available on Windows.")

    user_id = task_user or current_windows_user()
    stop_existing_service(SERVICE_NAME)
    if is_service_installed(SERVICE_NAME):
        run_sc("config", SERVICE_NAME, "start=", "disabled")
    remove_existing_scheduled_task()
    runner_path = write_hidden_task_runner(target_exe, config_path, install_dir)
    runner_argument = f'"{runner_path}"'

    script = "\n".join(
        [
            "$ErrorActionPreference = 'Stop'",
            f"$taskName = {ps_quote(SCHEDULED_TASK_NAME)}",
            "$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue",
            "if ($task) { Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue; Unregister-ScheduledTask -TaskName $taskName -Confirm:$false }",
            f"$action = New-ScheduledTaskAction -Execute 'wscript.exe' -Argument {ps_quote(runner_argument)}",
            f"$trigger = New-ScheduledTaskTrigger -AtLogOn -User {ps_quote(user_id)}",
            f"$principal = New-ScheduledTaskPrincipal -UserId {ps_quote(user_id)} -LogonType Interactive -RunLevel Highest",
            "$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)",
            "Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null",
            "Start-ScheduledTask -TaskName $taskName",
        ]
    )
    result = run_powershell(script)
    if result.returncode != 0:
        details = "\n".join(part.strip() for part in [result.stdout, result.stderr] if part.strip())
        raise SystemExit(
            f"Could not install scheduled task {SCHEDULED_TASK_NAME} for {user_id}.\n"
            f"{details}\n\n"
            "Make sure the user is currently logged on, then run install again."
        )

    print(f"Installed and started scheduled task {SCHEDULED_TASK_NAME} for {user_id}.")
    print("Windows Service is disabled so the agent does not run twice.")


def install_windows_service(target_exe: Path, config_path: Path) -> None:
    bin_path = f'"{target_exe}" service --config "{config_path}"'
    subprocess.run(
        ["sc.exe", "create", SERVICE_NAME, "binPath=", bin_path, "start=", "auto", "DisplayName=", SERVICE_DISPLAY_NAME],
        check=True,
    )
    subprocess.run(["sc.exe", "description", SERVICE_NAME, "Pull-based unified ATM agent"], check=True)
    subprocess.run(
        ["sc.exe", "failure", SERVICE_NAME, "reset=", "86400", "actions=", "restart/60000/restart/60000/restart/60000"],
        check=True,
    )
    start_windows_service_or_explain(config_path)


class AtmAgent:
    def __init__(
        self,
        config_path: Path,
        stop_event: threading.Event | None = None,
        startup_mode: str = "scheduled-task",
    ) -> None:
        self.config_path = config_path
        self.local_config = load_local_config(config_path)
        self.logger = setup_logger(self.local_config.local_log_path)
        self.api = ApiClient(self.local_config)
        self.self_update_manager = AgentSelfUpdateManager(
            self.api,
            current_version=AGENT_VERSION,
            config_path=config_path,
            startup_mode=startup_mode,
            service_name=SERVICE_NAME,
            task_name=SCHEDULED_TASK_NAME,
            logger=self.logger,
        )
        self.media_module = MediaUpdateModule(self.api, self.local_config, self.logger)
        self.cash_module = CashMonitoringModule(self.api, self.local_config.atm_id, self.logger)
        self.modules = ModuleRunner(self.logger)
        self.modules.register(self.media_module)
        self.modules.register(self.cash_module)
        self.stop_event = stop_event or threading.Event()
        self.remote_config: RemoteConfig | None = None
        self.applied_config_version = 0
        self.last_periodic_switch_probe = 0.0
        self.last_agent_update_check = 0.0

    def write_runtime_state(self) -> None:
        write_state(
            self.local_config,
            module_statuses=self.modules.module_statuses(),
            current_package_version=self.media_module.current_package_version,
            last_cash_snapshot_at=self.cash_module.last_snapshot_at,
            last_cash_unit_count=self.cash_module.last_unit_count,
            last_cash_error=self.cash_module.last_error,
        )

    def handle_switch_probe(self) -> None:
        probe = self.api.get_switch_probe()
        if not probe:
            return

        probe_id = int(probe["id"])
        host = str(probe["host"])
        port = int(probe["port"])
        self.logger.info("Running read-only switch TCP probe: %s:%s", host, port)
        result = tcp_connect_probe(host, port, timeout_seconds=5)
        if result.success:
            self.api.report_switch_probe(probe_id, "success", result.latency_ms)
            self.logger.info("Switch TCP probe succeeded: %s:%s latency=%sms", host, port, result.latency_ms)
            return

        self.api.report_switch_probe(probe_id, "failed", result.latency_ms, result.error_message)
        self.logger.warning("Switch TCP probe failed: %s:%s error=%s", host, port, result.error_message)

    def handle_periodic_switch_probe(self, now: float) -> None:
        config = self.remote_config
        if config is None:
            return
        interval = max(30, int(config.switch_probe_interval_seconds or 30))
        if now - self.last_periodic_switch_probe < interval:
            return

        self.last_periodic_switch_probe = now
        host = config.switch_probe_host
        port = int(config.switch_probe_port)
        self.logger.info("Running periodic switch TCP probe: %s:%s", host, port)
        result = tcp_connect_probe(host, port, timeout_seconds=5)
        if result.success:
            self.api.report_switch_probe_snapshot("success", result.latency_ms, None, host, port)
            self.logger.info("Periodic switch TCP probe succeeded: %s:%s latency=%sms", host, port, result.latency_ms)
            return

        self.api.report_switch_probe_snapshot("failed", result.latency_ms, result.error_message, host, port)
        self.logger.warning("Periodic switch TCP probe failed: %s:%s error=%s", host, port, result.error_message)

    def handle_agent_commands(self) -> None:
        commands = self.api.list_commands()
        for command in commands:
            command_id = int(command["id"])
            command_type = str(command.get("command_type") or "")
            if command_type != "cash_read_now":
                continue
            self.logger.info("Running read-only cash read request: command_id=%s", command_id)
            try:
                self.api.ack_command(command_id, "acknowledged", "Read-only cash read started")
                self.cash_module.read_now(time.monotonic())
                self.write_runtime_state()
                self.api.ack_command(command_id, "completed", "Cash snapshot sent")
            except Exception as exc:
                self.logger.exception("Read-only cash read request failed: %s", exc)
                try:
                    self.api.ack_command(command_id, "failed", str(exc))
                except Exception:
                    pass

    def handle_agent_self_update(self, now: float) -> bool:
        self.self_update_manager.report_pending_result()
        config = self.remote_config
        config_interval = (
            config.config_sync_interval_seconds
            if config
            else self.local_config.fallback_config_sync_interval_seconds
        )
        interval = max(60, int(config_interval or 60))
        if now - self.last_agent_update_check < interval:
            return False
        self.last_agent_update_check = now
        return self.self_update_manager.check_and_apply()

    def sync_config(self) -> None:
        config = self.api.get_config()
        try:
            self.modules.configure(config)
            self.remote_config = config
            self.applied_config_version = config.config_version
            self.api.ack_config(
                config.config_version,
                True,
                "Config applied successfully",
                self.modules.enabled_modules(),
            )
            write_state(
                self.local_config,
                last_config_sync_at=utc_now_iso(),
                config_version=config.config_version,
                applied_config_version=config.config_version,
                enabled_modules=self.modules.enabled_modules(),
                module_statuses=self.modules.module_statuses(),
                media_path=config.media_update.media_path,
                backup_path=config.media_update.backup_path,
                temp_path=config.media_update.temp_path,
                last_server_error=None,
                last_config_error=None,
            )
        except Exception as exc:
            self.api.ack_config(config.config_version, False, str(exc))
            write_state(
                self.local_config,
                last_config_sync_at=utc_now_iso(),
                config_version=config.config_version,
                last_config_error=str(exc),
            )
            raise

    def run_once(self) -> None:
        self.sync_config()
        config = self.remote_config
        if config is None:
            return
        self.api.heartbeat(
            AGENT_VERSION,
            "running",
            self.media_module.current_package_version,
            self.applied_config_version,
            enabled_modules=self.modules.enabled_modules(),
            module_statuses=self.modules.module_statuses(),
        )
        write_state(
            self.local_config,
            last_heartbeat_at=utc_now_iso(),
            agent_version=AGENT_VERSION,
            service_status="running",
            latency_ms=self.api.last_latency_ms,
            last_server_error=None,
        )
        self.handle_switch_probe()
        self.last_periodic_switch_probe = 0.0
        self.handle_periodic_switch_probe(time.monotonic())
        self.handle_agent_commands()
        self.modules.tick(time.monotonic())
        self.write_runtime_state()

    def run_forever(self) -> None:
        last_heartbeat = 0.0
        last_config = 0.0
        self.logger.info("QIB ATM Manager Agent %s started for %s", AGENT_VERSION, self.local_config.atm_id)

        while not self.stop_event.is_set():
            now = time.monotonic()
            config = self.remote_config
            heartbeat_interval = config.heartbeat_interval_seconds if config else self.local_config.fallback_heartbeat_interval_seconds
            config_interval = (
                config.config_sync_interval_seconds
                if config
                else self.local_config.fallback_config_sync_interval_seconds
            )

            try:
                if now - last_config >= config_interval:
                    self.sync_config()
                    last_config = now
                    config = self.remote_config

                if now - last_heartbeat >= heartbeat_interval:
                    self.api.heartbeat(
                        AGENT_VERSION,
                        "running",
                        self.media_module.current_package_version,
                        self.applied_config_version,
                        enabled_modules=self.modules.enabled_modules(),
                        module_statuses=self.modules.module_statuses(),
                        last_server_error=None,
                    )
                    write_state(
                        self.local_config,
                        last_heartbeat_at=utc_now_iso(),
                        agent_version=AGENT_VERSION,
                        service_status="running",
                        latency_ms=self.api.last_latency_ms,
                        enabled_modules=self.modules.enabled_modules(),
                        module_statuses=self.modules.module_statuses(),
                    )
                    last_heartbeat = now

                if self.handle_agent_self_update(now):
                    self.stop_event.set()
                    break

                if config:
                    self.handle_switch_probe()
                    self.handle_periodic_switch_probe(now)
                    self.handle_agent_commands()
                    self.modules.tick(now)
                    self.write_runtime_state()
            except requests.RequestException as exc:
                response = getattr(exc, "response", None)
                if response is not None:
                    self.logger.warning("Server communication failed: %s. Response: %s", exc, response.text[:500])
                    write_state(self.local_config, last_server_error=f"{exc}. Response: {response.text[:500]}")
                else:
                    self.logger.warning("Server communication failed: %s", exc)
                    write_state(self.local_config, last_server_error=str(exc))
            except Exception as exc:
                self.logger.exception("Agent cycle failed: %s", exc)
                write_state(self.local_config, last_update_error=str(exc))
                try:
                    self.api.log("error", "Agent cycle failed", str(exc))
                except Exception:
                    pass

            self.stop_event.wait(5)


def install(args: argparse.Namespace) -> None:
    if os.name == "nt":
        try:
            import ctypes

            is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            is_admin = False
        if not is_admin:
            raise SystemExit(
                "Administrator privileges are required to install the Windows Service. "
                "Open Command Prompt with Run as administrator, then run install again."
            )

    install_dir = Path(args.install_dir or DEFAULT_INSTALL_DIR)
    try:
        install_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError as exc:
        raise SystemExit(f"Access denied while creating install directory: {install_dir}") from exc
    config_path = Path(args.config or install_dir / "config.json")

    api_key = args.api_key or getpass.getpass("API Key: ")
    atm_id = args.atm_id or input("ATM ID: ").strip()
    if not args.server_url or not atm_id or not api_key:
        raise SystemExit("--server-url, --atm-id and --api-key are required for install")

    local_config = LocalConfig(
        server_url=args.server_url,
        atm_id=atm_id,
        api_key=api_key,
        local_log_path=args.local_log_path or str(install_dir / "logs"),
        fallback_check_interval_seconds=args.fallback_check_interval_seconds,
        fallback_heartbeat_interval_seconds=args.fallback_heartbeat_interval_seconds,
        fallback_config_sync_interval_seconds=args.fallback_config_sync_interval_seconds,
    )
    remote_config_payload = validate_server_credentials(local_config)
    detected_xfs_profile = cash_xfs_profile_from_remote_config(remote_config_payload) or "-"
    run_mode = choose_run_mode(args.run_mode, remote_config_payload)
    print(f"Detected XFS profile: {detected_xfs_profile}")
    print(f"Selected startup mode: {run_mode}")

    source_exe = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve()
    target_exe = install_dir / ("atm-agent.exe" if source_exe.suffix.lower() == ".exe" else source_exe.name)

    if os.name == "nt" and getattr(sys, "frozen", False):
        remove_previous_agent(target_exe, source_exe)

    write_local_config(config_path, local_config)

    if source_exe != target_exe:
        try:
            shutil.copy2(source_exe, target_exe)
        except PermissionError as exc:
            raise SystemExit(
        f"Could not replace {target_exe} because it is still in use. "
                f"Stop the existing service with: sc.exe stop {SERVICE_NAME}, then run install again."
            ) from exc

    if os.name != "nt":
        print(f"Config written to {config_path}. Windows Service installation is only available on Windows.")
        return

    if not getattr(sys, "frozen", False):
        raise SystemExit("Build atm-agent.exe with build_agent.bat before installing the Windows Service.")

    if run_mode == "scheduled-task":
        install_scheduled_task(target_exe, config_path, install_dir, args.task_user)
        return

    install_windows_service(target_exe, config_path)


def uninstall(_: argparse.Namespace) -> None:
    if os.name != "nt":
        print("Agent uninstall is only available on Windows.")
        return
    remove_existing_scheduled_task()
    for service_name in [SERVICE_NAME, *LEGACY_SERVICE_NAMES]:
        stop_existing_service(service_name)
        if is_service_installed(service_name):
            delete_existing_service(service_name)
    print("Uninstalled QIB ATM Manager Agent startup registrations.")


def service_status(name: str = SERVICE_NAME) -> str:
    if os.name != "nt":
        return "not available outside Windows"
    result = subprocess.run(["sc.exe", "query", name], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return "not installed"
    for line in result.stdout.splitlines():
        if "STATE" in line:
            return " ".join(line.split())
    return "unknown"


def status_command(args: argparse.Namespace) -> None:
    config_path = Path(args.config)
    try:
        config = load_local_config(config_path)
    except Exception as exc:
        raise SystemExit(f"Could not read config: {config_path}. {exc}") from exc

    print(f"Agent Version: {AGENT_VERSION}")
    print(f"Config Path: {config_path}")
    print(f"ATM ID: {config.atm_id}")
    print(f"Server URL: {config.server_url}")
    print(f"Service: {service_status()}")
    print(f"Scheduled Task: {scheduled_task_status()}")
    for legacy_name in LEGACY_SERVICE_NAMES:
        legacy_status = service_status(legacy_name)
        if legacy_status != "not installed":
            print(f"Legacy Service {legacy_name}: {legacy_status}")

    state = read_state(config)
    print(f"Last Heartbeat: {state.get('last_heartbeat_at', '-')}")
    print(f"Last Config Sync: {state.get('last_config_sync_at', '-')}")
    print(f"Config Version: {state.get('config_version', '-')}")
    print(f"Applied Config Version: {state.get('applied_config_version', '-')}")
    print(f"Current Package Version: {state.get('current_package_version', '-')}")
    print(f"Latency: {state.get('latency_ms', '-')} ms")
    if state.get("last_server_error"):
        print(f"Last Server Error: {state['last_server_error']}")
    if state.get("last_update_error"):
        print(f"Last Update Error: {state['last_update_error']}")
    print(f"Last Cash Snapshot: {state.get('last_cash_snapshot_at', '-')}")
    print(f"Last Cash Unit Count: {state.get('last_cash_unit_count', '-')}")
    if state.get("last_cash_error"):
        print(f"Last Cash Error: {state['last_cash_error']}")

    session = requests.Session()
    session.headers.update({"X-ATM-ID": config.atm_id, "X-API-Key": config.api_key})
    try:
        response = session.get(f"{config.server_url}/api/agent/config", timeout=20)
        if response.status_code == 200:
            payload = response.json()
            print("Server Connectivity: OK")
            print(f"Server Config Version: {payload.get('config_version', '-')}")
            modules = payload.get("modules") or {}
            media = modules.get("media_update") or payload
            cash = modules.get("cash_monitoring") or {}
            print(f"Media Update Enabled: {media.get('enabled', True)}")
            print(f"Media Path: {media.get('media_path', '-')}")
            print(f"Backup Path: {media.get('backup_path', '-')}")
            print(f"Temp Path: {media.get('temp_path', '-')}")
            print(f"Cash Monitoring Enabled: {cash.get('enabled', False)}")
            print(f"ATM Cash Mode: {cash.get('atm_cash_mode', 'DISPENSE_ONLY')}")
            print(f"CDM Provider: {cash.get('provider', '-')}")
            print(f"XFS Profile: {cash.get('xfs_profile', 'ncr_aptra')}")
            print(f"XFS Logical Service: {cash.get('xfs_logical_service', 'MediaDispenser1')}")
            print(f"XFS msxfs.dll Path: {cash.get('xfs_msxfs_path') or '-'}")
            print(f"XFS Version Range: {cash.get('xfs_version_range', '0x00031E03')}")
            print(f"Dispense Cassette Layout Count: {len(cash.get('cash_layout') or [])}")
        else:
            print(f"Server Connectivity: Failed HTTP {response.status_code}")
            print(f"Server Response: {response.text[:500]}")
    except requests.RequestException as exc:
        print(f"Server Connectivity: Failed {exc}")


def version_command(_: argparse.Namespace) -> None:
    print(AGENT_VERSION)


def xfs_cdm_diagnose_command(args: argparse.Namespace) -> None:
    result = diagnose_xfs_cdm(args.xfs_root or args.aptra_root)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(format_diagnostics(result))


def xfs_cdm_read_command(args: argparse.Namespace) -> None:
    result = read_cash_units(
        args.logical_service,
        msxfs_path=args.msxfs_path,
        timeout_ms=args.timeout_ms,
        version_range=int(str(args.version_range), 0),
    )
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(format_read_result(result))


def service_main(args: argparse.Namespace) -> None:
    if os.name != "nt":
        AtmAgent(Path(args.config), startup_mode="service").run_forever()
        return
    config_path = Path(args.config)
    bootstrap_log = config_path.parent / "logs" / "service-bootstrap.log"
    try:
        bootstrap_log.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        bootstrap_log.write_text(
            f"{timestamp} service command entered. exe={sys.executable} frozen={getattr(sys, 'frozen', False)}\n",
            encoding="utf-8",
        )
    except Exception:
        pass
    try:
        from service import run_service
    except Exception as exc:
        try:
            with bootstrap_log.open("a", encoding="utf-8", errors="replace") as handle:
                handle.write(f"Failed to import Windows service host: {exc}\n")
        except Exception:
            pass
        raise SystemExit("pywin32 is required for Windows Service mode. Build the agent with build_agent.bat.") from exc
    run_service(config_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="QIB ATM Manager Agent")
    sub = parser.add_subparsers(dest="command", required=True)

    install_parser = sub.add_parser("install")
    install_parser.add_argument("--server-url", required=True)
    install_parser.add_argument("--atm-id")
    install_parser.add_argument("--api-key")
    install_parser.add_argument("--install-dir", default=str(DEFAULT_INSTALL_DIR))
    install_parser.add_argument("--config")
    install_parser.add_argument("--local-log-path")
    install_parser.add_argument("--fallback-check-interval-seconds", type=int, default=300)
    install_parser.add_argument("--fallback-heartbeat-interval-seconds", type=int, default=60)
    install_parser.add_argument("--fallback-config-sync-interval-seconds", type=int, default=120)
    install_parser.add_argument("--run-mode", choices=["auto", "service", "scheduled-task"], default="auto")
    install_parser.add_argument("--task-user")
    install_parser.set_defaults(func=install)

    uninstall_parser = sub.add_parser("uninstall")
    uninstall_parser.set_defaults(func=uninstall)

    status_parser = sub.add_parser("status")
    status_parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    status_parser.set_defaults(func=status_command)

    version_parser = sub.add_parser("version")
    version_parser.set_defaults(func=version_command)

    diagnose_parser = sub.add_parser("xfs-cdm-diagnose")
    diagnose_parser.add_argument("--xfs-root")
    diagnose_parser.add_argument("--aptra-root")
    diagnose_parser.add_argument("--json", action="store_true")
    diagnose_parser.set_defaults(func=xfs_cdm_diagnose_command)

    read_parser = sub.add_parser("xfs-cdm-read")
    read_parser.add_argument("--logical-service", default="MediaDispenser1")
    read_parser.add_argument("--msxfs-path")
    read_parser.add_argument("--timeout-ms", type=int, default=20000)
    read_parser.add_argument("--version-range", default="0x00031E03")
    read_parser.add_argument("--json", action="store_true")
    read_parser.set_defaults(func=xfs_cdm_read_command)

    run_parser = sub.add_parser("run")
    run_parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    run_parser.add_argument("--once", action="store_true")
    run_parser.set_defaults(
        func=lambda args: AtmAgent(Path(args.config), startup_mode="none").run_once()
        if args.once
        else AtmAgent(Path(args.config), startup_mode="scheduled-task").run_forever()
    )

    service_parser = sub.add_parser("service")
    service_parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    service_parser.set_defaults(func=service_main)

    args = parser.parse_args(normalize_dash_prefixed_cli_values(sys.argv[1:]))
    args.func(args)


if __name__ == "__main__":
    main()
