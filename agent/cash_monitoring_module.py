from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Protocol

from config_manager import CashLayoutItem, CashMonitoringConfig, RemoteConfig
from xfs_cdm_reader import CashUnitRead as XfsCashUnitRead
from xfs_cdm_reader import XfsCdmReadResult, read_cash_units

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


class MockDispenseProvider:
    source = "mock"

    def get_dispense_cash_snapshot(self, atm_id: str, config: CashMonitoringConfig) -> list[DispenseCashUnit]:
        layout = config.cash_layout or [
            CashLayoutItem(1, "YER", 1000, 2000, 300, 100),
            CashLayoutItem(2, "YER", 1000, 2000, 300, 100),
            CashLayoutItem(3, "YER", 1000, 2000, 300, 100),
            CashLayoutItem(4, "YER", 1000, 2000, 300, 100),
        ]
        sample_counts = [850, 120, 25, 700]
        sample_rejects = [2, 5, 1, 0]
        units: list[DispenseCashUnit] = []
        for index, item in enumerate(layout):
            current_count = sample_counts[index % len(sample_counts)]
            status = "OK"
            if current_count <= 0:
                status = "EMPTY"
            elif current_count <= item.critical_threshold:
                status = "LOW"
            elif current_count <= item.low_threshold:
                status = "LOW"
            units.append(
                DispenseCashUnit(
                    cassette_no=item.cassette_no,
                    cassette_id=f"CST{item.cassette_no:02d}",
                    cassette_name=f"Dispense Cassette {item.cassette_no}",
                    reported_currency=item.currency,
                    reported_denomination=item.denomination,
                    initial_count=item.max_capacity,
                    current_count=current_count,
                    reject_count=sample_rejects[index % len(sample_rejects)],
                    retract_count=0,
                    dispensed_count=max(0, item.max_capacity - current_count),
                    presented_count=max(0, item.max_capacity - current_count),
                    status=status,
                    physical_status="PRESENT",
                )
            )
        return units

    def get_reject_retract_status(self, config: CashMonitoringConfig) -> RejectRetractStatus:
        return RejectRetractStatus(
            reject_count=8,
            retract_count=1,
            reject_status="OK",
            retract_status="OK",
        )


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

    def get_dispense_cash_snapshot(self, atm_id: str, config: CashMonitoringConfig) -> list[DispenseCashUnit]:
        result = self._read()
        units: list[DispenseCashUnit] = []
        dispense_units = [unit for unit in result.cash_units if not self._is_reject_or_retract_unit(unit)]
        for logical_cassette_no, xfs_unit in enumerate(dispense_units, start=1):
            layout = self._layout_for(config, logical_cassette_no)
            current_count = int(xfs_unit.current_count)
            units.append(
                DispenseCashUnit(
                    cassette_no=logical_cassette_no,
                    cassette_id=xfs_unit.unit_id or f"CST{xfs_unit.cassette_no:02d}",
                    cassette_name=xfs_unit.cassette_name or f"Dispense Cassette {logical_cassette_no}",
                    reported_currency=layout.currency,
                    reported_denomination=layout.denomination,
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
        self.provider: ICashDispenseProvider = MockDispenseProvider()
        self.last_read = 0.0
        self.status = "disabled"
        self.last_snapshot_at: str | None = None
        self.last_unit_count = 0
        self.last_error: str | None = None

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
            self.provider = MockDispenseProvider()
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
