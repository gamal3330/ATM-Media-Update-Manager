from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Protocol

from config_manager import CashLayoutItem, CashMonitoringConfig, RemoteConfig

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

    def get_dispense_cash_snapshot(self, atm_id: str, config: CashMonitoringConfig) -> list[DispenseCashUnit]:
        raise NotImplementedError("XFS CDM provider is not enabled yet. Run xfs-cdm-diagnose first.")

    def get_reject_retract_status(self, config: CashMonitoringConfig) -> RejectRetractStatus:
        raise NotImplementedError("XFS CDM provider is not enabled yet. Run xfs-cdm-diagnose first.")


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

    def configure(self, config: RemoteConfig) -> None:
        self.config = config.cash_monitoring
        if self.config.atm_cash_mode != "DISPENSE_ONLY":
            raise ValueError("Only DISPENSE_ONLY ATMs are supported by this agent version")

        provider_name = self.config.provider
        if provider_name == "xfs_cdm":
            self.provider = XfsCdmProvider()
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
        self.last_read = now
        self.status = "running"
