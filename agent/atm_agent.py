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
from config_manager import LocalConfig, RemoteConfig, load_local_config, write_local_config
from logger import setup_logger
from update_manager import UpdateManager

AGENT_VERSION = "1.0.3"
DEFAULT_INSTALL_DIR = Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "ATM Media Agent"
DEFAULT_CONFIG = DEFAULT_INSTALL_DIR / "config.json"
SERVICE_NAME = "ATMMediaAgent"
SERVICE_DISPLAY_NAME = "ATM Media Update Agent"


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


def validate_server_credentials(config: LocalConfig) -> None:
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


def run_sc(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["sc.exe", *args], capture_output=True, text=True, check=False)


def same_path(left: Path, right: Path) -> bool:
    left_text = os.path.normcase(os.path.abspath(str(left)))
    right_text = os.path.normcase(os.path.abspath(str(right)))
    return left_text == right_text


def is_service_installed() -> bool:
    if os.name != "nt":
        return False
    return run_sc("query", SERVICE_NAME).returncode == 0


def stop_existing_service(timeout_seconds: int = 45) -> None:
    if os.name != "nt" or not is_service_installed():
        return

    status = service_status()
    if "STOPPED" in status:
        return

    print(f"Stopping existing {SERVICE_DISPLAY_NAME} service...")
    run_sc("stop", SERVICE_NAME)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        status = service_status()
        if "STOPPED" in status or status == "not installed":
            return
        time.sleep(1)

    raise SystemExit(
        f"Could not stop existing {SERVICE_DISPLAY_NAME} service within {timeout_seconds} seconds. "
        "Close any running atm-agent.exe process, or run: sc.exe stop ATMMediaAgent"
    )


def delete_existing_service(timeout_seconds: int = 45) -> None:
    if os.name != "nt" or not is_service_installed():
        return

    print(f"Deleting existing {SERVICE_DISPLAY_NAME} service registration...")
    run_sc("delete", SERVICE_NAME)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not is_service_installed():
            return
        time.sleep(1)

    raise SystemExit(
        f"Could not delete existing {SERVICE_DISPLAY_NAME} service within {timeout_seconds} seconds. "
        "Restart Windows, then run install again."
    )


def terminate_processes_for_path(executable_path: Path) -> None:
    if os.name != "nt" or not executable_path.exists():
        return

    script = r"""
$target = [System.IO.Path]::GetFullPath($args[0]).ToLowerInvariant()
$currentPid = [int]$args[1]
Get-CimInstance Win32_Process -Filter "name='atm-agent.exe'" |
  Where-Object {
    $_.ExecutablePath -and
    ([System.IO.Path]::GetFullPath($_.ExecutablePath).ToLowerInvariant() -eq $target) -and
    ($_.ProcessId -ne $currentPid)
  } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
"""
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script, str(executable_path), str(os.getpid())],
        capture_output=True,
        text=True,
        check=False,
    )


def remove_previous_agent(target_exe: Path, source_exe: Path) -> None:
    if os.name != "nt":
        return

    stop_existing_service()
    delete_existing_service()
    terminate_processes_for_path(target_exe)

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


