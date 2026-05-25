from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Protocol

from config_manager import CashMonitoringConfig, RemoteConfig

if TYPE_CHECKING:
    from api_client import ApiClient


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CashUnit:
    unit_no: int
    cassette_id: str
    cassette_name: str
    currency: str
    denomination: int
    initial_count: int
    current_count: int
    reject_count: int
    dispensed_count: int
    presented_count: int
    retracted_count: int
    min_threshold: int
    max_capacity: int
    status: str
    physical_status: str


@dataclass
class CashSnapshot:
    atm_id: str
    source: str
    read_at: str
    cash_units: list[CashUnit]

    def to_payload(self) -> dict:
        return {
            "atm_id": self.atm_id,
            "source": self.source,
            "read_at": self.read_at,
            "cash_units": [asdict(unit) for unit in self.cash_units],
        }


class ICashProvider(Protocol):
    source: str

    def get_cash_snapshot(self, atm_id: str, config: CashMonitoringConfig) -> CashSnapshot:
        ...


class MockCashProvider:
    source = "mock"

    def get_cash_snapshot(self, atm_id: str, config: CashMonitoringConfig) -> CashSnapshot:
        units = [
            CashUnit(
                unit_no=1,
                cassette_id="CST01",
                cassette_name="Cassette 1",
                currency="YER",
                denomination=1000,
                initial_count=2000,
                current_count=420,
                reject_count=3,
                dispensed_count=1580,
                presented_count=1580,
                retracted_count=0,
                min_threshold=config.low_threshold_default,
                max_capacity=2000,
                status="OK",
                physical_status="PRESENT",
            ),
            CashUnit(
                unit_no=2,
                cassette_id="CST02",
                cassette_name="Cassette 2",
                currency="YER",
                denomination=500,
                initial_count=2000,
                current_count=95,
                reject_count=1,
                dispensed_count=1905,
                presented_count=1905,
                retracted_count=0,
                min_threshold=config.low_threshold_default,
                max_capacity=2000,
                status="LOW",
                physical_status="PRESENT",
            ),
        ]
        return CashSnapshot(atm_id=atm_id, source=self.source, read_at=utc_now_iso(), cash_units=units)


class XfsCashProvider:
    source = "xfs"

    def get_cash_snapshot(self, atm_id: str, config: CashMonitoringConfig) -> CashSnapshot:
        raise NotImplementedError("XFS provider is a read-only integration stub until vendor SDK is available")


class VendorApiCashProvider:
    source = "vendor_api"

    def get_cash_snapshot(self, atm_id: str, config: CashMonitoringConfig) -> CashSnapshot:
        raise NotImplementedError("Vendor API provider is a read-only integration stub until SDK/API details are available")


class CashMonitoringModule:
    name = "cash_monitoring"

    def __init__(self, api: ApiClient, atm_id: str, logger: logging.Logger) -> None:
        self.api = api
        self.atm_id = atm_id
        self.logger = logger
        self.config: CashMonitoringConfig | None = None
        self.provider: ICashProvider = MockCashProvider()
        self.last_read = 0.0
        self.status = "disabled"

    def configure(self, config: RemoteConfig) -> None:
        self.config = config.cash_monitoring
        provider_name = self.config.provider
        if provider_name == "xfs":
            self.provider = XfsCashProvider()
        elif provider_name == "vendor_api":
            self.provider = VendorApiCashProvider()
        else:
            self.provider = MockCashProvider()
        self.status = "running" if self.config.enabled else "disabled"

    def tick(self, now: float) -> None:
        if self.config is None or not self.config.enabled:
            self.status = "disabled"
            return
        if now - self.last_read < self.config.read_interval_seconds:
            return

        snapshot = self.provider.get_cash_snapshot(self.atm_id, self.config)
        self.api.cash_snapshot(snapshot.to_payload())
        self.last_read = now
        self.status = "running"
