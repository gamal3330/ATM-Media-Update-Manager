from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

from config_manager import RemoteConfig
from xfs_siu_reader import XfsSiuStatusResult, read_siu_status

if TYPE_CHECKING:
    from api_client import ApiClient


class TerminalStatusModule:
    name = "terminal_status"

    def __init__(self, api: ApiClient, logger: logging.Logger) -> None:
        self.api = api
        self.logger = logger
        self.config: RemoteConfig | None = None
        self.status = "disabled"
        self.last_read = 0.0
        self.last_error: str | None = None
        self.last_siu_status: dict[str, Any] | None = None
        self.siu_logical_service = os.environ.get("ATM_XFS_SIU_LOGICAL_SERVICE", "SIU").strip() or "SIU"
        self._last_signature: dict[str, str] | None = None
        self._siu_error_reported = False

    def configure(self, config: RemoteConfig) -> None:
        self.config = config
        cash_config = config.cash_monitoring
        self.status = "running" if cash_config.enabled and cash_config.provider == "xfs_cdm" else "disabled"

    def tick(self, now: float) -> None:
        if self.config is None:
            self.status = "disabled"
            return
        cash_config = self.config.cash_monitoring
        if not cash_config.enabled or cash_config.provider != "xfs_cdm":
            self.status = "disabled"
            return
        interval = max(30, int(cash_config.read_interval_seconds or 120))
        if now - self.last_read < interval:
            return
        self.last_read = now

        try:
            result = read_siu_status(
                self.siu_logical_service,
                msxfs_path=cash_config.xfs_msxfs_path,
                version_range=int(str(cash_config.xfs_version_range or "0x00031E03"), 0),
            )
        except Exception as exc:
            self.status = "warning"
            self.last_error = str(exc)
            if not self._siu_error_reported:
                self._log_event(
                    "warning",
                    "SIU status read failed",
                    {
                        "event_type": "SIU_STATUS_READ_FAILED",
                        "error": str(exc),
                        "logical_service": self.siu_logical_service,
                    },
                )
                self._siu_error_reported = True
            return

        self._siu_error_reported = False
        self.last_error = None
        self.last_siu_status = result.to_dict()
        self.status = "running"
        self._report_status_changes(result)

    def _log_event(self, level: str, message: str, context: dict[str, Any]) -> None:
        try:
            self.api.log(level, message, context)
        except Exception:
            self.logger.debug("Could not send terminal status event: %s", message, exc_info=True)

    @staticmethod
    def _port_status(result: XfsSiuStatusResult, group: str, name: str) -> str:
        container = getattr(result, group) or {}
        port = container.get(name) or {}
        statuses = port.get("statuses") or []
        return "+".join(statuses) if statuses else "UNKNOWN"

    @classmethod
    def _signature(cls, result: XfsSiuStatusResult) -> dict[str, str]:
        return {
            "device": result.device_status,
            "cabinet": cls._port_status(result, "doors", "cabinet"),
            "safe": cls._port_status(result, "doors", "safe"),
            "vandal_shield": cls._port_status(result, "doors", "vandal_shield"),
            "operator_switch": cls._port_status(result, "sensors", "operator_switch"),
            "tamper": cls._port_status(result, "sensors", "tamper"),
            "internal_tamper": cls._port_status(result, "sensors", "internal_tamper"),
            "seismic": cls._port_status(result, "sensors", "seismic"),
            "heat": cls._port_status(result, "sensors", "heat"),
            "proximity": cls._port_status(result, "sensors", "proximity"),
        }

    @staticmethod
    def _has_any(value: str, states: set[str]) -> bool:
        parts = {item.strip().upper() for item in value.split("+") if item.strip()}
        return bool(parts & states)

    def _door_event(self, door_name: str, state: str) -> tuple[str | None, str, str]:
        labels = {
            "cabinet": "CABINET_DOOR",
            "safe": "SAFE_DOOR",
            "vandal_shield": "VANDAL_SHIELD",
        }
        prefix = labels.get(door_name, door_name.upper())
        if self._has_any(state, {"OPEN", "AJAR", "JAMMED"}):
            return f"SIU_{prefix}_OPENED", "warning", "SIU door opened"
        if self._has_any(state, {"CLOSED"}):
            return f"SIU_{prefix}_CLOSED", "info", "SIU door closed"
        return None, "info", "SIU door status changed"

    def _sensor_event(self, sensor_name: str, state: str) -> tuple[str | None, str, str]:
        attention_states = {"ON", "PRESENT", "MAINTENANCE", "SUPERVISOR"}
        if sensor_name == "operator_switch" and self._has_any(state, {"MAINTENANCE", "SUPERVISOR"}):
            return "SIU_OPERATOR_SWITCH_CHANGED", "warning", "SIU operator switch changed"
        if sensor_name in {"tamper", "internal_tamper", "seismic", "heat"} and self._has_any(state, attention_states):
            return f"SIU_{sensor_name.upper()}_TRIGGERED", "error", "SIU sensor triggered"
        if sensor_name == "proximity" and self._has_any(state, {"PRESENT"}):
            return "SIU_PROXIMITY_PRESENT", "info", "SIU proximity detected"
        return None, "info", "SIU sensor status changed"

    def _context(self, result: XfsSiuStatusResult, event_type: str, key: str, state: str, previous: str | None) -> dict[str, Any]:
        return {
            "event_type": event_type,
            "port": key,
            "previous_state": previous,
            "state": state,
            "siu": result.to_dict(),
        }

    def _report_status_changes(self, result: XfsSiuStatusResult) -> None:
        signature = self._signature(result)
        previous = self._last_signature
        self._last_signature = signature

        if previous is None:
            for key, state in signature.items():
                if key in {"cabinet", "safe", "vandal_shield"}:
                    event_type, level, message = self._door_event(key, state)
                elif key != "device":
                    event_type, level, message = self._sensor_event(key, state)
                else:
                    event_type, level, message = None, "info", ""
                if event_type and level in {"warning", "error"}:
                    self._log_event(level, message, self._context(result, event_type, key, state, None))
            return

        for key, state in signature.items():
            previous_state = previous.get(key)
            if previous_state == state:
                continue
            if key in {"cabinet", "safe", "vandal_shield"}:
                event_type, level, message = self._door_event(key, state)
            elif key != "device":
                event_type, level, message = self._sensor_event(key, state)
            else:
                event_type, level, message = (
                    ("SIU_DEVICE_ONLINE", "info", "SIU device online")
                    if state == "ONLINE"
                    else ("SIU_DEVICE_ATTENTION", "warning", "SIU device needs attention")
                )
            if event_type:
                self._log_event(level, message, self._context(result, event_type, key, state, previous_state))