class AtmAgent:
    def __init__(self, config_path: Path, stop_event: threading.Event | None = None) -> None:
        self.config_path = config_path
        self.local_config = load_local_config(config_path)
        self.logger = setup_logger(self.local_config.local_log_path)
        self.api = ApiClient(self.local_config)
        self.update_manager = UpdateManager(self.api, self.local_config)
        self.stop_event = stop_event or threading.Event()
        self.remote_config: RemoteConfig | None = None
        self.applied_config_version = 0

    def sync_config(self) -> None:
        config = self.api.get_config()
        try:
            self.update_manager.apply_remote_config(config)
            self.remote_config = config
            self.applied_config_version = config.config_version
            self.api.ack_config(config.config_version, True, "Config applied successfully")
            write_state(
                self.local_config,
                last_config_sync_at=utc_now_iso(),
                config_version=config.config_version,
                applied_config_version=config.config_version,
                media_path=config.media_path,
                backup_path=config.backup_path,
                temp_path=config.temp_path,
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
            self.update_manager.current_package_version,
            self.applied_config_version,
        )
        update = self.api.check_update()
        if update:
            self.update_manager.apply_update(update, config)

    def process_commands(self) -> bool:
        commands = self.api.get_commands()
        for command in commands:
            if command.get("command_type") != "reboot":
                continue
            self.handle_reboot_command(command)
            return True
        return False

    def handle_reboot_command(self, command: dict) -> None:
        command_id = int(command["id"])
        payload = command.get("payload") or {}
        delay_seconds = int(payload.get("delay_seconds") or 60)
        reason = str(payload.get("reason") or "ATM Media Update Manager requested restart")
        self.logger.warning("Reboot command received. command_id=%s delay=%ss reason=%s", command_id, delay_seconds, reason)
        self.api.ack_command(command_id, "acknowledged", "Reboot command received")
        try:
            self.schedule_reboot(delay_seconds, reason)
            self.api.ack_command(command_id, "completed", f"Reboot scheduled in {delay_seconds} seconds")
            write_state(
                self.local_config,
                last_reboot_requested_at=utc_now_iso(),
                last_reboot_status="scheduled",
                last_reboot_delay_seconds=delay_seconds,
            )
        except Exception as exc:
            self.api.ack_command(command_id, "failed", str(exc))
            write_state(self.local_config, last_reboot_status="failed", last_reboot_error=str(exc))
            raise

    def schedule_reboot(self, delay_seconds: int, reason: str) -> None:
        if os.name != "nt":
            raise RuntimeError("Reboot command is only supported on Windows")
        safe_delay = max(30, min(3600, delay_seconds))
        subprocess.run(
            ["shutdown.exe", "/r", "/t", str(safe_delay), "/c", reason[:512]],
            check=True,
            capture_output=True,
            text=True,
        )

    def run_forever(self) -> None:
        last_heartbeat = 0.0
        last_check = 0.0
        last_config = 0.0
        last_commands = 0.0
        self.logger.info("ATM Media Agent %s started for %s", AGENT_VERSION, self.local_config.atm_id)

        while not self.stop_event.is_set():
            now = time.monotonic()
            config = self.remote_config
            heartbeat_interval = config.heartbeat_interval_seconds if config else self.local_config.fallback_heartbeat_interval_seconds
            check_interval = config.check_interval_seconds if config else self.local_config.fallback_check_interval_seconds

            try:
                if now - last_config >= min(check_interval, 60):
                    self.sync_config()
                    last_config = now
                    config = self.remote_config

                if now - last_heartbeat >= heartbeat_interval:
                    self.api.heartbeat(
                        AGENT_VERSION,
                        "running",
                        self.update_manager.current_package_version,
                        self.applied_config_version,
                    )
                    write_state(
                        self.local_config,
                        last_heartbeat_at=utc_now_iso(),
                        agent_version=AGENT_VERSION,
                        service_status="running",
                        latency_ms=self.api.last_latency_ms,
                    )
                    last_heartbeat = now

                if now - last_commands >= min(heartbeat_interval, 30):
                    if self.process_commands():
                        last_commands = now
                        self.stop_event.wait(5)
                        continue
                    last_commands = now

                if config and now - last_check >= check_interval:
                    update = self.api.check_update()
                    write_state(self.local_config, last_update_check_at=utc_now_iso(), has_update=bool(update))
                    if update:
                        self.update_manager.apply_update(update, config)
                        write_state(
                            self.local_config,
                            current_package_version=self.update_manager.current_package_version,
                            last_update_error=None,
                        )
                    last_check = now
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
                "Open Command Prompt or PowerShell with Run as administrator, then run install again."
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
    )
    validate_server_credentials(local_config)

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
                "Stop the existing service with: sc.exe stop ATMMediaAgent, then run install again."
            ) from exc

    if os.name != "nt":
        print(f"Config written to {config_path}. Windows Service installation is only available on Windows.")
        return

    if not getattr(sys, "frozen", False):
        raise SystemExit("Build atm-agent.exe with build_agent.bat before installing the Windows Service.")

    bin_path = f'"{target_exe}" service --config "{config_path}"'
    subprocess.run(
        ["sc.exe", "create", SERVICE_NAME, "binPath=", bin_path, "start=", "auto", "DisplayName=", SERVICE_DISPLAY_NAME],
        check=True,
    )
    subprocess.run(["sc.exe", "description", SERVICE_NAME, "Pull-based ATM media update agent"], check=True)
    subprocess.run(
        ["sc.exe", "failure", SERVICE_NAME, "reset=", "86400", "actions=", "restart/60000/restart/60000/restart/60000"],
        check=True,
    )
    subprocess.run(["sc.exe", "start", SERVICE_NAME], check=True)
    print(f"Installed and started {SERVICE_DISPLAY_NAME}.")


