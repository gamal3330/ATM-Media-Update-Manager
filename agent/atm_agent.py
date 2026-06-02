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
from cash_monitoring_module import CashMonitoringModule
from config_manager import LocalConfig, RemoteConfig, load_local_config, write_local_config
from logger import setup_logger
from media_update_module import MediaUpdateModule
from module_runner import ModuleRunner
from network_probe import tcp_connect_probe
from xfs_cdm_diagnostics import diagnose_xfs_cdm, format_diagnostics
from xfs_cdm_reader import read_cash_units, format_read_result

AGENT_VERSION = "2.0.1"
DEFAULT_INSTALL_DIR = Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "ATM Media Agent"
DEFAULT_CONFIG = DEFAULT_INSTALL_DIR / "config.json"
SERVICE_NAME = "ATMUnifiedAgent"
LEGACY_SERVICE_NAMES = ["ATMMediaAgent"]
SERVICE_DISPLAY_NAME = "ATM Unified Agent Service"


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


class AtmAgent:
    def __init__(self, config_path: Path, stop_event: threading.Event | None = None) -> None:
        self.config_path = config_path
        self.local_config = load_local_config(config_path)
        self.logger = setup_logger(self.local_config.local_log_path)
        self.api = ApiClient(self.local_config)
        self.media_module = MediaUpdateModule(self.api, self.local_config, self.logger)
        self.cash_module = CashMonitoringModule(self.api, self.local_config.atm_id, self.logger)
        self.modules = ModuleRunner(self.logger)
        self.modules.register(self.media_module)
        self.modules.register(self.cash_module)
        self.stop_event = stop_event or threading.Event()
        self.remote_config: RemoteConfig | None = None
        self.applied_config_version = 0

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
        self.handle_switch_probe()
        self.modules.tick(time.monotonic())

    def run_forever(self) -> None:
        last_heartbeat = 0.0
        last_config = 0.0
        self.logger.info("ATM Unified Agent %s started for %s", AGENT_VERSION, self.local_config.atm_id)

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

                if config:
                    self.handle_switch_probe()
                    self.modules.tick(now)
                    write_state(
                        self.local_config,
                        module_statuses=self.modules.module_statuses(),
                        current_package_version=self.media_module.current_package_version,
                    )
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
                f"Stop the existing service with: sc.exe stop {SERVICE_NAME}, then run install again."
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
    subprocess.run(["sc.exe", "description", SERVICE_NAME, "Pull-based unified ATM agent"], check=True)
    subprocess.run(
        ["sc.exe", "failure", SERVICE_NAME, "reset=", "86400", "actions=", "restart/60000/restart/60000/restart/60000"],
        check=True,
    )
    start_windows_service_or_explain(config_path)


def uninstall(_: argparse.Namespace) -> None:
    if os.name != "nt":
        print("Windows Service uninstall is only available on Windows.")
        return
    subprocess.run(["sc.exe", "stop", SERVICE_NAME], check=False)
    subprocess.run(["sc.exe", "delete", SERVICE_NAME], check=True)
    print(f"Uninstalled {SERVICE_DISPLAY_NAME}.")


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
        AtmAgent(Path(args.config)).run_forever()
        return
    try:
        from service import run_service
    except ImportError as exc:
        raise SystemExit("pywin32 is required for Windows Service mode. Build the agent with build_agent.bat.") from exc
    run_service(Path(args.config))


def main() -> None:
    parser = argparse.ArgumentParser(description="ATM Unified Agent")
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
    run_parser.set_defaults(func=lambda args: AtmAgent(Path(args.config)).run_once() if args.once else AtmAgent(Path(args.config)).run_forever())

    service_parser = sub.add_parser("service")
    service_parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    service_parser.set_defaults(func=service_main)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
