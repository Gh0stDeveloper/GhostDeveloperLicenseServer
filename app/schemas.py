from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    expires_in_minutes: int = Field(default=240, ge=1, le=525_600)
    activation_limit: int = Field(default=1, ge=1, le=100)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LicenseResponse(BaseModel):
    id: str
    key_prefix: str
    product: str
    owner_telegram_id: str | None
    owner_username: str | None
    status: str
    created_at: datetime
    expires_at: datetime
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

    key: str = Field(min_length=12, max_length=128)
    ip: str = Field(min_length=3, max_length=45)
    nonce: str = Field(pattern=r"^[A-Fa-f0-9]{48}$")
    timestamp: int
    product: str = Field(default="hextunnel", pattern=PRODUCT_PATTERN)
    action: Literal["install", "upgrade"] = "install"


class AuthorizeResponse(BaseModel):
    status: Literal["valid"]
    expires_at: datetime
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
