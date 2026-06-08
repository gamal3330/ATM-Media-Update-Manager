from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Protocol

from config_manager import CashLayoutItem, CashMonitoringConfig, RemoteConfig
from xfs_cdm_reader import CashUnitRead as XfsCashUnitRead
from xfs_cdm_reader import XfsCdmReadResult, XfsCdmStatusResult, read_cash_units, read_cdm_status

if TYPE_CHECKING:
    from api_client import ApiClient


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DispenseCashUnit:
    cassette_no: int
    cassette_id: str
    cassette_name: str
    reported_currency: str
    reported_denomination: int
    initial_count: int
    current_count: int
    reject_count: int
    retract_count: int
    dispensed_count: int
    presented_count: int
    status: str
    physical_status: str


@dataclass
class RejectRetractStatus:
    reject_count: int
    retract_count: int
    reject_status: str
    retract_status: str
    reject_max_capacity: int = 100
    retract_max_capacity: int = 50


@dataclass
class DispenseCashSnapshot:
    atm_id: str
    source: str
    atm_cash_mode: str
    read_at: str
    cash_units: list[DispenseCashUnit]
    reject_retract: RejectRetractStatus

    def to_payload(self) -> dict:
        return {
            "atm_id": self.atm_id,
            "source": self.source,
            "atm_cash_mode": self.atm_cash_mode,
            "read_at": self.read_at,
            "cash_units": [asdict(unit) for unit in self.cash_units],
            "reject_retract": asdict(self.reject_retract),
        }


class ICashDispenseProvider(Protocol):
    source: str

    def get_dispense_cash_snapshot(self, atm_id: str, config: CashMonitoringConfig) -> list[DispenseCashUnit]:
        ...

    def get_reject_retract_status(self, config: CashMonitoringConfig) -> RejectRetractStatus:
        ...


