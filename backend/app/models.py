from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(30), default="admin", nullable=False)
    allowed_pages: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    packages: Mapped[list["UpdatePackage"]] = relationship(back_populates="created_by")


class ATM(Base):
    __tablename__ = "atms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    atm_id: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    vpn_ip: Mapped[str] = mapped_column(String(80), nullable=False)
    branch: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="offline", nullable=False)
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_image_version: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    api_key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    last_heartbeat_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    current_package_version: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    agent_version: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    media_path: Mapped[str] = mapped_column(String(500), default="C:\\ATM\\Media", nullable=False)
    backup_path: Mapped[str] = mapped_column(String(500), default="C:\\ATM\\Media_Backup", nullable=False)
    temp_path: Mapped[str] = mapped_column(String(500), default="C:\\ATM\\Temp", nullable=False)
    config_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    config_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    applied_config_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_config_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_config_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    heartbeat_interval_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    config_sync_interval_seconds: Mapped[int] = mapped_column(Integer, default=120, nullable=False)
    check_interval_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    media_update_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    cash_monitoring_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    module_status_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    cash_provider: Mapped[str] = mapped_column(String(40), default="xfs_cdm", nullable=False)
    xfs_profile: Mapped[str] = mapped_column(String(40), default="ncr_aptra", nullable=False)
    xfs_logical_service: Mapped[str] = mapped_column(String(120), default="MediaDispenser1", nullable=False)
    xfs_msxfs_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    xfs_version_range: Mapped[str] = mapped_column(String(20), default="0x00031E03", nullable=False)
    atm_cash_mode: Mapped[str] = mapped_column(String(40), default="DISPENSE_ONLY", nullable=False)
    cash_layout_json: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    cash_read_interval_seconds: Mapped[int] = mapped_column(Integer, default=120, nullable=False)
    cash_low_threshold_default: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    cash_critical_threshold_default: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    cash_stale_after_minutes: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    switch_probe_host: Mapped[str] = mapped_column(String(120), default="172.16.25.75", nullable=False)
    switch_probe_port: Mapped[int] = mapped_column(Integer, default=10200, nullable=False)
    switch_probe_interval_seconds: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    last_switch_probe_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    last_switch_probe_latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_switch_probe_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_switch_probe_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    targets: Mapped[list["UpdateTarget"]] = relationship(back_populates="atm")
    logs: Mapped[list["AgentLog"]] = relationship(back_populates="atm")
    results: Mapped[list["UpdateResult"]] = relationship(back_populates="atm")
    commands: Mapped[list["AgentCommand"]] = relationship(back_populates="atm")
    agent_configs: Mapped[list["AtmAgentConfig"]] = relationship(back_populates="atm")
    cash_units: Mapped[list["AtmCashUnit"]] = relationship(back_populates="atm")
    cash_snapshots: Mapped[list["AtmCashSnapshot"]] = relationship(back_populates="atm")
    cash_alerts: Mapped[list["AtmCashAlert"]] = relationship(back_populates="atm")
    cash_thresholds: Mapped[list["AtmCashThreshold"]] = relationship(back_populates="atm")
    reject_retract_statuses: Mapped[list["AtmRejectRetractStatus"]] = relationship(back_populates="atm")
    switch_probes: Mapped[list["AtmSwitchProbe"]] = relationship(back_populates="atm")

    @property
    def seconds_since_last_seen(self) -> int | None:
        last_heartbeat = self.last_heartbeat_at or self.last_seen
        if not last_heartbeat:
            return None
        last_seen = last_heartbeat
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        return max(0, int((datetime.now(timezone.utc) - last_seen).total_seconds()))

    @property
    def is_online(self) -> bool:
        if self.seconds_since_last_seen is None:
            return False
        return self.seconds_since_last_seen <= 300

    @property
    def active_update_count(self) -> int:
        return sum(1 for target in self.targets if target.status in {"pending", "downloading"})

    @property
    def last_agent_error(self) -> str | None:
        errors = [log for log in self.logs if log.level in {"error", "warning"}]
        if not errors:
            return None
        latest = max(errors, key=lambda log: log.created_at)
        return latest.message

    @property
    def last_agent_error_at(self) -> datetime | None:
        errors = [log for log in self.logs if log.level in {"error", "warning"}]
        if not errors:
            return None
        latest = max(errors, key=lambda log: log.created_at)
        return latest.created_at

    @property
    def pending_reboot_count(self) -> int:
        return sum(1 for command in self.commands if command.command_type == "reboot" and command.status == "pending")

    @property
    def last_reboot_status(self) -> str | None:
        reboots = [command for command in self.commands if command.command_type == "reboot"]
        if not reboots:
            return None
        latest = max(reboots, key=lambda command: command.created_at)
        return latest.status

    @property
    def last_reboot_requested_at(self) -> datetime | None:
        reboots = [command for command in self.commands if command.command_type == "reboot"]
        if not reboots:
            return None
        latest = max(reboots, key=lambda command: command.created_at)
        return latest.created_at


