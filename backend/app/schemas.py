from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .page_permissions import ALL_PAGE_IDS

UserRole = Literal["admin", "system_admin", "operator", "media_admin", "cash_monitoring_viewer", "cash_monitoring_admin"]


PATH_FIELDS = {"media_path", "backup_path", "temp_path"}
ALLOWED_CURRENCIES = {"YER", "USD", "SAR"}
ALLOWED_DENOMINATIONS = {"YER": {1000}, "USD": {100}, "SAR": {100}}
CASH_MODE_DISPENSE_ONLY = "DISPENSE_ONLY"
CashDispenseProvider = Literal["xfs_cdm", "vendor_cdm"]
CashSnapshotSource = Literal["xfs_cdm", "vendor_cdm"]
XfsProfile = Literal["ncr_aptra", "grg", "custom"]
SmtpSecurity = Literal["starttls", "ssl", "none"]


def validate_email_like(value: str | None) -> str | None:
    if value is None:
        return value
    cleaned = value.strip()
    if not cleaned:
        return None
    if any(char.isspace() for char in cleaned) or "@" not in cleaned:
        raise ValueError("Enter a valid email address")
    local, _, domain = cleaned.rpartition("@")
    if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise ValueError("Enter a valid email address")
    return cleaned


def validate_atm_managed_path(value: str | None) -> str | None:
    if value is None:
        return value
    cleaned = value.strip()
    normalized = cleaned.replace("/", "\\")
    upper = normalized.upper()
    if not upper.startswith("C:\\ATM\\"):
        raise ValueError("Path must be under C:\\ATM\\")
    if ".." in normalized.split("\\"):
        raise ValueError("Path must not contain '..'")
    return cleaned


def validate_probe_host(value: str | None) -> str | None:
    if value is None:
        return value
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Switch host is required")
    if any(char.isspace() for char in cleaned):
        raise ValueError("Switch host must not contain spaces")
    if "/" in cleaned or "\\" in cleaned or ":" in cleaned:
        raise ValueError("Switch host must be a hostname or IP address only")
    return cleaned


def validate_xfs_logical_service(value: str | None) -> str | None:
    if value is None:
        return value
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("XFS Logical Service is required")
    if any(ord(char) < 32 for char in cleaned):
        raise ValueError("XFS Logical Service must not contain control characters")
    if any(char in cleaned for char in "\\/:;|&<>`$"):
        raise ValueError("XFS Logical Service must be a service name, not a path or command")
    return cleaned


def validate_xfs_msxfs_path(value: str | None) -> str | None:
    if value is None:
        return value
    cleaned = value.strip()
    if not cleaned:
        return None
    normalized = cleaned.replace("/", "\\").lower()
    if not normalized.endswith("\\msxfs.dll") and normalized != "msxfs.dll":
        raise ValueError("XFS msxfs path must point to msxfs.dll")
    if any(char in cleaned for char in "|&<>`$"):
        raise ValueError("XFS msxfs path contains unsupported characters")
    return cleaned


def validate_xfs_version_range(value: str | None) -> str | None:
    if value is None:
        return value
    cleaned = value.strip()
    if not cleaned:
        return "0x00031E03"
    try:
        int(cleaned, 0)
    except ValueError as exc:
        raise ValueError("XFS Version Range must be a number such as 0x00031E03") from exc
    return cleaned


class CashLayoutItem(BaseModel):
    cassette_no: int = Field(ge=1, le=12)
    currency: Literal["YER", "USD", "SAR"]
    denomination: int = Field(ge=1)
    max_capacity: int = Field(default=2000, ge=1, le=100000)
    low_threshold: int = Field(default=300, ge=0, le=100000)
    critical_threshold: int = Field(default=100, ge=0, le=100000)

    @field_validator("denomination")
    @classmethod
    def validate_denomination(cls, value: int, info) -> int:
        currency = info.data.get("currency")
        if currency and value not in ALLOWED_DENOMINATIONS[currency]:
            raise ValueError(f"Unsupported denomination for {currency}")
        return value


def validate_cash_layout_items(value: list[CashLayoutItem] | None) -> list[CashLayoutItem] | None:
    if value is None:
        return value
    cassette_numbers = [item.cassette_no for item in value]
    if len(cassette_numbers) != len(set(cassette_numbers)):
        raise ValueError("Duplicate cassette_no is not allowed in the same ATM layout")
    return value