class XfsCdmProvider:
    source = "xfs_cdm"

    def __init__(
        self,
        logical_service: str | None = None,
        xfs_profile: str = "ncr_aptra",
        msxfs_path: str | None = None,
        version_range: str = "0x00031E03",
    ) -> None:
        self.xfs_profile = (xfs_profile or "ncr_aptra").strip().lower()
        default_logical_service = "CDM" if self.xfs_profile == "grg" else "MediaDispenser1"
        self.logical_service = (
            logical_service or os.environ.get("ATM_XFS_CDM_LOGICAL_SERVICE", default_logical_service)
        ).strip() or default_logical_service
        self.msxfs_path = (msxfs_path or os.environ.get("ATM_MSXFS_PATH") or "").strip() or None
        self.version_range = int(str(version_range or "0x00031E03"), 0)
        self.last_result: XfsCdmReadResult | None = None

    def _read(self) -> XfsCdmReadResult:
        self.last_result = read_cash_units(
            self.logical_service,
            msxfs_path=self.msxfs_path,
            version_range=self.version_range,
        )
        return self.last_result

    def get_cdm_status(self) -> XfsCdmStatusResult:
        return read_cdm_status(
            self.logical_service,
            msxfs_path=self.msxfs_path,
            version_range=self.version_range,
        )

    @staticmethod
    def _layout_for(config: CashMonitoringConfig, cassette_no: int) -> CashLayoutItem:
        for item in config.cash_layout:
            if item.cassette_no == cassette_no:
                return item
        return CashLayoutItem(cassette_no, "YER", 1000, 2000, 300, 100)

    @staticmethod
    def _is_reject_or_retract_unit(unit: XfsCashUnitRead) -> bool:
        text = f"{unit.unit_type} {unit.cassette_name} {unit.unit_id}".upper()
        return unit.denomination <= 0 or "REJECT" in text or "RETRACT" in text

    @staticmethod
    def _cash_status(current_count: int, layout: CashLayoutItem, xfs_status: str) -> str:
        upper_status = xfs_status.upper()
        if upper_status in {"MISSING", "INOPERATIVE", "INOP", "EMPTY"}:
            return upper_status
        if current_count <= 0:
            return "EMPTY"
        if current_count <= layout.low_threshold:
            return "LOW"
        return "OK"

    @staticmethod
    def _physical_status(xfs_status: str) -> str:
        upper_status = xfs_status.upper()
        if upper_status in {"MISSING", "INOPERATIVE", "INOP"}:
            return upper_status
        return "PRESENT"

    @staticmethod
    def _unit_max_capacity(unit: XfsCashUnitRead) -> int:
        values = [int(getattr(unit, "max_capacity", 0) or 0)]
        values.extend(
            int(getattr(physical, "max_capacity", 0) or 0)
            for physical in getattr(unit, "physical_units", []) or []
        )
        return max(values or [0])

    @staticmethod
    def _safe_retract_count(unit: XfsCashUnitRead) -> int:
        value = int(getattr(unit, "retracted_count", 0) or 0)
        # Some GRG XFS providers expose uninitialized high-order values here.
        if value < 0 or value > 100000:
            return 0
        return value

    @staticmethod
    def _reported_currency_and_denomination(
        unit: XfsCashUnitRead,
        layout: CashLayoutItem,
    ) -> tuple[str, int]:
        return layout.currency, layout.denomination

    def get_dispense_cash_snapshot(self, atm_id: str, config: CashMonitoringConfig) -> list[DispenseCashUnit]:
        result = self._read()
        units: list[DispenseCashUnit] = []
        dispense_units = [unit for unit in result.cash_units if not self._is_reject_or_retract_unit(unit)]
        for logical_cassette_no, xfs_unit in enumerate(dispense_units, start=1):
            layout = self._layout_for(config, logical_cassette_no)
            reported_currency, reported_denomination = self._reported_currency_and_denomination(xfs_unit, layout)
            current_count = int(xfs_unit.current_count)
            units.append(
                DispenseCashUnit(
                    cassette_no=logical_cassette_no,
                    cassette_id=xfs_unit.unit_id or f"CST{xfs_unit.cassette_no:02d}",
                    cassette_name=xfs_unit.cassette_name or f"Dispense Cassette {logical_cassette_no}",
                    reported_currency=reported_currency,
                    reported_denomination=reported_denomination,
                    initial_count=int(xfs_unit.initial_count),
                    current_count=current_count,
                    reject_count=int(xfs_unit.reject_count),
                    retract_count=self._safe_retract_count(xfs_unit),
                    dispensed_count=int(xfs_unit.dispensed_count),
                    presented_count=int(xfs_unit.presented_count),
                    status=self._cash_status(current_count, layout, xfs_unit.status),
                    physical_status=self._physical_status(xfs_unit.status),
                )
            )
        return units

    def get_reject_retract_status(self, config: CashMonitoringConfig) -> RejectRetractStatus:
        result = self.last_result or self._read()
        reject_units = [unit for unit in result.cash_units if self._is_reject_or_retract_unit(unit)]
        dispense_units = [unit for unit in result.cash_units if not self._is_reject_or_retract_unit(unit)]
        reject_count = sum(int(unit.current_count) for unit in reject_units)
        if reject_count <= 0:
            reject_count = sum(int(unit.reject_count) for unit in dispense_units)
        retract_count = sum(self._safe_retract_count(unit) for unit in result.cash_units)
        reject_status = "OK"
        retract_status = "OK"
        for unit in reject_units:
            if unit.status.upper() not in {"OK", "LOW"}:
                reject_status = unit.status.upper()
                break
        return RejectRetractStatus(
            reject_count=max(0, reject_count),
            retract_count=max(0, retract_count),
            reject_status=reject_status,
            retract_status=retract_status,
            reject_max_capacity=max([self._unit_max_capacity(unit) for unit in reject_units if self._unit_max_capacity(unit) > 0] or [100]),
            retract_max_capacity=50,
        )


class VendorCdmProvider:
    source = "vendor_cdm"

    def get_dispense_cash_snapshot(self, atm_id: str, config: CashMonitoringConfig) -> list[DispenseCashUnit]:
        raise NotImplementedError("Vendor CDM provider is a read-only integration stub until API details are available")

    def get_reject_retract_status(self, config: CashMonitoringConfig) -> RejectRetractStatus:
        raise NotImplementedError("Vendor CDM provider is a read-only integration stub until API details are available")


