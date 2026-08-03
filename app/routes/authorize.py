from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.dependencies import get_secrets, get_session, get_settings_from_app, get_signer
from app.models import Activation, License, Release
from app.schemas import AuthorizeRequest, AuthorizeResponse
from app.security import AppSecrets, normalize_ip, request_source_ip
from app.services import (
    active_release,
    add_audit,
    begin_immediate,
    cleanup_ephemeral_records,
    create_activation_event,
    create_activation_token_hash,
    create_download_token,
    create_license_key_hash,
    create_or_rotate_activation,
    iso_z,
    now_epoch,
    register_nonce,
    resolved_reseller_name,
)
from app.signing import AuthorizationSigner, canonical_authorization

router = APIRouter(prefix="/api/v1/install", tags=["installation"])


@router.post("/authorize", response_model=AuthorizeResponse)
def authorize_installation(
    payload: AuthorizeRequest,
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings_from_app),
    secrets: AppSecrets = Depends(get_secrets),
    signer: AuthorizationSigner = Depends(get_signer),
) -> AuthorizeResponse:
    current_time = now_epoch()
    if abs(current_time - payload.timestamp) > settings.max_clock_skew_seconds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El timestamp está fuera de la ventana permitida",
        )

    subject_ip = normalize_ip(payload.ip)
    if settings.enforce_source_ip:
        source_ip = request_source_ip(request)
        if source_ip != subject_ip:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="La IP declarada no coincide con la conexión de origen",
            )

    # Verify the package before taking SQLite's write lock.
    verified_release = active_release(session, payload.product)
    release_id = verified_release.id
    session.rollback()

    begin_immediate(session)
    cleanup_ephemeral_records(session, current_time)
    register_nonce(
        session,
        secrets,
        payload.nonce,
        current_time + settings.nonce_ttl_seconds,
    )

    activation: Activation | None = None
    license_row: License | None = None

    if payload.action == "upgrade" and payload.activation_token:
        token_hash = create_activation_token_hash(secrets, payload.activation_token)
        activation = session.scalar(
            select(Activation).where(
                Activation.token_hash == token_hash,
                Activation.revoked_at.is_(None),
            )
        )
        if activation is None:
            raise HTTPException(status_code=403, detail="Token de activación inválido")
        if activation.subject_ip != subject_ip:
            raise HTTPException(status_code=403, detail="La activación pertenece a otra IP")
        license_row = session.get(License, activation.license_id)
    else:
        if not payload.key:
            raise HTTPException(status_code=403, detail="No se proporcionó una key")
        key_hash = create_license_key_hash(secrets, payload.key)
        license_row = session.scalar(select(License).where(License.key_hash == key_hash))

    if license_row is None:
        raise HTTPException(status_code=403, detail="La key o activación no existe")
    if license_row.product != payload.product:
        raise HTTPException(status_code=403, detail="La autorización no corresponde a este producto")
    if license_row.status == "revoked":
        raise HTTPException(status_code=403, detail="La instalación fue revocada")

    if payload.action == "install":
        if license_row.status == "activated" or license_row.activation_count > 0:
            raise HTTPException(status_code=403, detail="La key ya fue utilizada")
        if license_row.expires_at <= current_time:
            license_row.status = "expired"
            session.commit()
            raise HTTPException(status_code=403, detail="La key expiró antes de ser utilizada")
    elif activation is None:
        activation = session.scalar(
            select(Activation).where(
                Activation.license_id == license_row.id,
                Activation.subject_ip == subject_ip,
                Activation.revoked_at.is_(None),
            )
        )
        if activation is None:
            raise HTTPException(
                status_code=403,
                detail="La actualización requiere una activación existente en esta IP",
            )

    release = session.get(Release, release_id)
    if release is None or not release.active:
        raise HTTPException(status_code=503, detail="La release verificada dejó de estar activa")

    lease_expires_at = current_time + settings.lease_ttl_seconds
    activation, activation_token, created = create_or_rotate_activation(
        session,
        license_row=license_row,
        subject_ip=subject_ip,
        secrets=secrets,
        lease_expires_at=lease_expires_at,
    )
    license_row.status = "activated"
    if created:
        # ActivationEvent has a foreign key to the newly created activation.
        # Flush it first so SQLite can validate the reference deterministically.
        session.flush()
        create_activation_event(session, license_row=license_row, activation=activation)

    download_expires_at = current_time + settings.download_ttl_seconds
    raw_download_token = create_download_token(
        session,
        license_id=license_row.id,
        release_id=release.id,
        subject_ip=subject_ip,
        secrets=secrets,
        expires_at=download_expires_at,
    )
    download_url = f"{settings.download_base_url}/releases/{raw_download_token}"

    add_audit(
        session,
        event_type=("installation.activated" if created else "installation.authorized"),
        actor=subject_ip,
        subject=license_row.id,
        details={
            "activation_id": activation.id,
            "release_id": release.id,
            "version": release.version,
            "action": payload.action,
            "permanent": True,
            "reseller_name": resolved_reseller_name(license_row),
        },
    )
    session.commit()

    key_expires_at_text = iso_z(license_row.expires_at)
    activated_at_text = iso_z(license_row.activated_at or activation.created_at)
    download_expires_at_text = iso_z(download_expires_at)
    reseller_name = resolved_reseller_name(license_row)
    canonical = canonical_authorization(
        status="valid",
        key_expires_at=key_expires_at_text,
        activated_at=activated_at_text,
        installation_permanent=True,
        reseller_name=reseller_name,
        download_expires_at=download_expires_at_text,
        nonce=payload.nonce,
        subject=subject_ip,
        version=release.version,
        download_url=download_url,
        package_sha256=release.sha256,
        entrypoint=release.entrypoint,
    )
    signature = signer.sign(canonical)

    return AuthorizeResponse(
        status="valid",
        expires_at=key_expires_at_text,
        key_expires_at=key_expires_at_text,
        activated_at=activated_at_text,
        installation_permanent=True,
        reseller_name=reseller_name,
        download_expires_at=download_expires_at_text,
        nonce=payload.nonce,
        subject=subject_ip,
        version=release.version,
        download_url=download_url,
        package_sha256=release.sha256,
        entrypoint=release.entrypoint,
        signature=signature,
        activation_token=activation_token,
        lease_expires_at=iso_z(lease_expires_at),
    )