class LoginRequest(BaseModel):
    username: str
    password: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str
    allowed_pages: list[str] = Field(default_factory=list)
    is_active: bool = True


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=8, max_length=200)
    role: UserRole = "operator"
    allowed_pages: list[str] = Field(default_factory=list)
    is_active: bool = True

    @field_validator("allowed_pages")
    @classmethod
    def validate_allowed_pages(cls, value: list[str]) -> list[str]:
        unknown = [page for page in value if page not in ALL_PAGE_IDS]
        if unknown:
            raise ValueError(f"Unknown page ids: {', '.join(unknown)}")
        return value


class UserUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=2, max_length=80)
    password: str | None = Field(default=None, min_length=8, max_length=200)
    role: UserRole | None = None
    allowed_pages: list[str] | None = None
    is_active: bool | None = None

    @field_validator("allowed_pages")
    @classmethod
    def validate_allowed_pages(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        unknown = [page for page in value if page not in ALL_PAGE_IDS]
        if unknown:
            raise ValueError(f"Unknown page ids: {', '.join(unknown)}")
        return value


class PagePermissionRead(BaseModel):
    id: str
    label: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class ATMBase(BaseModel):
    atm_id: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=2, max_length=160)
    vpn_ip: str = Field(min_length=3, max_length=80)
    branch: str = Field(min_length=2, max_length=160)


class ATMCreate(ATMBase):
    media_path: str | None = Field(default=None, max_length=500)
    backup_path: str | None = Field(default=None, max_length=500)
    temp_path: str | None = Field(default=None, max_length=500)
    check_interval_seconds: int | None = Field(default=None, ge=30, le=86400)
    heartbeat_interval_seconds: int | None = Field(default=None, ge=10, le=3600)
    config_sync_interval_seconds: int | None = Field(default=None, ge=30, le=86400)
    media_update_enabled: bool | None = None
    cash_monitoring_enabled: bool | None = None
    atm_cash_mode: Literal["DISPENSE_ONLY"] | None = None
    cash_provider: CashDispenseProvider | None = None
    xfs_profile: XfsProfile | None = None
    xfs_logical_service: str | None = Field(default=None, min_length=1, max_length=120)
    xfs_msxfs_path: str | None = Field(default=None, max_length=500)
    xfs_version_range: str | None = Field(default=None, max_length=20)
    cash_layout: list[CashLayoutItem] | None = None
    cash_read_interval_seconds: int | None = Field(default=None, ge=30, le=86400)
    cash_low_threshold_default: int | None = Field(default=None, ge=0, le=100000)
    cash_critical_threshold_default: int | None = Field(default=None, ge=0, le=100000)
    cash_stale_after_minutes: int | None = Field(default=None, ge=1, le=1440)
    switch_probe_host: str | None = Field(default=None, min_length=1, max_length=120)
    switch_probe_port: int | None = Field(default=None, ge=1, le=65535)
    switch_probe_interval_seconds: int | None = Field(default=None, ge=30, le=86400)

    @field_validator("media_path", "backup_path", "temp_path")
    @classmethod
    def validate_paths(cls, value: str | None) -> str | None:
        return validate_atm_managed_path(value)

    @field_validator("cash_layout")
    @classmethod
    def validate_cash_layout(cls, value: list[CashLayoutItem] | None) -> list[CashLayoutItem] | None:
        return validate_cash_layout_items(value)

    @field_validator("switch_probe_host")
    @classmethod
    def validate_switch_probe_host(cls, value: str | None) -> str | None:
        return validate_probe_host(value)

    @field_validator("xfs_logical_service")
    @classmethod
    def validate_xfs_service(cls, value: str | None) -> str | None:
        return validate_xfs_logical_service(value)

    @field_validator("xfs_msxfs_path")
    @classmethod
    def validate_xfs_dll_path(cls, value: str | None) -> str | None:
        return validate_xfs_msxfs_path(value)

    @field_validator("xfs_version_range")
    @classmethod
    def validate_xfs_range(cls, value: str | None) -> str | None:
        return validate_xfs_version_range(value)

    @model_validator(mode="after")
    def validate_real_cash_provider(self):
        if self.cash_monitoring_enabled and self.cash_provider == "vendor_cdm":
            raise ValueError("Vendor CDM provider is not available yet. Use XFS CDM Provider for real ATMs.")
        return self


class ATMUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    vpn_ip: str | None = Field(default=None, min_length=3, max_length=80)
    branch: str | None = Field(default=None, min_length=2, max_length=160)
    status: str | None = None
    last_image_version: str | None = None
    media_path: str | None = Field(default=None, min_length=3, max_length=500)
    backup_path: str | None = Field(default=None, min_length=3, max_length=500)
    temp_path: str | None = Field(default=None, min_length=3, max_length=500)
    check_interval_seconds: int | None = Field(default=None, ge=30, le=86400)
    heartbeat_interval_seconds: int | None = Field(default=None, ge=10, le=3600)
    config_sync_interval_seconds: int | None = Field(default=None, ge=30, le=86400)
    media_update_enabled: bool | None = None
    cash_monitoring_enabled: bool | None = None
    atm_cash_mode: Literal["DISPENSE_ONLY"] | None = None
    cash_provider: CashDispenseProvider | None = None
    xfs_profile: XfsProfile | None = None
    xfs_logical_service: str | None = Field(default=None, min_length=1, max_length=120)
    xfs_msxfs_path: str | None = Field(default=None, max_length=500)
    xfs_version_range: str | None = Field(default=None, max_length=20)
    cash_layout: list[CashLayoutItem] | None = None
    cash_read_interval_seconds: int | None = Field(default=None, ge=30, le=86400)
    cash_low_threshold_default: int | None = Field(default=None, ge=0, le=100000)
    cash_critical_threshold_default: int | None = Field(default=None, ge=0, le=100000)
    cash_stale_after_minutes: int | None = Field(default=None, ge=1, le=1440)
    switch_probe_host: str | None = Field(default=None, min_length=1, max_length=120)
    switch_probe_port: int | None = Field(default=None, ge=1, le=65535)
    switch_probe_interval_seconds: int | None = Field(default=None, ge=30, le=86400)

    @field_validator("media_path", "backup_path", "temp_path")
    @classmethod
    def validate_paths(cls, value: str | None) -> str | None:
        return validate_atm_managed_path(value)

    @field_validator("cash_layout")
    @classmethod
    def validate_cash_layout(cls, value: list[CashLayoutItem] | None) -> list[CashLayoutItem] | None:
        return validate_cash_layout_items(value)

    @field_validator("switch_probe_host")
    @classmethod
    def validate_switch_probe_host(cls, value: str | None) -> str | None:
        return validate_probe_host(value)

    @field_validator("xfs_logical_service")
    @classmethod
    def validate_xfs_service(cls, value: str | None) -> str | None:
        return validate_xfs_logical_service(value)

    @field_validator("xfs_msxfs_path")
    @classmethod
    def validate_xfs_dll_path(cls, value: str | None) -> str | None:
        return validate_xfs_msxfs_path(value)

    @field_validator("xfs_version_range")
    @classmethod
    def validate_xfs_range(cls, value: str | None) -> str | None:
        return validate_xfs_version_range(value)

    @model_validator(mode="after")
    def validate_real_cash_provider(self):
        if self.cash_monitoring_enabled and self.cash_provider == "vendor_cdm":
            raise ValueError("Vendor CDM provider is not available yet. Use XFS CDM Provider for real ATMs.")
        return self