class CashMonitoringModule:
    name = "cash_monitoring"

    def __init__(self, api: ApiClient, atm_id: str, logger: logging.Logger) -> None:
        self.api = api
        self.atm_id = atm_id
        self.logger = logger
        self.config: CashMonitoringConfig | None = None
        self.provider: ICashDispenseProvider = XfsCdmProvider()
        self.last_read = 0.0
        self.status = "disabled"
        self.last_snapshot_at: str | None = None
        self.last_unit_count = 0
        self.last_error: str | None = None
        self.last_cdm_status: dict | None = None
        self._last_cdm_status_signature: dict[str, str] | None = None
        self._last_cassette_states: dict[int, str] = {}
        self._cdm_status_error_reported = False
        self._cdm_busy_started_at: float | None = None

    def configure(self, config: RemoteConfig) -> None:
        self.config = config.cash_monitoring
        if self.config.atm_cash_mode != "DISPENSE_ONLY":
            raise ValueError("Only DISPENSE_ONLY ATMs are supported by this agent version")

        provider_name = self.config.provider
        if provider_name == "xfs_cdm":
            self.provider = XfsCdmProvider(
                self.config.xfs_logical_service,
                self.config.xfs_profile,
                self.config.xfs_msxfs_path,
                self.config.xfs_version_range,
            )
        elif provider_name == "vendor_cdm":
            self.provider = VendorCdmProvider()
        else:
            raise ValueError(f"Unsupported cash monitoring provider: {provider_name}")
        self.status = "running" if self.config.enabled else "disabled"

    def tick(self, now: float) -> None:
        if self.config is None or not self.config.enabled:
            self.status = "disabled"
            return
        if now - self.last_read < self.config.read_interval_seconds:
            return

        try:
            self.logger.info(
                "Reading cash snapshot: provider=%s profile=%s logical_service=%s",
                self.provider.source,
                self.config.xfs_profile,
                self.config.xfs_logical_service,
            )
            cash_units = self.provider.get_dispense_cash_snapshot(self.atm_id, self.config)
            reject_retract = self.provider.get_reject_retract_status(self.config)
            snapshot = DispenseCashSnapshot(
                atm_id=self.atm_id,
                source=self.provider.source,
                atm_cash_mode=self.config.atm_cash_mode,
                read_at=utc_now_iso(),
                cash_units=cash_units,
                reject_retract=reject_retract,
            )
            self.api.cash_snapshot(snapshot.to_payload())
            self._report_cdm_status_changes(now)
            self._report_cassette_status_changes(cash_units)
        except Exception as exc:
            self.status = "error"
            self.last_error = str(exc)
            self.logger.exception("Cash snapshot failed: %s", exc)
            self.api.log(
                "error",
                "Cash snapshot failed",
                {
                    "error": str(exc),
                    "provider": self.provider.source,
                    "xfs_profile": self.config.xfs_profile,
                    "xfs_logical_service": self.config.xfs_logical_service,
                    "xfs_msxfs_path": self.config.xfs_msxfs_path,
                    "xfs_version_range": self.config.xfs_version_range,
                },
            )
            raise

        self.last_read = now
        self.last_snapshot_at = snapshot.read_at
        self.last_unit_count = len(cash_units)
        self.last_error = None
        self.status = "running"
        self.logger.info(
            "Cash snapshot sent: units=%s reject=%s retract=%s",
            self.last_unit_count,
            reject_retract.reject_count,
            reject_retract.retract_count,
        )

    def read_now(self, now: float) -> None:
        if self.config is None or not self.config.enabled:
            raise RuntimeError("Cash monitoring is disabled or not configured")
        self.last_read = 0.0
        self.tick(now)

    @staticmethod
    def _status_signature(status: XfsCdmStatusResult) -> dict[str, str]:
        return {
            "device": status.device_status,
            "safe_door": status.safe_door_status,
            "dispenser": status.dispenser_status,
            "intermediate_stacker": status.intermediate_stacker_status,
            "shutter": status.shutter_status,
            "transport": status.transport_status,
            "transport_position": status.transport_position_status,
            "jammed_shutter_position": status.jammed_shutter_position,
        }

    @staticmethod
    def _status_context(
        status: XfsCdmStatusResult,
        event_type: str,
        previous_state: str | None = None,
        busy_duration_seconds: int | None = None,
    ) -> dict:
        payload = status.to_dict()
        context = {
            "event_type": event_type,
            "previous_state": previous_state,
            "state": payload,
        }
        if busy_duration_seconds is not None:
            context["busy_duration_seconds"] = busy_duration_seconds
        return context

    @staticmethod
    def _shutter_event_type(value: str) -> tuple[str | None, str]:
        status = value.upper()
        if status == "OPEN":
            return "CDM_SHUTTER_OPENED", "warning"
        if status == "CLOSED":
            return "CDM_SHUTTER_CLOSED", "info"
        if status == "JAMMED":
            return "CDM_SHUTTER_JAMMED", "error"
        return None, "info"

    @staticmethod
    def _safe_door_event_type(value: str) -> tuple[str | None, str]:
        status = value.upper()
        if status == "OPEN":
            return "CDM_SAFE_DOOR_OPENED", "warning"
        if status == "CLOSED":
            return "CDM_SAFE_DOOR_CLOSED", "info"
        return None, "info"

    @staticmethod
    def _device_event_type(value: str) -> tuple[str | None, str]:
        status = value.upper()
        if status in {"HWERROR", "POWEROFF", "NODEVICE", "OFFLINE", "FRAUDATTEMPT", "POTENTIALFRAUD"}:
            return "CDM_DEVICE_ATTENTION", "error" if status in {"HWERROR", "FRAUDATTEMPT", "POTENTIALFRAUD"} else "warning"
        if status == "ONLINE":
            return "CDM_DEVICE_ONLINE", "info"
        return None, "info"

    def _log_agent_event(self, level: str, message: str, context: dict) -> None:
        try:
            self.api.log(level, message, context)
        except Exception:
            self.logger.debug("Could not send agent event log: %s", message, exc_info=True)

    def _report_cdm_status_changes(self, now: float) -> None:
        if not hasattr(self.provider, "get_cdm_status"):
            return
        try:
            status = self.provider.get_cdm_status()  # type: ignore[attr-defined]
        except Exception as exc:
            if not self._cdm_status_error_reported:
                self._log_agent_event(
                    "warning",
                    "CDM status read failed",
                    {
                        "event_type": "CDM_STATUS_READ_FAILED",
                        "error": str(exc),
                        "provider": self.provider.source,
                    },
                )
                self._cdm_status_error_reported = True
            return

        self._cdm_status_error_reported = False
        self.last_cdm_status = status.to_dict()
        signature = self._status_signature(status)
        previous = self._last_cdm_status_signature
        self._last_cdm_status_signature = signature
        device_status = (signature.get("device") or "").upper()
        previous_device_status = (previous or {}).get("device", "").upper()
        busy_duration_seconds: int | None = None
        if device_status == "BUSY" and self._cdm_busy_started_at is None:
            self._cdm_busy_started_at = now
        elif device_status == "ONLINE" and self._cdm_busy_started_at is not None:
            busy_duration_seconds = max(0, int(now - self._cdm_busy_started_at))
            self._cdm_busy_started_at = None
        elif device_status not in {"BUSY", "ONLINE"}:
            self._cdm_busy_started_at = None

        if previous is None:
            initial_events = [
                (*self._shutter_event_type(signature["shutter"]), "CDM shutter initial attention", signature["shutter"]),
                (*self._safe_door_event_type(signature["safe_door"]), "CDM safe door initial attention", signature["safe_door"]),
                (*self._device_event_type(signature["device"]), "CDM device initial attention", signature["device"]),
            ]
            for event_type, level, message, value in initial_events:
                if event_type and level != "info":
                    self._log_agent_event(level, message, self._status_context(status, event_type))
            return

        checks = [
            ("shutter", self._shutter_event_type, "CDM shutter status changed"),
            ("safe_door", self._safe_door_event_type, "CDM safe door status changed"),
            ("device", self._device_event_type, "CDM device status changed"),
        ]
        for key, event_factory, message in checks:
            if previous.get(key) == signature.get(key):
                continue
            event_type, level = event_factory(signature[key])
            if event_type:
                duration = busy_duration_seconds if key == "device" and previous_device_status == "BUSY" else None
                self._log_agent_event(
                    level,
                    message,
                    self._status_context(status, event_type, previous.get(key), duration),
                )

    @staticmethod
    def _cassette_state(unit: DispenseCashUnit) -> str:
        physical = (unit.physical_status or "").upper()
        status = (unit.status or "").upper()
        if physical in {"MISSING", "INOPERATIVE", "INOP"}:
            return physical
        if status in {"MISSING", "INOPERATIVE", "INOP"}:
            return status
        return "PRESENT"

    def _report_cassette_status_changes(self, cash_units: list[DispenseCashUnit]) -> None:
        current_states = {unit.cassette_no: self._cassette_state(unit) for unit in cash_units}
        if not self._last_cassette_states:
            self._last_cassette_states = current_states
            return

        for unit in cash_units:
            state = current_states[unit.cassette_no]
            previous = self._last_cassette_states.get(unit.cassette_no)
            if previous == state:
                continue

            event_type = "CASH_CASSETTE_STATUS_CHANGED"
            level = "warning"
            message = "Cash cassette status changed"
            if state == "MISSING":
                event_type = "CASH_CASSETTE_REMOVED"
                message = "Cash cassette removed"
            elif previous == "MISSING" and state == "PRESENT":
                event_type = "CASH_CASSETTE_INSERTED"
                level = "info"
                message = "Cash cassette inserted"

            self._log_agent_event(
                level,
                message,
                {
                    "event_type": event_type,
                    "cassette_no": unit.cassette_no,
                    "cassette_id": unit.cassette_id,
                    "cassette_name": unit.cassette_name,
                    "previous_state": previous,
                    "state": state,
                    "status": unit.status,
                    "physical_status": unit.physical_status,
                },
            )

        self._last_cassette_states = current_states
