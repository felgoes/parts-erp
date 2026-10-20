from datetime import datetime
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    model_validator,
)

from app.models import UserRole
from app.schemas.base import ORMModel, UtcModel

NotificationSound = Literal["system", "bell", "chime", "soft", "kaching", "silent"]


class ErpSettingsOut(BaseModel):
    company_name: str
    company_short_name: str
    logo_data_url: str | None
    backup_enabled: bool
    backup_frequency: Literal["daily", "weekly"]
    backup_time: str
    backup_retention_days: int
    backup_destination: Literal["google_drive"]
    backup_ready: bool = False
    backup_status: str = "setup_required"
    drive_client_id: str | None = None
    drive_client_secret_configured: bool = False
    drive_folder_id: str | None = None
    drive_connected: bool = False
    backup_last_at: datetime | None = None
    backup_last_status: str = "setup_required"
    backup_last_error: str | None = None
    backup_last_success_at: datetime | None = None
    backup_last_attempt_at: datetime | None = None
    backup_next_run_at: datetime | None = None
    backup_state: str = "setup_required"
    backup_last_error_code: str | None = None
    backup_local_dir: str | None = None


class ErpSettingsUpdate(BaseModel):
    company_name: str = Field(min_length=2, max_length=120)
    company_short_name: str = Field(min_length=1, max_length=40)
    logo_data_url: str | None = Field(default=None, max_length=3_000_000)
    backup_enabled: bool = False
    backup_frequency: Literal["daily", "weekly"] = "daily"
    backup_time: str = Field(default="02:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    backup_retention_days: int = Field(default=30, ge=1, le=30)
    backup_destination: Literal["google_drive"] = "google_drive"
    drive_client_id: str | None = Field(default=None, max_length=255)
    drive_client_secret: str | None = Field(default=None, max_length=4096)
    drive_folder_id: str | None = Field(default=None, max_length=255)

    @model_validator(mode="before")
    @classmethod
    def restore_default_brand_when_empty(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        if not str(normalized.get("company_name") or "").strip():
            normalized["company_name"] = "Parts ERP"
        if not str(normalized.get("company_short_name") or "").strip():
            normalized["company_short_name"] = "Parts"
        if not str(normalized.get("logo_data_url") or "").strip():
            normalized["logo_data_url"] = None
        return normalized


class UserOut(ORMModel):
    id: str
    email: str
    full_name: str
    role: UserRole
    active: bool
    financial_summary_hidden: bool


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=12, max_length=128)
    role: UserRole = UserRole.operator


class UserPasswordUpdate(BaseModel):
    password: str = Field(min_length=12, max_length=128)


class UserProfileUpdate(BaseModel):
    email: EmailStr


class UserPreferencesUpdate(BaseModel):
    financial_summary_hidden: bool


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    password: str | None = Field(default=None, min_length=12, max_length=128)
    role: UserRole | None = None
    active: bool | None = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105
    persistent: bool = False
    user: UserOut


class BiometricCredentialCreate(BaseModel):
    device_name: str = Field(min_length=1, max_length=160)


class BiometricCredentialLogin(BaseModel):
    credential: str = Field(min_length=32, max_length=512)


class BiometricCredentialOut(BaseModel):
    credential: str
    expires_at: datetime


class PushDeviceRegistration(BaseModel):
    token: str = Field(min_length=20, max_length=4096)
    platform: Literal["android"] = "android"
    sound_settings_version: Literal[0, 1, 2] = 0


class PushPreferenceUpdate(BaseModel):
    enabled: bool
    sound: NotificationSound | None = None


class PushPreferenceOut(BaseModel):
    category: str
    label: str
    description: str
    enabled: bool
    sound: NotificationSound = "system"


class PushNotificationOut(UtcModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    category: str
    title: str
    body: str
    status: str
    created_at: datetime
    sent_at: datetime | None = None
    data: dict[str, Any] = Field(default_factory=dict)