class UpdatePackage(Base):
    __tablename__ = "update_packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    version: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    created_by: Mapped[Optional[User]] = relationship(back_populates="packages")
    targets: Mapped[list["UpdateTarget"]] = relationship(back_populates="package")
    results: Mapped[list["UpdateResult"]] = relationship(back_populates="package")


class UpdateTarget(Base):
    __tablename__ = "update_targets"
    __table_args__ = (UniqueConstraint("package_id", "atm_id", name="uq_update_target_package_atm"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("update_packages.id"), nullable=False)
    atm_id: Mapped[int] = mapped_column(ForeignKey("atms.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    progress_phase: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    progress_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bytes_downloaded: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_progress_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    package: Mapped[UpdatePackage] = relationship(back_populates="targets")
    atm: Mapped[ATM] = relationship(back_populates="targets")


class AgentLog(Base):
    __tablename__ = "agent_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    atm_id: Mapped[Optional[int]] = mapped_column(ForeignKey("atms.id"), nullable=True)
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    atm: Mapped[Optional[ATM]] = relationship(back_populates="logs")


class AtmAgentConfig(Base):
    __tablename__ = "atm_agent_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    atm_id: Mapped[int] = mapped_column(ForeignKey("atms.id"), nullable=False)
    config_version: Mapped[int] = mapped_column(Integer, nullable=False)
    heartbeat_interval_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    config_sync_interval_seconds: Mapped[int] = mapped_column(Integer, default=120, nullable=False)
    media_update_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    media_path: Mapped[str] = mapped_column(String(500), nullable=False)
    backup_path: Mapped[str] = mapped_column(String(500), nullable=False)
    temp_path: Mapped[str] = mapped_column(String(500), nullable=False)
    media_check_interval_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    cash_monitoring_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cash_provider: Mapped[str] = mapped_column(String(40), default="xfs_cdm", nullable=False)
    xfs_profile: Mapped[str] = mapped_column(String(40), default="ncr_aptra", nullable=False)
    xfs_logical_service: Mapped[str] = mapped_column(String(120), default="MediaDispenser1", nullable=False)
    xfs_msxfs_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    xfs_version_range: Mapped[str] = mapped_column(String(20), default="0x00031E03", nullable=False)
    atm_cash_mode: Mapped[str] = mapped_column(String(40), default="DISPENSE_ONLY", nullable=False)
    cash_layout_json: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    cash_read_interval_seconds: Mapped[int] = mapped_column(Integer, default=120, nullable=False)
    cash_stale_after_minutes: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    switch_probe_interval_seconds: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    updated_by: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    atm: Mapped[ATM] = relationship(back_populates="agent_configs")


class AtmCashUnit(Base):
    __tablename__ = "atm_cash_units"
    __table_args__ = (UniqueConstraint("atm_id", "unit_no", name="uq_cash_unit_atm_unit"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    atm_id: Mapped[int] = mapped_column(ForeignKey("atms.id"), nullable=False)
    unit_no: Mapped[int] = mapped_column(Integer, nullable=False)
    cassette_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    cassette_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    cassette_name: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    expected_currency: Mapped[str] = mapped_column(String(10), default="YER", nullable=False)
    expected_denomination: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    reported_currency: Mapped[str] = mapped_column(String(10), default="YER", nullable=False)
    reported_denomination: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="YER", nullable=False)
    denomination: Mapped[int] = mapped_column(Integer, nullable=False)
    initial_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reject_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retract_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    dispensed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    presented_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retracted_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    min_threshold: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    low_threshold: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    critical_threshold: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    max_capacity: Mapped[int] = mapped_column(Integer, default=2000, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="OK", nullable=False)
    physical_status: Mapped[str] = mapped_column(String(40), default="PRESENT", nullable=False)
    layout_match_status: Mapped[str] = mapped_column(String(40), default="MATCH", nullable=False)
    source: Mapped[str] = mapped_column(String(40), default="xfs_cdm", nullable=False)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    atm: Mapped[ATM] = relationship(back_populates="cash_units")


class AtmRejectRetractStatus(Base):
    __tablename__ = "atm_reject_retract_status"
    __table_args__ = (UniqueConstraint("atm_id", name="uq_reject_retract_atm"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    atm_id: Mapped[int] = mapped_column(ForeignKey("atms.id"), nullable=False)
    reject_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retract_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reject_status: Mapped[str] = mapped_column(String(30), default="OK", nullable=False)
    retract_status: Mapped[str] = mapped_column(String(30), default="OK", nullable=False)
    reject_max_capacity: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    retract_max_capacity: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    atm: Mapped[ATM] = relationship(back_populates="reject_retract_statuses")


class AtmCashSnapshot(Base):
    __tablename__ = "atm_cash_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    atm_id: Mapped[int] = mapped_column(ForeignKey("atms.id"), nullable=False)
    snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    source: Mapped[str] = mapped_column(String(40), default="xfs_cdm", nullable=False)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    atm: Mapped[ATM] = relationship(back_populates="cash_snapshots")


class AtmCashAlert(Base):
    __tablename__ = "atm_cash_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    atm_id: Mapped[int] = mapped_column(ForeignKey("atms.id"), nullable=False)
    unit_no: Mapped[int] = mapped_column(Integer, nullable=False)
    alert_type: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    current_count: Mapped[int] = mapped_column(Integer, nullable=False)
    threshold_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    atm: Mapped[ATM] = relationship(back_populates="cash_alerts")


class NotificationSettings(Base):
    __tablename__ = "notification_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    recipient_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sender_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    smtp_host: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    smtp_port: Mapped[int] = mapped_column(Integer, default=587, nullable=False)
    smtp_security: Mapped[str] = mapped_column(String(20), default="starttls", nullable=False)
    smtp_username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    smtp_password: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    whatsapp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    whatsapp_gateway_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    whatsapp_gateway_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    whatsapp_default_recipient: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    notify_cash_low: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_cash_empty: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_switch_disconnected: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_by: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    @property
    def has_smtp_password(self) -> bool:
        return bool(self.smtp_password)

    @property
    def has_whatsapp_gateway_token(self) -> bool:
        return bool(self.whatsapp_gateway_token)

    @property
    def is_configured(self) -> bool:
        return bool(self.sender_email and self.smtp_host and self.smtp_port)

    @property
    def is_whatsapp_configured(self) -> bool:
        return bool(self.whatsapp_enabled and self.whatsapp_gateway_url)


class NotificationRecipient(Base):
    __tablename__ = "notification_recipients"
    __table_args__ = (UniqueConstraint("atm_id", name="uq_notification_recipient_atm"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    atm_id: Mapped[int] = mapped_column(ForeignKey("atms.id"), nullable=False)
    recipient_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    whatsapp_number: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_by: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    alert_id: Mapped[Optional[int]] = mapped_column(ForeignKey("atm_cash_alerts.id"), nullable=True)
    atm_id: Mapped[Optional[int]] = mapped_column(ForeignKey("atms.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    channel: Mapped[str] = mapped_column(String(30), default="email", nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class AtmCashThreshold(Base):
    __tablename__ = "atm_cash_thresholds"
    __table_args__ = (UniqueConstraint("atm_id", "denomination", name="uq_cash_threshold_atm_denomination"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    atm_id: Mapped[int] = mapped_column(ForeignKey("atms.id"), nullable=False)
    denomination: Mapped[int] = mapped_column(Integer, nullable=False)
    low_threshold_count: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    critical_threshold_count: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    max_capacity: Mapped[int] = mapped_column(Integer, default=2000, nullable=False)
    updated_by: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    atm: Mapped[ATM] = relationship(back_populates="cash_thresholds")


class AtmSwitchProbe(Base):
    __tablename__ = "atm_switch_probes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    atm_id: Mapped[int] = mapped_column(ForeignKey("atms.id"), nullable=False)
    host: Mapped[str] = mapped_column(String(120), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    requested_by: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    atm: Mapped[ATM] = relationship(back_populates="switch_probes")


class UpdateResult(Base):
    __tablename__ = "update_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    atm_id: Mapped[int] = mapped_column(ForeignKey("atms.id"), nullable=False)
    package_id: Mapped[int] = mapped_column(ForeignKey("update_packages.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    atm: Mapped[ATM] = relationship(back_populates="results")
    package: Mapped[UpdatePackage] = relationship(back_populates="results")


class AgentCommand(Base):
    __tablename__ = "agent_commands"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    atm_id: Mapped[int] = mapped_column(ForeignKey("atms.id"), nullable=False)
    command_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    requested_by: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    atm: Mapped[ATM] = relationship(back_populates="commands")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    actor_type: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
