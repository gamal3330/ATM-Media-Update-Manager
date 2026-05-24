from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .page_permissions import ALL_PAGE_IDS


PATH_FIELDS = {"media_path", "backup_path", "temp_path"}


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
    role: Literal["admin", "operator"] = "operator"
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
    role: Literal["admin", "operator"] | None = None
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

    @field_validator("media_path", "backup_path", "temp_path")
    @classmethod
    def validate_paths(cls, value: str | None) -> str | None:
        return validate_atm_managed_path(value)


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

    @field_validator("media_path", "backup_path", "temp_path")
    @classmethod
    def validate_paths(cls, value: str | None) -> str | None:
        return validate_atm_managed_path(value)


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
    check_interval_seconds: int
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


class HeartbeatRequest(BaseModel):
    atm_id: str | None = None
    status: str = "online"
    current_version: str | None = None
    current_package_version: str | None = None
    agent_version: str | None = None
    service_status: str | None = None
    applied_config_version: int | None = None
    latency_ms: int | None = Field(default=None, ge=0, le=600000)


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


class AgentConfigResponse(BaseModel):
    atm_id: str
    config_version: int
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