class ATMRead(ATMBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    last_seen: datetime | None
    last_image_version: str | None
    last_heartbeat_at: datetime | None = None
    current_package_version: str | None = None
    agent_version: str | None = None
    latency_ms: int | None = None
    media_path: str
    backup_path: str
    temp_path: str
    config_version: int
    config_updated_at: datetime | None = None
    applied_config_version: int
    last_config_sync_at: datetime | None = None
    last_config_error: str | None = None
    heartbeat_interval_seconds: int
    config_sync_interval_seconds: int
    check_interval_seconds: int
    media_update_enabled: bool
    cash_monitoring_enabled: bool
    module_status_json: dict[str, Any] = Field(default_factory=dict)
    atm_cash_mode: str
    cash_provider: str
    xfs_profile: str
    xfs_logical_service: str
    xfs_msxfs_path: str | None = None
    xfs_version_range: str = "0x00031E03"
    cash_layout_json: list[dict[str, Any]] = Field(default_factory=list)
    cash_read_interval_seconds: int
    cash_low_threshold_default: int
    cash_critical_threshold_default: int
    cash_stale_after_minutes: int
    switch_probe_host: str
    switch_probe_port: int
    switch_probe_interval_seconds: int
    last_switch_probe_status: str | None = None
    last_switch_probe_latency_ms: int | None = None
    last_switch_probe_error: str | None = None
    last_switch_probe_at: datetime | None = None
    seconds_since_last_seen: int | None = None
    is_online: bool = False
    active_update_count: int = 0
    last_agent_error: str | None = None
    last_agent_error_at: datetime | None = None
    pending_reboot_count: int = 0
    last_reboot_status: str | None = None
    last_reboot_requested_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ATMCreateResponse(BaseModel):
    atm: ATMRead
    api_key: str


class PackageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version: str
    original_filename: str
    sha256: str
    size_bytes: int
    notes: str | None
    created_at: datetime


class PackageSummary(PackageRead):
    total_targets: int = 0
    pending_targets: int = 0
    applied_targets: int = 0
    failed_targets: int = 0


class UpdateTargetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    assigned_at: datetime
    last_checked_at: datetime | None
    completed_at: datetime | None
    last_error: str | None
    attempt_count: int
    progress_percent: int = 0
    progress_phase: str = "pending"
    progress_message: str | None = None
    bytes_downloaded: int | None = None
    total_bytes: int | None = None
    last_progress_at: datetime | None = None
    atm: ATMRead


class PackageDetails(PackageRead):
    targets: list[UpdateTargetRead]


class PackageAssignRequest(BaseModel):
    atm_ids: list[str] = Field(default_factory=list, min_length=1)


class PackageAssignResponse(BaseModel):
    package_id: int
    assigned: int
    targets: list[UpdateTargetRead]


class ATMRebootRequest(BaseModel):
    confirmation: Literal["REBOOT"]
    reason: str | None = Field(default=None, max_length=300)
    delay_seconds: int = Field(default=60, ge=30, le=3600)


class AgentCommandRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    atm_id: int
    command_type: str
    status: str
    payload: dict[str, Any] | None = None
    requested_by: str | None = None
    last_error: str | None = None
    created_at: datetime
    acknowledged_at: datetime | None = None
    completed_at: datetime | None = None


class SwitchProbeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    atm_id: int
    host: str
    port: int
    status: str
    requested_by: str | None = None
    requested_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    latency_ms: int | None = None
    error_message: str | None = None


class SwitchProbeRequest(BaseModel):
    host: str | None = Field(default=None, min_length=1, max_length=120)
    port: int | None = Field(default=None, ge=1, le=65535)

    @field_validator("host")
    @classmethod
    def validate_host(cls, value: str | None) -> str | None:
        return validate_probe_host(value)


class AgentSwitchProbeRequest(BaseModel):
    has_probe: bool
    probe: SwitchProbeRead | None = None
    timeout_seconds: int = 5


class AgentSwitchProbeResult(BaseModel):
    probe_id: int
    status: Literal["success", "failed"]
    latency_ms: int | None = Field(default=None, ge=0, le=600000)
    error_message: str | None = Field(default=None, max_length=1000)


class AgentSwitchProbeSnapshot(BaseModel):
    status: Literal["success", "failed"]
    latency_ms: int | None = Field(default=None, ge=0, le=600000)
    error_message: str | None = Field(default=None, max_length=1000)
    host: str | None = Field(default=None, min_length=1, max_length=120)
    port: int | None = Field(default=None, ge=1, le=65535)

    @field_validator("host")
    @classmethod
    def validate_host(cls, value: str | None) -> str | None:
        return validate_probe_host(value)


class HeartbeatRequest(BaseModel):
    atm_id: str | None = None
    status: str = "online"
    current_version: str | None = None
    current_package_version: str | None = None
    agent_version: str | None = None
    service_status: str | None = None
    applied_config_version: int | None = None
    latency_ms: int | None = Field(default=None, ge=0, le=600000)
    enabled_modules: list[str] = Field(default_factory=list)
    module_statuses: dict[str, str] = Field(default_factory=dict)


class HeartbeatResponse(BaseModel):
    ok: bool = True
    pending_updates: int


class AgentUpdateAvailable(BaseModel):
    update_available: Literal[True]
    has_update: Literal[True] = True
    package_id: int
    version: str
    sha256: str
    size_bytes: int
    download_url: str


class AgentNoUpdate(BaseModel):
    update_available: Literal[False]
    has_update: Literal[False] = False


class UpdateResultRequest(BaseModel):
    atm_id: str | None = None
    package_id: int
    version: str | None = None
    status: Literal["success", "failed"]
    message: str | None = None
    rollback_done: bool | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class AgentProgressRequest(BaseModel):
    package_id: int
    phase: Literal["pending", "downloading", "applying", "rollback", "applied", "failed"]
    progress_percent: int = Field(ge=0, le=100)
    message: str | None = Field(default=None, max_length=500)
    bytes_downloaded: int | None = Field(default=None, ge=0)
    total_bytes: int | None = Field(default=None, ge=0)


class AgentLogRequest(BaseModel):
    atm_id: str | None = None
    level: Literal["debug", "info", "warning", "error"]
    message: str = Field(min_length=1)
    context: dict[str, Any] | None = None
    details: str | dict[str, Any] | None = None


class MediaUpdateRemoteConfig(BaseModel):
    enabled: bool
    media_path: str
    backup_path: str
    temp_path: str
    check_interval_seconds: int
    allowed_extensions: list[str]


class CashMonitoringRemoteConfig(BaseModel):
    enabled: bool
    atm_cash_mode: Literal["DISPENSE_ONLY"] = "DISPENSE_ONLY"
    provider: CashDispenseProvider = "xfs_cdm"
    xfs_profile: XfsProfile = "ncr_aptra"
    xfs_logical_service: str = "MediaDispenser1"
    xfs_msxfs_path: str | None = None
    xfs_version_range: str = "0x00031E03"
    read_interval_seconds: int
    cash_layout: list[CashLayoutItem] = Field(default_factory=list)
    stale_after_minutes: int


class AgentModulesConfig(BaseModel):
    media_update: MediaUpdateRemoteConfig
    cash_monitoring: CashMonitoringRemoteConfig


class AgentConfigResponse(BaseModel):
    atm_id: str
    config_version: int
    config_sync_interval_seconds: int = 120
    switch_probe_host: str
    switch_probe_port: int
    switch_probe_interval_seconds: int = 30
    modules: AgentModulesConfig
    # Legacy fields kept so older installed agents can continue to run during rollout.
    media_path: str
    backup_path: str
    temp_path: str
    heartbeat_interval_seconds: int
    check_interval_seconds: int
    allowed_extensions: list[str]


class AgentConfigAckRequest(BaseModel):
    atm_id: str | None = None
    applied_config_version: int
    success: bool
    message: str | None = None
    enabled_modules: list[str] = Field(default_factory=list)


class AgentCommandAckRequest(BaseModel):
    status: Literal["acknowledged", "completed", "failed"]
    message: str | None = Field(default=None, max_length=500)


class AgentLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    level: str
    message: str
    context: dict[str, Any] | None
    created_at: datetime
    atm: ATMRead | None = None


class ATMDiagnostics(BaseModel):
    atm_id: str
    is_online: bool
    service_status: str
    reporting_status: Literal["reporting", "not_reporting", "never_reported"]
    severity: Literal["ok", "warning", "critical"]
    summary: str
    recommended_action: str
    last_heartbeat_at: datetime | None = None
    seconds_since_last_seen: int | None = None
    last_agent_error: str | None = None
    last_agent_error_at: datetime | None = None
    last_server_error: str | None = None
    last_server_error_at: datetime | None = None
    last_reboot_command: AgentCommandRead | None = None
    recent_logs: list[AgentLogRead] = Field(default_factory=list)
    recent_commands: list[AgentCommandRead] = Field(default_factory=list)


class AtmEventRead(BaseModel):
    id: str
    occurred_at: datetime
    source: str
    event_type: str
    severity: str = "info"
    title: str
    message: str | None = None
    status: str | None = None
    actor: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_type: str
    actor_id: str | None
    action: str
    entity_type: str
    entity_id: str | None
    details: dict[str, Any] | None
    created_at: datetime


class NotificationSettingsUpdate(BaseModel):
    enabled: bool = False
    recipient_email: str | None = Field(default=None, max_length=255)
    sender_email: str | None = Field(default=None, max_length=255)
    smtp_host: str | None = Field(default=None, max_length=255)
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_security: SmtpSecurity = "starttls"
    smtp_username: str | None = Field(default=None, max_length=255)
    smtp_password: str | None = Field(default=None, max_length=500)
    clear_smtp_password: bool = False
    notify_cash_low: bool = True
    notify_cash_empty: bool = True

    @field_validator("recipient_email", "sender_email")
    @classmethod
    def validate_email_fields(cls, value: str | None) -> str | None:
        return validate_email_like(value)

    @field_validator("smtp_host", "smtp_username", "smtp_password")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        cleaned = value.strip()
        return cleaned or None

    @model_validator(mode="after")
    def validate_enabled_configuration(self):
        if self.enabled and not (self.sender_email and self.smtp_host):
            raise ValueError("Sender email and SMTP host are required when notifications are enabled")
        return self


class NotificationSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    enabled: bool
    recipient_email: str | None
    sender_email: str | None
    smtp_host: str | None
    smtp_port: int
    smtp_security: str
    smtp_username: str | None
    notify_cash_low: bool
    notify_cash_empty: bool
    has_smtp_password: bool = False
    is_configured: bool = False
    updated_by: str | None
    created_at: datetime
    updated_at: datetime


class NotificationDeliveryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    alert_id: int | None
    atm_id: int | None
    event_type: str
    channel: str
    recipient_email: str
    subject: str
    status: str
    error_message: str | None
    created_at: datetime
    sent_at: datetime | None


class NotificationRecipientItemUpdate(BaseModel):
    atm_id: str = Field(min_length=1, max_length=80)
    recipient_email: str | None = Field(default=None, max_length=255)
    enabled: bool = True

    @field_validator("recipient_email")
    @classmethod
    def validate_recipient_email(cls, value: str | None) -> str | None:
        return validate_email_like(value)


class NotificationRecipientsUpdate(BaseModel):
    recipients: list[NotificationRecipientItemUpdate] = Field(default_factory=list)


class NotificationRecipientRead(BaseModel):
    atm_id: str
    name: str
    branch: str
    recipient_email: str | None = None
    effective_recipient_email: str | None = None
    enabled: bool = True
    uses_default: bool = True
    updated_at: datetime | None = None


class RejectRetractPayload(BaseModel):
    reject_count: int = Field(default=0, ge=0)
    retract_count: int = Field(default=0, ge=0)
    reject_status: str = "OK"
    retract_status: str = "OK"
    reject_max_capacity: int = Field(default=100, ge=1)
    retract_max_capacity: int = Field(default=50, ge=1)


class CashUnitPayload(BaseModel):
    cassette_no: int = Field(ge=1, le=12)
    cassette_id: str | None = None
    cassette_name: str | None = None
    reported_currency: str = Field(min_length=1, max_length=10)
    reported_denomination: int = Field(ge=1)
    initial_count: int = Field(default=0, ge=0)
    current_count: int = Field(default=0, ge=0)
    reject_count: int = Field(default=0, ge=0)
    retract_count: int = Field(default=0, ge=0)
    dispensed_count: int = Field(default=0, ge=0)
    presented_count: int = Field(default=0, ge=0)
    status: str = "OK"
    physical_status: str = "PRESENT"

    @field_validator("reported_currency")
    @classmethod
    def normalize_reported_currency(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("Reported currency is required")
        if any(ord(char) < 32 for char in cleaned):
            raise ValueError("Reported currency must not contain control characters")
        return cleaned


class CashSnapshotRequest(BaseModel):
    atm_id: str | None = None
    source: CashSnapshotSource = "xfs_cdm"
    atm_cash_mode: Literal["DISPENSE_ONLY"] = "DISPENSE_ONLY"
    read_at: datetime
    cash_units: list[CashUnitPayload] = Field(default_factory=list)
    reject_retract: RejectRetractPayload = Field(default_factory=RejectRetractPayload)


class CashUnitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    atm_id: int
    cassette_no: int
    cassette_id: str | None
    cassette_name: str | None
    expected_currency: str
    expected_denomination: int
    reported_currency: str
    reported_denomination: int
    initial_count: int
    current_count: int
    reject_count: int
    retract_count: int
    dispensed_count: int
    presented_count: int
    low_threshold: int
    critical_threshold: int
    max_capacity: int
    status: str
    physical_status: str
    layout_match_status: str
    source: str
    read_at: datetime
    updated_at: datetime


class CashAlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    atm_id: int
    unit_no: int
    alert_type: str
    severity: str
    message: str
    current_count: int
    threshold_count: int
    status: str
    opened_at: datetime
    closed_at: datetime | None


class RejectRetractRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reject_count: int
    retract_count: int
    reject_status: str
    retract_status: str
    reject_max_capacity: int
    retract_max_capacity: int
    read_at: datetime
    updated_at: datetime


class CashThresholdCreate(BaseModel):
    atm_id: str
    denomination: int = Field(ge=0)
    low_threshold_count: int = Field(ge=0)
    critical_threshold_count: int = Field(ge=0)
    max_capacity: int = Field(default=2000, ge=0)


class CashThresholdUpdate(BaseModel):
    low_threshold_count: int | None = Field(default=None, ge=0)
    critical_threshold_count: int | None = Field(default=None, ge=0)
    max_capacity: int | None = Field(default=None, ge=0)


class CashThresholdRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    atm_id: int
    denomination: int
    low_threshold_count: int
    critical_threshold_count: int
    max_capacity: int
    updated_by: str | None
    updated_at: datetime


class CashForecastRead(BaseModel):
    atm_id: str
    atm_name: str
    branch: str
    cassette_no: int
    currency: str
    denomination: int
    current_count: int
    low_threshold: int
    critical_threshold: int
    notes_per_day: float | None = None
    days_to_low: float | None = None
    days_to_empty: float | None = None
    risk: str
    last_read_at: datetime | None = None
    sample_count: int = 0


class CashVerificationIssue(BaseModel):
    cassette_no: int | None = None
    code: str
    severity: str
    message: str
    expected: str | None = None
    reported: str | None = None


class CashVerificationSummary(BaseModel):
    status: str
    matched: bool
    checked_at: datetime | None = None
    total_units: int = 0
    matched_units: int = 0
    mismatch_count: int = 0
    warning_count: int = 0
    issues: list[CashVerificationIssue] = Field(default_factory=list)


class CashAtmDetails(BaseModel):
    atm: ATMRead
    units: list[CashUnitRead]
    reject_retract: RejectRetractRead | None = None
    alerts: list[CashAlertRead]
    thresholds: list[CashThresholdRead]
    forecasts: list[CashForecastRead] = Field(default_factory=list)
    verification: CashVerificationSummary
    last_cash_read_command: AgentCommandRead | None = None


class CashLowAtmRead(BaseModel):
    atm_id: str
    name: str
    branch: str
    cassette_no: int
    currency: str
    denomination: int
    current_count: int
    threshold_count: int
    status: str
    read_at: datetime | None = None


class CashSummary(BaseModel):
    atm_count: int
    cash_low_atms: int
    cash_critical_atms: int
    cash_empty_atms: int
    cash_stale_atms: int
    open_alerts: int
    units: list[CashUnitRead]
    low_cash_atms: list[CashLowAtmRead] = Field(default_factory=list)
    empty_cash_atms: list[CashLowAtmRead] = Field(default_factory=list)


class CashAtmReportRead(BaseModel):
    atm_id: str
    name: str
    branch: str
    is_stale: bool
    last_read_at: datetime | None = None
    totals_by_currency: dict[str, int] = Field(default_factory=dict)
    total_note_count: int = 0
    lowest_cassette_no: int | None = None
    lowest_current_count: int | None = None
    open_alert_count: int = 0
    highest_risk: str = "UNKNOWN"
    forecast_days_to_empty: float | None = None


class CashReportOverview(BaseModel):
    generated_at: datetime
    atms: list[CashAtmReportRead]
    forecast_risks: list[CashForecastRead]
