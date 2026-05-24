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
    check_interval_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    targets: Mapped[list["UpdateTarget"]] = relationship(back_populates="atm")
    logs: Mapped[list["AgentLog"]] = relationship(back_populates="atm")
    results: Mapped[list["UpdateResult"]] = relationship(back_populates="atm")
    commands: Mapped[list["AgentCommand"]] = relationship(back_populates="atm")

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
