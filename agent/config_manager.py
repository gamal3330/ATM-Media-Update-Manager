from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class LocalConfig:
    server_url: str
    atm_id: str
    api_key: str
    local_log_path: str
    fallback_check_interval_seconds: int = 300
    fallback_heartbeat_interval_seconds: int = 60
    fallback_config_sync_interval_seconds: int = 120


@dataclass
class MediaUpdateConfig:
    enabled: bool
    media_path: str
    backup_path: str
    temp_path: str
    check_interval_seconds: int
    allowed_extensions: set[str]


@dataclass
class CashMonitoringConfig:
    enabled: bool
    provider: str
    read_interval_seconds: int
    low_threshold_default: int
    critical_threshold_default: int
    stale_after_minutes: int


@dataclass
class RemoteConfig:
    atm_id: str
    config_version: int
    heartbeat_interval_seconds: int
    config_sync_interval_seconds: int
    media_update: MediaUpdateConfig
    cash_monitoring: CashMonitoringConfig

    @property
    def media_path(self) -> str:
        return self.media_update.media_path

    @property
    def backup_path(self) -> str:
        return self.media_update.backup_path

    @property
    def temp_path(self) -> str:
        return self.media_update.temp_path

    @property
    def check_interval_seconds(self) -> int:
        return self.media_update.check_interval_seconds

    @property
    def allowed_extensions(self) -> set[str]:
        return self.media_update.allowed_extensions


def load_local_config(path: Path) -> LocalConfig:
    with path.open("r", encoding="utf-8") as file_obj:
        payload: dict[str, Any] = json.load(file_obj)

    required = ["server_url", "atm_id", "api_key"]
    missing = [key for key in required if not payload.get(key)]
    if missing:
        raise ValueError(f"Missing local config keys: {', '.join(missing)}")

    return LocalConfig(
        server_url=str(payload["server_url"]).rstrip("/"),
        atm_id=str(payload["atm_id"]),
        api_key=str(payload["api_key"]),
        local_log_path=str(payload.get("local_log_path") or "C:\\ATM\\Agent\\logs"),
        fallback_check_interval_seconds=int(payload.get("fallback_check_interval_seconds") or 300),
        fallback_heartbeat_interval_seconds=int(payload.get("fallback_heartbeat_interval_seconds") or 60),
        fallback_config_sync_interval_seconds=int(payload.get("fallback_config_sync_interval_seconds") or 120),
    )


def write_local_config(path: Path, config: LocalConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "server_url": config.server_url,
        "atm_id": config.atm_id,
        "api_key": config.api_key,
        "local_log_path": config.local_log_path,
        "fallback_check_interval_seconds": config.fallback_check_interval_seconds,
        "fallback_heartbeat_interval_seconds": config.fallback_heartbeat_interval_seconds,
        "fallback_config_sync_interval_seconds": config.fallback_config_sync_interval_seconds,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def parse_remote_config(payload: dict[str, Any]) -> RemoteConfig:
    modules = payload.get("modules") or {}
    media_payload = modules.get("media_update") or {
        "enabled": True,
        "media_path": payload["media_path"],
        "backup_path": payload["backup_path"],
        "temp_path": payload["temp_path"],
        "check_interval_seconds": payload.get("check_interval_seconds") or 300,
        "allowed_extensions": payload.get("allowed_extensions", []),
    }
    cash_payload = modules.get("cash_monitoring") or {
        "enabled": False,
        "provider": "mock",
        "read_interval_seconds": 120,
        "low_threshold_default": 300,
        "critical_threshold_default": 100,
        "stale_after_minutes": 10,
    }
    return RemoteConfig(
        atm_id=str(payload["atm_id"]),
        config_version=int(payload["config_version"]),
        heartbeat_interval_seconds=int(payload.get("heartbeat_interval_seconds") or 60),
        config_sync_interval_seconds=int(payload.get("config_sync_interval_seconds") or 120),
        media_update=MediaUpdateConfig(
            enabled=bool(media_payload.get("enabled", True)),
            media_path=str(media_payload["media_path"]),
            backup_path=str(media_payload["backup_path"]),
            temp_path=str(media_payload["temp_path"]),
            check_interval_seconds=int(media_payload.get("check_interval_seconds") or 300),
            allowed_extensions={str(item).lower().lstrip(".") for item in media_payload.get("allowed_extensions", [])},
        ),
        cash_monitoring=CashMonitoringConfig(
            enabled=bool(cash_payload.get("enabled", False)),
            provider=str(cash_payload.get("provider") or "mock"),
            read_interval_seconds=int(cash_payload.get("read_interval_seconds") or 120),
            low_threshold_default=int(cash_payload.get("low_threshold_default") or 300),
            critical_threshold_default=int(cash_payload.get("critical_threshold_default") or 100),
            stale_after_minutes=int(cash_payload.get("stale_after_minutes") or 10),
        ),
    )
