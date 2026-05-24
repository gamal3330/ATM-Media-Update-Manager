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


@dataclass
class RemoteConfig:
    atm_id: str
    config_version: int
    media_path: str
    backup_path: str
    temp_path: str
    heartbeat_interval_seconds: int
    check_interval_seconds: int
    allowed_extensions: set[str]


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
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def parse_remote_config(payload: dict[str, Any]) -> RemoteConfig:
    return RemoteConfig(
        atm_id=str(payload["atm_id"]),
        config_version=int(payload["config_version"]),
        media_path=str(payload["media_path"]),
        backup_path=str(payload["backup_path"]),
        temp_path=str(payload["temp_path"]),
        heartbeat_interval_seconds=int(payload.get("heartbeat_interval_seconds") or 60),
        check_interval_seconds=int(payload.get("check_interval_seconds") or 300),
        allowed_extensions={str(item).lower().lstrip(".") for item in payload.get("allowed_extensions", [])},
    )
