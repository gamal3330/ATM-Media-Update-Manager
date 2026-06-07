import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


UPDATER_VERSION = "0.1.0"
DEFAULT_SERVICE_NAME = "ATMUnifiedAgent"
DEFAULT_TASK_NAME = "QIB ATM Manager Agent"
DEFAULT_PROCESS_NAME = "atm-agent.exe"


CommandRunner = Callable[[list[str], bool], subprocess.CompletedProcess]


@dataclass
class UpdateOptions:
    current_path: Path
    new_path: Path
    mode: str
    agent_package_id: int | None = None
    version: str | None = None
    service_name: str = DEFAULT_SERVICE_NAME
    task_name: str = DEFAULT_TASK_NAME
    process_name: str = DEFAULT_PROCESS_NAME
    backup_dir: Path | None = None
    result_file: Path | None = None
    expected_sha256: str | None = None
    timeout_seconds: int = 60
    kill_process: bool = True


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_command(args: list[str], ignore_errors: bool = False) -> subprocess.CompletedProcess:
    completed = subprocess.run(args, capture_output=True, text=True, timeout=30)
    if completed.returncode != 0 and not ignore_errors:
        output = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"Command failed ({completed.returncode}): {' '.join(args)} {output}".strip())
    return completed


def validate_options(options: UpdateOptions) -> None:
    if options.mode not in {"service", "scheduled-task", "none"}:
        raise ValueError("mode must be service, scheduled-task, or none")
    if options.timeout_seconds < 5:
        raise ValueError("timeout_seconds must be at least 5")
    if not options.current_path.exists():
        raise FileNotFoundError(f"Current agent was not found: {options.current_path}")
    if not options.new_path.exists():
        raise FileNotFoundError(f"New agent was not found: {options.new_path}")
    if options.current_path.resolve() == options.new_path.resolve():
        raise ValueError("current and new paths must be different")
    if options.expected_sha256:
        actual = sha256_file(options.new_path)
        if actual.lower() != options.expected_sha256.lower():
            raise ValueError(f"SHA256 mismatch for new agent. expected={options.expected_sha256} actual={actual}")


def stop_existing_startup(options: UpdateOptions, runner: CommandRunner = run_command) -> None:
    if options.mode == "service":
        runner(["sc.exe", "stop", options.service_name], True)
    elif options.mode == "scheduled-task":
        runner(["schtasks.exe", "/End", "/TN", options.task_name], True)

    if options.kill_process:
        runner(["taskkill.exe", "/IM", options.process_name, "/F"], True)


def start_existing_startup(options: UpdateOptions, runner: CommandRunner = run_command) -> bool:
    if options.mode == "service":
        runner(["sc.exe", "start", options.service_name], False)
        return True
    if options.mode == "scheduled-task":
        runner(["schtasks.exe", "/Run", "/TN", options.task_name], False)
        return True
    return False


def backup_current_agent(options: UpdateOptions) -> Path:
    backup_dir = options.backup_dir or (options.current_path.parent / "agent_backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"{options.current_path.name}.{timestamp}.bak"
    shutil.copy2(options.current_path, backup_path)
    return backup_path


def replace_with_retry(new_path: Path, current_path: Path, timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: OSError | None = None
    while time.monotonic() <= deadline:
        try:
            os.replace(new_path, current_path)
            return
        except OSError as exc:
            last_error = exc
            time.sleep(1)
    if last_error:
        raise last_error
    raise TimeoutError("Timed out waiting to replace current agent")


def perform_update(options: UpdateOptions, runner: CommandRunner = run_command) -> dict:
    validate_options(options)

    if options.mode != "none":
        stop_existing_startup(options, runner)
        time.sleep(2)

    backup_path = backup_current_agent(options)
    replace_with_retry(options.new_path, options.current_path, options.timeout_seconds)
    started = start_existing_startup(options, runner) if options.mode != "none" else False

    return {
        "ok": True,
        "status": "applied",
        "updater_version": UPDATER_VERSION,
        "agent_package_id": options.agent_package_id,
        "version": options.version,
        "mode": options.mode,
        "current_path": str(options.current_path),
        "new_path": str(options.new_path),
        "backup_path": str(backup_path),
        "started": started,
        "error": None,
        "updated_at": utc_timestamp(),
    }


def default_result_file(options: UpdateOptions | None) -> Path:
    if options and options.result_file:
        return options.result_file
    if options:
        return options.current_path.parent / "update-result.json"
    return Path.cwd() / "update-result.json"


def write_result(path: Path, result: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args(argv: list[str]) -> UpdateOptions:
    parser = argparse.ArgumentParser(description="Replace QIB ATM Manager agent executable safely.")
    parser.add_argument("--current", required=True, help="Path to the current atm-agent.exe")
    parser.add_argument("--new", required=True, help="Path to the downloaded new atm-agent.exe")
    parser.add_argument("--mode", choices=["service", "scheduled-task", "none"], default="none")
    parser.add_argument("--agent-package-id", type=int)
    parser.add_argument("--version", default="")
    parser.add_argument("--service-name", default=DEFAULT_SERVICE_NAME)
    parser.add_argument("--task-name", default=DEFAULT_TASK_NAME)
    parser.add_argument("--process-name", default=DEFAULT_PROCESS_NAME)
    parser.add_argument("--backup-dir", default="")
    parser.add_argument("--result-file", default="")
    parser.add_argument("--expected-sha256", default="")
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument("--skip-process-kill", action="store_true")
    args = parser.parse_args(argv)

    return UpdateOptions(
        current_path=Path(args.current),
        new_path=Path(args.new),
        mode=args.mode,
        agent_package_id=args.agent_package_id,
        version=args.version or None,
        service_name=args.service_name,
        task_name=args.task_name,
        process_name=args.process_name,
        backup_dir=Path(args.backup_dir) if args.backup_dir else None,
        result_file=Path(args.result_file) if args.result_file else None,
        expected_sha256=args.expected_sha256 or None,
        timeout_seconds=args.timeout_seconds,
        kill_process=not args.skip_process_kill,
    )


def main(argv: list[str] | None = None) -> int:
    options: UpdateOptions | None = None
    try:
        options = parse_args(argv or sys.argv[1:])
        result = perform_update(options)
        write_result(default_result_file(options), result)
        print(f"Agent update applied. Backup: {result['backup_path']}")
        return 0
    except Exception as exc:
        restarted_after_failure = False
        restart_error = None
        if options and options.mode != "none":
            try:
                restarted_after_failure = start_existing_startup(options)
            except Exception as restart_exc:
                restart_error = str(restart_exc)
        result = {
            "ok": False,
            "status": "failed",
            "updater_version": UPDATER_VERSION,
            "agent_package_id": options.agent_package_id if options else None,
            "version": options.version if options else None,
            "mode": options.mode if options else None,
            "current_path": str(options.current_path) if options else None,
            "new_path": str(options.new_path) if options else None,
            "backup_path": None,
            "started": restarted_after_failure,
            "error": str(exc),
            "restart_error": restart_error,
            "updated_at": utc_timestamp(),
        }
        write_result(default_result_file(options), result)
        print(f"Agent update failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
