from __future__ import annotations

import hashlib
import json
import os
import tarfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import (
    Activation,
    ActivationEvent,
    AuditEvent,
    DownloadToken,
    InstallerLink,
    License,
    Release,
    UsedNonce,
)
from app.schemas import LicenseResponse, ReleaseResponse
from app.security import AppSecrets, generate_license_key, generate_url_token, hmac_digest

DEFAULT_RESELLER_NAME = "Hex Tunnel Bot Gen"


def now_epoch() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def as_datetime(epoch: int | None) -> datetime | None:
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, timezone.utc)


def iso_z(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace("+00:00", "Z")


def begin_immediate(session: Session) -> None:
    if session.bind is not None and session.bind.dialect.name == "sqlite":
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")


def add_audit(
    session: Session,
    *,
    event_type: str,
    actor: str,
    subject: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditEvent(
            id=str(uuid.uuid4()),
            event_type=event_type,
            actor=actor,
            subject=subject,
            created_at=now_epoch(),
            details_json=json.dumps(details or {}, separators=(",", ":"), sort_keys=True),
        )
    )


def license_metadata(license_row: License) -> dict[str, Any]:
    try:
        value = json.loads(license_row.metadata_json or "{}")
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def resolved_reseller_name(license_row: License) -> str:
    metadata = license_metadata(license_row)
    value = license_row.reseller_name or metadata.get("reseller_name") or DEFAULT_RESELLER_NAME
    return str(value)[:128]


def license_to_response(license_row: License) -> LicenseResponse:
    metadata = license_metadata(license_row)
    return LicenseResponse(
        id=license_row.id,
        key_prefix=license_row.key_prefix,
        product=license_row.product,
        owner_telegram_id=license_row.owner_telegram_id,
        owner_username=license_row.owner_username,
        issued_by_telegram_id=(
            license_row.issued_by_telegram_id
            or metadata.get("issued_by_telegram_id")
        ),
        source_chat_id=license_row.source_chat_id or metadata.get("source_chat_id"),
        notification_chat_id=(
            license_row.notification_chat_id
            or metadata.get("notification_chat_id")
            or metadata.get("source_chat_id")
        ),
        reseller_name=resolved_reseller_name(license_row),
        status=license_row.status,
        created_at=as_datetime(license_row.created_at),
        expires_at=as_datetime(license_row.expires_at),
        key_redeemed_at=as_datetime(license_row.key_redeemed_at),
        activation_limit=license_row.activation_limit,
        activation_count=license_row.activation_count,
        bound_ip=license_row.bound_ip,
        activated_at=as_datetime(license_row.activated_at),
        revoked_at=as_datetime(license_row.revoked_at),
        revoke_reason=license_row.revoke_reason,
        metadata=metadata,
    )


def release_to_response(release: Release, release_root: Path) -> ReleaseResponse:
    path = Path(release.file_path)
    try:
        relative_path = str(path.resolve().relative_to(release_root.resolve()))
    except ValueError:
        relative_path = path.name
    return ReleaseResponse(
        id=release.id,
        product=release.product,
        version=release.version,
        relative_path=relative_path,
        sha256=release.sha256,
        entrypoint=release.entrypoint,
        active=release.active,
        created_at=as_datetime(release.created_at),
    )


def create_license_key_hash(secrets: AppSecrets, key: str) -> str:
    return hmac_digest(secrets.hmac_secret, "license:" + key)


def create_activation_token_hash(secrets: AppSecrets, token: str) -> str:
    return hmac_digest(secrets.hmac_secret, "activation:" + token)


def create_download_token_hash(secrets: AppSecrets, token: str) -> str:
    return hmac_digest(secrets.hmac_secret, "download:" + token)


def create_installer_link_hash(secrets: AppSecrets, token: str) -> str:
    return hmac_digest(secrets.hmac_secret, "installer-link:" + token)


def create_nonce_hash(secrets: AppSecrets, nonce: str) -> str:
    return hmac_digest(secrets.hmac_secret, "nonce:" + nonce.lower())


def generate_unique_license(session: Session, secrets: AppSecrets) -> tuple[str, str]:
    for _ in range(10):
        key = generate_license_key()
        key_hash = create_license_key_hash(secrets, key)
        exists = session.scalar(select(License.id).where(License.key_hash == key_hash))
        if exists is None:
            return key, key_hash
    raise HTTPException(status_code=500, detail="No se pudo generar una key única")


def resolve_release_path(settings: Settings, relative_path: str) -> Path:
    root = settings.release_root.resolve()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Ruta de release fuera del directorio permitido") from exc
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="El paquete indicado no existe")
    return candidate


def validate_release_archive(path: Path, entrypoint: str) -> None:
    try:
        with tarfile.open(path, "r:gz") as archive:
            members = archive.getmembers()
            names: set[str] = set()
            for member in members:
                normalized = member.name.replace("\\", "/")
                parts = [part for part in normalized.split("/") if part not in {"", "."}]
                if normalized.startswith("/") or ".." in parts:
                    raise HTTPException(
                        status_code=422,
                        detail="El paquete contiene rutas no seguras",
                    )
                if member.issym() or member.islnk() or member.isdev():
                    raise HTTPException(
                        status_code=422,
                        detail="El paquete contiene enlaces o dispositivos no permitidos",
                    )
                normalized_name = "/".join(parts)
                if normalized_name in names:
                    raise HTTPException(
                        status_code=422,
                        detail="El paquete contiene rutas duplicadas",
                    )
                names.add(normalized_name)
    except (tarfile.TarError, OSError) as exc:
        raise HTTPException(status_code=422, detail="El paquete no es un TAR.GZ válido") from exc
    if entrypoint not in names:
        raise HTTPException(
            status_code=422,
            detail=f"El paquete no contiene el entrypoint requerido: {entrypoint}",
        )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cleanup_ephemeral_records(session: Session, current_time: int) -> None:
    session.execute(delete(UsedNonce).where(UsedNonce.expires_at < current_time))
    session.execute(
        delete(DownloadToken).where(
            DownloadToken.expires_at < current_time - 86400,
        )
    )
    session.execute(delete(InstallerLink).where(InstallerLink.expires_at < current_time - 86400))
    session.execute(
        delete(ActivationEvent).where(
            ActivationEvent.delivered_at.is_not(None),
            ActivationEvent.delivered_at < current_time - 30 * 86400,
        )
    )


