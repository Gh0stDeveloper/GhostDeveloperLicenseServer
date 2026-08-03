from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


PRODUCT_PATTERN = r"^[a-z0-9][a-z0-9._-]{1,63}$"
VERSION_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$"


class HealthResponse(BaseModel):
    status: Literal["online"]
    service: str
    version: str
    environment: str


class LicenseCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product: str = Field(default="hextunnel", pattern=PRODUCT_PATTERN)
    owner_telegram_id: str | None = Field(default=None, max_length=32)
    owner_username: str | None = Field(default=None, max_length=128)
    issued_by_telegram_id: str | None = Field(default=None, max_length=32)
    source_chat_id: str | None = Field(default=None, max_length=32)
    notification_chat_id: str | None = Field(default=None, max_length=32)
    reseller_name: str = Field(default="Hex Tunnel Bot Gen", min_length=2, max_length=128)
    expires_in_minutes: int = Field(default=240, ge=1, le=525_600)
    activation_limit: int = Field(default=1, ge=1, le=100)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LicenseResponse(BaseModel):
    id: str
    key_prefix: str
    product: str
    owner_telegram_id: str | None
    owner_username: str | None
    issued_by_telegram_id: str | None
    source_chat_id: str | None
    notification_chat_id: str | None
    reseller_name: str
    status: str
    created_at: datetime
    expires_at: datetime
    key_redeemed_at: datetime | None
    activation_limit: int
    activation_count: int
    bound_ip: str | None
    activated_at: datetime | None
    revoked_at: datetime | None
    revoke_reason: str | None
    metadata: dict[str, Any]


class LicenseCreatedResponse(LicenseResponse):
    key: str


class LicenseListResponse(BaseModel):
    items: list[LicenseResponse]
    total: int
    limit: int
    offset: int


class RevokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(default="Revocada por un administrador", min_length=3, max_length=500)


class ResetActivationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(default="Reinicio administrativo", min_length=3, max_length=500)


class ReleaseCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product: str = Field(default="hextunnel", pattern=PRODUCT_PATTERN)
    version: str = Field(pattern=VERSION_PATTERN)
    relative_path: str = Field(min_length=1, max_length=512)
    entrypoint: str = Field(default="bin/hextunnel-private-install", min_length=1, max_length=256)
    activate: bool = True

    @field_validator("relative_path", "entrypoint")
    @classmethod
    def reject_unsafe_paths(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        if normalized.startswith("/") or ".." in normalized.split("/"):
            raise ValueError("La ruta debe ser relativa y no puede contener '..'")
        return normalized


class ReleaseActivateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(default="Promoción administrativa", min_length=3, max_length=500)


class ReleaseResponse(BaseModel):
    id: str
    product: str
    version: str
    relative_path: str
    sha256: str
    entrypoint: str
    active: bool
    created_at: datetime


class AuthorizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str | None = Field(default=None, min_length=12, max_length=128)
    activation_token: str | None = Field(default=None, min_length=32, max_length=256)
    ip: str = Field(min_length=3, max_length=45)
    nonce: str = Field(pattern=r"^[A-Fa-f0-9]{48}$")
    timestamp: int
    product: str = Field(default="hextunnel", pattern=PRODUCT_PATTERN)
    action: Literal["install", "upgrade"] = "install"

    @model_validator(mode="after")
    def validate_credential(self) -> "AuthorizeRequest":
        if self.action == "install" and not self.key:
            raise ValueError("La instalación requiere una key")
        if self.action == "upgrade" and not (self.activation_token or self.key):
            raise ValueError("La actualización requiere el token de activación")
        return self


class AuthorizeResponse(BaseModel):
    status: Literal["valid"]
    expires_at: datetime
    key_expires_at: datetime
    activated_at: datetime
    installation_permanent: Literal[True]
    reseller_name: str
    download_expires_at: datetime
    nonce: str
    subject: str
    version: str
    download_url: str
    package_sha256: str
    entrypoint: str
    signature: str
    activation_token: str
    lease_expires_at: datetime


class LeaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activation_token: str = Field(min_length=32, max_length=256)
    ip: str = Field(min_length=3, max_length=45)
    product: str = Field(default="hextunnel", pattern=PRODUCT_PATTERN)


class LeaseResponse(BaseModel):
    status: Literal["active"]
    lease_expires_at: datetime
    subject: str
    product: str
    activation_id: str
    signature: str


class InstallerLinkCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expires_in_minutes: int = Field(default=15, ge=1, le=1440)
    created_by_telegram_id: str | None = Field(default=None, max_length=32)
    source_chat_id: str | None = Field(default=None, max_length=32)


class InstallerLinkResponse(BaseModel):
    url: str
    expires_at: datetime


class ActivationEventResponse(BaseModel):
    id: str
    license_id: str
    activation_id: str
    key_prefix: str
    subject_ip: str
    activated_at: datetime
    notification_chat_id: str | None
    source_chat_id: str | None
    issued_by_telegram_id: str | None
    reseller_name: str


class ActivationEventListResponse(BaseModel):
    items: list[ActivationEventResponse]
    total: int


class ActivationEventDeliveredResponse(BaseModel):
    id: str
    delivered_at: datetime
