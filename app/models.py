from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class License(Base):
    __tablename__ = "licenses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    key_prefix: Mapped[str] = mapped_column(String(24), index=True)
    product: Mapped[str] = mapped_column(String(64), index=True)
    owner_telegram_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    owner_username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    issued_by_telegram_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    source_chat_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    notification_chat_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    reseller_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    created_at: Mapped[int] = mapped_column(Integer)
    # expires_at is the redemption deadline of the key. It does not terminate an
    # activation that was completed before this timestamp.
    expires_at: Mapped[int] = mapped_column(Integer, index=True)
    key_redeemed_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    activation_limit: Mapped[int] = mapped_column(Integer, default=1)
    activation_count: Mapped[int] = mapped_column(Integer, default=0)
    bound_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    activated_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revoked_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")

    activations: Mapped[list["Activation"]] = relationship(
        back_populates="license", cascade="all, delete-orphan"
    )


class Activation(Base):
    __tablename__ = "activations"
    __table_args__ = (
        UniqueConstraint("license_id", "subject_ip", name="uq_activation_license_ip"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    license_id: Mapped[str] = mapped_column(
        ForeignKey("licenses.id", ondelete="CASCADE"), index=True
    )
    subject_ip: Mapped[str] = mapped_column(String(45), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[int] = mapped_column(Integer)
    last_seen_at: Mapped[int] = mapped_column(Integer)
    lease_expires_at: Mapped[int] = mapped_column(Integer)
    revoked_at: Mapped[int | None] = mapped_column(Integer, nullable=True)

    license: Mapped[License] = relationship(back_populates="activations")


class ActivationEvent(Base):
    __tablename__ = "activation_events"
    __table_args__ = (
        UniqueConstraint("activation_id", name="uq_activation_event_activation"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    license_id: Mapped[str] = mapped_column(
        ForeignKey("licenses.id", ondelete="CASCADE"), index=True
    )
    activation_id: Mapped[str] = mapped_column(
        ForeignKey("activations.id", ondelete="CASCADE"), index=True
    )
    subject_ip: Mapped[str] = mapped_column(String(45), index=True)
    created_at: Mapped[int] = mapped_column(Integer, index=True)
    notification_chat_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    source_chat_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    issued_by_telegram_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reseller_name: Mapped[str] = mapped_column(String(128), default="Hex Tunnel Bot Gen")
    delivered_at: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)


class InstallerLink(Base):
    __tablename__ = "installer_links"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[int] = mapped_column(Integer, index=True)
    created_by_telegram_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    source_chat_id: Mapped[str | None] = mapped_column(String(32), nullable=True)


class Release(Base):
    __tablename__ = "releases"
    __table_args__ = (UniqueConstraint("product", "version", name="uq_release_product_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    product: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[str] = mapped_column(String(64), index=True)
    file_path: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    entrypoint: Mapped[str] = mapped_column(String(256))
    active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[int] = mapped_column(Integer)


class UsedNonce(Base):
    __tablename__ = "used_nonces"

    nonce_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[int] = mapped_column(Integer, index=True)


class DownloadToken(Base):
    __tablename__ = "download_tokens"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    license_id: Mapped[str] = mapped_column(
        ForeignKey("licenses.id", ondelete="CASCADE"), index=True
    )
    release_id: Mapped[str] = mapped_column(
        ForeignKey("releases.id", ondelete="CASCADE"), index=True
    )
    subject_ip: Mapped[str] = mapped_column(String(45), index=True)
    created_at: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[int] = mapped_column(Integer, index=True)
    consumed_at: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    actor: Mapped[str] = mapped_column(String(128))
    subject: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[int] = mapped_column(Integer, index=True)
    details_json: Mapped[str] = mapped_column(Text, default="{}")


Index("ix_download_token_validity", DownloadToken.expires_at, DownloadToken.consumed_at)
Index("ix_activation_event_pending", ActivationEvent.delivered_at, ActivationEvent.created_at)