def register_nonce(
    session: Session,
    secrets: AppSecrets,
    nonce: str,
    expires_at: int,
) -> None:
    nonce_hash = create_nonce_hash(secrets, nonce)
    session.add(UsedNonce(nonce_hash=nonce_hash, expires_at=expires_at))
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El nonce ya fue utilizado",
        ) from exc


def active_release(session: Session, product: str) -> Release:
    release = session.scalar(
        select(Release)
        .where(Release.product == product, Release.active.is_(True))
        .order_by(Release.created_at.desc())
    )
    if release is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No existe una versión publicada para este producto",
        )
    package = Path(release.file_path)
    if not package.is_file():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El paquete publicado no está disponible en el servidor",
        )
    if sha256_file(package) != release.sha256:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La integridad del paquete publicado no coincide con la release registrada",
        )
    return release


def create_or_rotate_activation(
    session: Session,
    *,
    license_row: License,
    subject_ip: str,
    secrets: AppSecrets,
    lease_expires_at: int,
) -> tuple[Activation, str, bool]:
    current_time = now_epoch()
    activation = session.scalar(
        select(Activation).where(
            Activation.license_id == license_row.id,
            Activation.subject_ip == subject_ip,
            Activation.revoked_at.is_(None),
        )
    )
    raw_token = generate_url_token()
    token_hash = create_activation_token_hash(secrets, raw_token)
    created = activation is None

    if activation is None:
        if license_row.activation_count >= license_row.activation_limit:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="La key ya fue utilizada",
            )
        activation = Activation(
            id=str(uuid.uuid4()),
            license_id=license_row.id,
            subject_ip=subject_ip,
            token_hash=token_hash,
            created_at=current_time,
            last_seen_at=current_time,
            lease_expires_at=lease_expires_at,
        )
        session.add(activation)
        license_row.activation_count += 1
        license_row.bound_ip = subject_ip
        license_row.activated_at = license_row.activated_at or current_time
        license_row.key_redeemed_at = license_row.key_redeemed_at or current_time
    else:
        activation.token_hash = token_hash
        activation.last_seen_at = current_time
        activation.lease_expires_at = lease_expires_at

    return activation, raw_token, created


def create_activation_event(
    session: Session,
    *,
    license_row: License,
    activation: Activation,
) -> ActivationEvent:
    metadata = license_metadata(license_row)
    event = ActivationEvent(
        id=str(uuid.uuid4()),
        license_id=license_row.id,
        activation_id=activation.id,
        subject_ip=activation.subject_ip,
        created_at=activation.created_at,
        notification_chat_id=(
            license_row.notification_chat_id
            or metadata.get("notification_chat_id")
            or metadata.get("source_chat_id")
            or license_row.issued_by_telegram_id
            or metadata.get("issued_by_telegram_id")
        ),
        source_chat_id=license_row.source_chat_id or metadata.get("source_chat_id"),
        issued_by_telegram_id=(
            license_row.issued_by_telegram_id
            or metadata.get("issued_by_telegram_id")
        ),
        reseller_name=resolved_reseller_name(license_row),
    )
    session.add(event)
    return event


def create_download_token(
    session: Session,
    *,
    license_id: str,
    release_id: str,
    subject_ip: str,
    secrets: AppSecrets,
    expires_at: int,
) -> str:
    for _ in range(10):
        raw_token = generate_url_token()
        token_hash = create_download_token_hash(secrets, raw_token)
        existing = session.scalar(
            select(DownloadToken.token_hash).where(DownloadToken.token_hash == token_hash)
        )
        if existing is None:
            session.add(
                DownloadToken(
                    token_hash=token_hash,
                    license_id=license_id,
                    release_id=release_id,
                    subject_ip=subject_ip,
                    created_at=now_epoch(),
                    expires_at=expires_at,
                )
            )
            return raw_token
    raise HTTPException(status_code=500, detail="No se pudo generar el token de descarga")


def create_installer_link(
    session: Session,
    *,
    secrets: AppSecrets,
    expires_at: int,
    created_by_telegram_id: str | None,
    source_chat_id: str | None,
) -> str:
    for _ in range(10):
        token = generate_url_token()
        token_hash = create_installer_link_hash(secrets, token)
        if session.get(InstallerLink, token_hash) is None:
            session.add(
                InstallerLink(
                    token_hash=token_hash,
                    created_at=now_epoch(),
                    expires_at=expires_at,
                    created_by_telegram_id=created_by_telegram_id,
                    source_chat_id=source_chat_id,
                )
            )
            return token
    raise HTTPException(status_code=500, detail="No se pudo crear el enlace temporal")


def ensure_secure_file(path: Path) -> None:
    stat = path.stat()
    if stat.st_mode & 0o077:
        raise RuntimeError(f"Permisos inseguros en {path}; se requiere 600 o más restrictivo")
    if os.name == "posix" and stat.st_uid != 0 and os.getenv("GHOST_LICENSE_ALLOW_NONROOT_SECRETS") != "1":
        raise RuntimeError(f"El archivo secreto {path} debe pertenecer a root")