def uninstall(_: argparse.Namespace) -> None:
    if os.name != "nt":
        print("Windows Service uninstall is only available on Windows.")
        return
    subprocess.run(["sc.exe", "stop", SERVICE_NAME], check=False)
    subprocess.run(["sc.exe", "delete", SERVICE_NAME], check=True)
    print(f"Uninstalled {SERVICE_DISPLAY_NAME}.")


def service_status() -> str:
    if os.name != "nt":
        return "not available outside Windows"
    result = subprocess.run(["sc.exe", "query", SERVICE_NAME], capture_output=True, text=True, check=False)
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

    session = requests.Session()
    session.headers.update({"X-ATM-ID": config.atm_id, "X-API-Key": config.api_key})
    try:
        response = session.get(f"{config.server_url}/api/agent/config", timeout=20)
        if response.status_code == 200:
            payload = response.json()
            print("Server Connectivity: OK")
            print(f"Server Config Version: {payload.get('config_version', '-')}")
            print(f"Media Path: {payload.get('media_path', '-')}")
            print(f"Backup Path: {payload.get('backup_path', '-')}")
            print(f"Temp Path: {payload.get('temp_path', '-')}")
        else:
            print(f"Server Connectivity: Failed HTTP {response.status_code}")
            print(f"Server Response: {response.text[:500]}")
    except requests.RequestException as exc:
        print(f"Server Connectivity: Failed {exc}")


def version_command(_: argparse.Namespace) -> None:
    print(AGENT_VERSION)


def service_main(args: argparse.Namespace) -> None:
    if os.name != "nt":
        AtmAgent(Path(args.config)).run_forever()
        return
    try:
        from service import run_service
    except ImportError as exc:
        raise SystemExit("pywin32 is required for Windows Service mode. Build the agent with build_agent.bat.") from exc
    run_service(Path(args.config))


def main() -> None:
    parser = argparse.ArgumentParser(description="ATM Media Update Agent")
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
    install_parser.set_defaults(func=install)

    uninstall_parser = sub.add_parser("uninstall")
    uninstall_parser.set_defaults(func=uninstall)

    status_parser = sub.add_parser("status")
    status_parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    status_parser.set_defaults(func=status_command)

    version_parser = sub.add_parser("version")
    version_parser.set_defaults(func=version_command)

    run_parser = sub.add_parser("run")
    run_parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    run_parser.add_argument("--once", action="store_true")
    run_parser.set_defaults(func=lambda args: AtmAgent(Path(args.config)).run_once() if args.once else AtmAgent(Path(args.config)).run_forever())

    service_parser = sub.add_parser("service")
    service_parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    service_parser.set_defaults(func=service_main)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
