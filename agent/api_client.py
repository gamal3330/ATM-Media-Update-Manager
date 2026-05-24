from __future__ import annotations

import time
from typing import Any, BinaryIO

import requests

from config_manager import LocalConfig, RemoteConfig, parse_remote_config


class ApiClient:
    def __init__(self, config: LocalConfig) -> None:
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({"X-ATM-ID": config.atm_id, "X-API-Key": config.api_key})
        self.last_latency_ms: int | None = None

    def url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self.config.server_url}{path}"

    def get_config(self) -> RemoteConfig:
        started = time.perf_counter()
        response = self.session.get(self.url("/api/agent/config"), timeout=30)
        response.raise_for_status()
        self.last_latency_ms = max(0, int((time.perf_counter() - started) * 1000))
        return parse_remote_config(response.json())

    def ack_config(self, version: int, success: bool, message: str | None = None) -> None:
        response = self.session.post(
            self.url("/api/agent/config-ack"),
            json={
                "atm_id": self.config.atm_id,
                "applied_config_version": version,
                "success": success,
                "message": message,
            },
            timeout=30,
        )
        response.raise_for_status()

    def heartbeat(
        self,
        agent_version: str,
        service_status: str,
        current_package_version: str | None,
        applied_config_version: int,
        measured_latency_ms: int | None = None,
    ) -> int:
        started = time.perf_counter()
        payload: dict[str, Any] = {
            "atm_id": self.config.atm_id,
            "agent_version": agent_version,
            "service_status": service_status,
            "current_package_version": current_package_version,
            "applied_config_version": applied_config_version,
        }
        latency = measured_latency_ms if measured_latency_ms is not None else self.last_latency_ms
        if latency is not None:
            payload["latency_ms"] = latency
        response = self.session.post(
            self.url("/api/agent/heartbeat"),
            json=payload,
            timeout=20,
        )
        response.raise_for_status()
        self.last_latency_ms = max(0, int((time.perf_counter() - started) * 1000))
        return self.last_latency_ms

    def check_update(self) -> dict[str, Any] | None:
        started = time.perf_counter()
        response = self.session.get(self.url("/api/agent/check-update"), timeout=30)
        response.raise_for_status()
        self.last_latency_ms = max(0, int((time.perf_counter() - started) * 1000))
        payload = response.json()
        if not payload.get("has_update") and not payload.get("update_available"):
            return None
        return payload

    def get_commands(self) -> list[dict[str, Any]]:
        response = self.session.get(self.url("/api/agent/commands"), timeout=30)
        response.raise_for_status()
        return response.json()

    def ack_command(self, command_id: int, status: str, message: str | None = None) -> None:
        response = self.session.post(
            self.url(f"/api/agent/commands/{command_id}/ack"),
            json={"status": status, "message": message},
            timeout=30,
        )
        response.raise_for_status()

    def download_package(self, download_url: str, output: BinaryIO) -> tuple[int, int]:
        downloaded = 0
        with self.session.get(self.url(download_url), stream=True, timeout=180) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length") or 0)
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                output.write(chunk)
                downloaded += len(chunk)
        return downloaded, total

    def progress(
        self,
        package_id: int,
        phase: str,
        percent: int,
        message: str,
        bytes_downloaded: int | None = None,
        total_bytes: int | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "package_id": package_id,
            "phase": phase,
            "progress_percent": max(0, min(100, percent)),
            "message": message,
        }
        if bytes_downloaded is not None:
            payload["bytes_downloaded"] = bytes_downloaded
        if total_bytes is not None:
            payload["total_bytes"] = total_bytes
        try:
            self.session.post(self.url("/api/agent/progress"), json=payload, timeout=15)
        except requests.RequestException:
            pass

    def report_result(
        self,
        package_id: int,
        version: str,
        status: str,
        message: str,
        started_at: str,
        finished_at: str,
        rollback_done: bool | None = None,
    ) -> None:
        response = self.session.post(
            self.url("/api/agent/report-result"),
            json={
                "atm_id": self.config.atm_id,
                "package_id": package_id,
                "version": version,
                "status": status,
                "message": message,
                "started_at": started_at,
                "finished_at": finished_at,
                "rollback_done": rollback_done,
            },
            timeout=30,
        )
        response.raise_for_status()

    def log(self, level: str, message: str, details: str | dict[str, Any] | None = None) -> None:
        try:
            self.session.post(
                self.url("/api/agent/logs"),
                json={"atm_id": self.config.atm_id, "level": level, "message": message, "details": details},
                timeout=15,
            )
        except requests.RequestException:
            pass
