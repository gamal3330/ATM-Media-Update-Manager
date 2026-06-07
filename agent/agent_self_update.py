from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from checksum import sha256_file


DEFAULT_SERVICE_NAME = "ATMUnifiedAgent"
DEFAULT_TASK_NAME = "QIB ATM Manager Agent"

UpdaterLauncher = Callable[[list[str], Path], None]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_current_exe() -> Path | None:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return None


def launch_updater_process(command: list[str], cwd: Path) -> None:
    kwargs: dict[str, Any] = {"cwd": str(cwd), "close_fds": True}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(command, **kwargs)


class AgentSelfUpdateManager:
    def __init__(
        self,
        api,
        *,
        current_version: str,
        config_path: Path,
        startup_mode: str,
        current_exe: Path | None = None,
        launcher: UpdaterLauncher = launch_updater_process,
        service_name: str = DEFAULT_SERVICE_NAME,
        task_name: str = DEFAULT_TASK_NAME,
        logger=None,
    ) -> None:
        self.api = api
        self.current_version = current_version
        self.config_path = config_path
        self.current_exe = current_exe or default_current_exe()
        self.install_dir = self.current_exe.parent if self.current_exe else config_path.parent
        self.startup_mode = startup_mode if startup_mode in {"service", "scheduled-task", "none"} else "none"
        self.launcher = launcher
        self.service_name = service_name
        self.task_name = task_name
        self.logger = logger
        self.staging_root = self.install_dir / "agent_updates"
        self.result_file = self.install_dir / "update-result.json"

    def report_pending_result(self) -> bool:
        if not self.result_file.exists():
            return False
        try:
            result = json.loads(self.result_file.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            if self.logger:
                self.logger.warning("Could not read agent update result file: %s", exc)
            return False

        package_id = result.get("agent_package_id")
        if not package_id:
            return False

        ok = bool(result.get("ok"))
        status = "success" if ok else "failed"
        message = "Agent update applied" if ok else result.get("error") or "Agent update failed"
        version = result.get("version")
        finished_at = result.get("updated_at")

        self.api.report_agent_update_result(
            int(package_id),
            version,
            status,
            message,
            finished_at=finished_at,
        )
        reported_path = self.result_file.with_suffix(".reported.json")
        try:
            if reported_path.exists():
                reported_path.unlink()
            self.result_file.replace(reported_path)
        except OSError:
            try:
                self.result_file.unlink()
            except OSError:
                pass
        return True

    def check_and_apply(self) -> bool:
        if not self.current_exe or not self.current_exe.exists():
            return False

        update = self.api.check_agent_update()
        if not update:
            return False

        package_id = int(update["agent_package_id"])
        version = str(update["version"])
        if version == self.current_version:
            self.api.agent_update_progress(
                package_id,
                "applied",
                100,
                "Agent is already running the requested version",
            )
            self.api.report_agent_update_result(
                package_id,
                version,
                "success",
                "Agent is already running the requested version",
                finished_at=utc_now_iso(),
            )
            return False

        started_at = utc_now_iso()
        try:
            staging_dir = self.staging_root / f"package-{package_id}"
            staging_dir.mkdir(parents=True, exist_ok=True)
            agent_path = staging_dir / "atm-agent.exe"
            updater_path = staging_dir / "agent-updater.exe"
            for path in (agent_path, updater_path):
                if path.exists():
                    path.unlink()

            total_size = int(update.get("agent_size_bytes") or 0) + int(update.get("updater_size_bytes") or 0)
            self.api.agent_update_progress(
                package_id,
                "downloading",
                5,
                "Agent update download started",
                bytes_downloaded=0,
                total_bytes=total_size or None,
            )
            self._download_and_verify(
                package_id,
                label="atm-agent.exe",
                download_url=str(update["agent_download_url"]),
                expected_sha256=str(update["agent_sha256"]),
                target_path=agent_path,
                percent=45,
                total_size=total_size,
            )
            self._download_and_verify(
                package_id,
                label="agent-updater.exe",
                download_url=str(update["updater_download_url"]),
                expected_sha256=str(update["updater_sha256"]),
                target_path=updater_path,
                percent=75,
                total_size=total_size,
            )

            command = [
                str(updater_path),
                "--current",
                str(self.current_exe),
                "--new",
                str(agent_path),
                "--mode",
                self.startup_mode,
                "--service-name",
                self.service_name,
                "--task-name",
                self.task_name,
                "--process-name",
                self.current_exe.name,
                "--expected-sha256",
                str(update["agent_sha256"]),
                "--result-file",
                str(self.result_file),
                "--agent-package-id",
                str(package_id),
                "--version",
                version,
            ]
            self.api.agent_update_progress(package_id, "applying", 90, "Agent updater launched")
            self.launcher(command, self.install_dir)
            return True
        except Exception as exc:
            message = str(exc)
            if self.logger:
                self.logger.exception("Agent self-update failed: %s", message)
            self.api.agent_update_progress(package_id, "failed", 0, message)
            self.api.report_agent_update_result(
                package_id,
                version,
                "failed",
                message,
                started_at=started_at,
                finished_at=utc_now_iso(),
            )
            return False

    def _download_and_verify(
        self,
        package_id: int,
        *,
        label: str,
        download_url: str,
        expected_sha256: str,
        target_path: Path,
        percent: int,
        total_size: int,
    ) -> None:
        with target_path.open("wb") as output:
            downloaded, reported_total = self.api.download_package(download_url, output)
        actual_sha256 = sha256_file(target_path)
        if actual_sha256.lower() != expected_sha256.lower():
            raise ValueError(f"{label} SHA256 mismatch. expected={expected_sha256} actual={actual_sha256}")
        total = reported_total or target_path.stat().st_size
        self.api.agent_update_progress(
            package_id,
            "downloading",
            percent,
            f"{label} downloaded",
            bytes_downloaded=downloaded,
            total_bytes=total_size or total,
        )
