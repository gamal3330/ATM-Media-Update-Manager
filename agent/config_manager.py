from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


GRG_JOURNAL_GLOB = r"D:\Program Files\DTATMW\Bin\ATMAPP\Log\EJ*.log"
NCR_JOURNAL_GLOB = r"C:\Program Files (x86)\NCR APTRA\Advance NDC\Data\EJDATA.LOG"


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
class CashLayoutItem:
    cassette_no: int
    currency: str
    denomination: int
    max_capacity: int
    low_threshold: int
    critical_threshold: int


@dataclass
class CashMonitoringConfig:
    enabled: bool
    atm_cash_mode: str
    provider: str
    xfs_profile: str
    xfs_logical_service: str
    xfs_msxfs_path: str | None
    xfs_version_range: str
    read_interval_seconds: int
    cash_layout: list[CashLayoutItem]
    stale_after_minutes: int


@dataclass
class JournalReaderConfig:
    enabled: bool
    provider: str
    log_glob: str
    read_interval_seconds: int


@dataclass
class RemoteConfig:
    atm_id: str
    config_version: int
    heartbeat_interval_seconds: int
    config_sync_interval_seconds: int
    switch_probe_host: str
    switch_probe_port: int
    switch_probe_interval_seconds: int
    media_update: MediaUpdateConfig
    cash_monitoring: CashMonitoringConfig
    journal_reader: JournalReaderConfig

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
    with path.open("r", encoding="utf-8-sig") as file_obj:
        payload: dict[str, Any] = json.load(file_obj)

    required = ["server_url", "atm_id", "api_key"]
    missing = [key for key in required if not payload.get(key)]
    if missing:
        raise ValueError(f"Missing local config keys: {', '.join(missing)}")

    return LocalConfig(
        server_url=str(payload["server_url"]).strip().rstrip("/"),
        atm_id=str(payload["atm_id"]).strip(),
        api_key=str(payload["api_key"]).strip(),
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
        "atm_cash_mode": "DISPENSE_ONLY",
        "provider": "xfs_cdm",
        "xfs_profile": "ncr_aptra",
        "xfs_logical_service": "MediaDispenser1",
        "xfs_msxfs_path": None,
        "xfs_version_range": "0x00031E03",
        "read_interval_seconds": 120,
        "cash_layout": [],
        "stale_after_minutes": 10,
    }
    journal_payload = modules.get("journal_reader") or {}
    cash_layout = [
        CashLayoutItem(
            cassette_no=int(item["cassette_no"]),
            currency=str(item["currency"]),
            denomination=int(item["denomination"]),
            max_capacity=int(item.get("max_capacity") or 2000),
            low_threshold=int(item.get("low_threshold") or 300),
            critical_threshold=int(item.get("critical_threshold") or 100),
        )
        for item in cash_payload.get("cash_layout", [])
    ]
    xfs_profile = str(cash_payload.get("xfs_profile") or "ncr_aptra").strip().lower() or "ncr_aptra"
    if xfs_profile not in {"ncr_aptra", "grg", "custom"}:
        xfs_profile = "custom"
    default_logical_service = "CDM" if xfs_profile == "grg" else "MediaDispenser1"
    journal_enabled_default = xfs_profile in {"grg", "ncr_aptra"}
    default_journal_provider = "ncr_ej" if xfs_profile == "ncr_aptra" else "grg_ej"
    default_journal_glob = NCR_JOURNAL_GLOB if xfs_profile == "ncr_aptra" else GRG_JOURNAL_GLOB
    return RemoteConfig(
        atm_id=str(payload["atm_id"]),
        config_version=int(payload["config_version"]),
        heartbeat_interval_seconds=int(payload.get("heartbeat_interval_seconds") or 60),
        config_sync_interval_seconds=int(payload.get("config_sync_interval_seconds") or 120),
        switch_probe_host=str(payload.get("switch_probe_host") or "172.16.75.25").strip(),
        switch_probe_port=int(payload.get("switch_probe_port") or 10200),
        switch_probe_interval_seconds=int(payload.get("switch_probe_interval_seconds") or 3600),
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
            atm_cash_mode=str(cash_payload.get("atm_cash_mode") or "DISPENSE_ONLY"),
            provider=str(cash_payload.get("provider") or "xfs_cdm"),
            xfs_profile=xfs_profile,
            xfs_logical_service=str(cash_payload.get("xfs_logical_service") or default_logical_service).strip()
            or default_logical_service,
            xfs_msxfs_path=str(cash_payload.get("xfs_msxfs_path") or "").strip() or None,
            xfs_version_range=str(cash_payload.get("xfs_version_range") or "0x00031E03").strip() or "0x00031E03",
            read_interval_seconds=int(cash_payload.get("read_interval_seconds") or 120),
            cash_layout=cash_layout,
            stale_after_minutes=int(cash_payload.get("stale_after_minutes") or 10),
        ),
        journal_reader=JournalReaderConfig(
            enabled=bool(journal_payload.get("enabled", journal_enabled_default)),
            provider=str(journal_payload.get("provider") or default_journal_provider).strip().lower()
            or default_journal_provider,
            log_glob=str(
                journal_payload.get("log_glob")
                or default_journal_glob
            ),
            read_interval_seconds=int(journal_payload.get("read_interval_seconds") or 60),
        ),
    )
