from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.dependencies import get_secrets, get_session, get_settings_from_app, get_signer
from app.models import License
from app.schemas import AuthorizeRequest, AuthorizeResponse
from app.security import AppSecrets, normalize_ip, request_source_ip
from app.services import (
    active_release,
    add_audit,
    begin_immediate,
    cleanup_ephemeral_records,
    create_download_token,
    create_license_key_hash,
    create_or_rotate_activation,
    iso_z,
    now_epoch,
    register_nonce,
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

    begin_immediate(session)
    cleanup_ephemeral_records(session, current_time)
    register_nonce(
        session,
        secrets,
        payload.nonce,
        current_time + settings.nonce_ttl_seconds,
    )

    key_hash = create_license_key_hash(secrets, payload.key)
    license_row = session.scalar(select(License).where(License.key_hash == key_hash))
    if license_row is None:
        raise HTTPException(status_code=403, detail="La key no existe")
    if license_row.product != payload.product:
        raise HTTPException(status_code=403, detail="La key no corresponde a este producto")
    if license_row.status == "revoked":
        raise HTTPException(status_code=403, detail="La licencia fue revocada")
    if license_row.expires_at <= current_time:
        license_row.status = "expired"
        session.commit()
        raise HTTPException(status_code=403, detail="La licencia expiró")

    release = active_release(session, payload.product)
    lease_expires_at = min(current_time + settings.lease_ttl_seconds, license_row.expires_at)
    activation, activation_token = create_or_rotate_activation(
        session,
        license_row=license_row,
        subject_ip=subject_ip,
        secrets=secrets,
        lease_expires_at=lease_expires_at,
    )
    license_row.status = "activated"

    download_expires_at = min(
        current_time + settings.download_ttl_seconds,
        license_row.expires_at,
    )
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
        event_type="installation.authorized",
        actor=subject_ip,
        subject=license_row.id,
        details={
            "activation_id": activation.id,
            "release_id": release.id,
            "version": release.version,
        },
    )
    session.commit()

    expires_at_text = iso_z(license_row.expires_at)
    download_expires_at_text = iso_z(download_expires_at)
    canonical = canonical_authorization(
        status="valid",
        expires_at=expires_at_text,
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
        expires_at=expires_at_text,
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
