from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.dependencies import get_secrets, get_session, get_settings_from_app, get_signer
from app.models import Activation, License
from app.schemas import LeaseRequest, LeaseResponse
from app.security import AppSecrets, normalize_ip, request_source_ip
from app.services import (
    add_audit,
    begin_immediate,
    create_activation_token_hash,
    iso_z,
    now_epoch,
)
from app.signing import AuthorizationSigner, canonical_lease

router = APIRouter(prefix="/api/v1/licenses", tags=["licenses"])


@router.post("/lease", response_model=LeaseResponse)
def renew_lease(
    payload: LeaseRequest,
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings_from_app),
    secrets: AppSecrets = Depends(get_secrets),
    signer: AuthorizationSigner = Depends(get_signer),
) -> LeaseResponse:
    subject_ip = normalize_ip(payload.ip)
    if settings.enforce_source_ip and request_source_ip(request) != subject_ip:
        raise HTTPException(status_code=403, detail="La IP declarada no coincide con el origen")

    token_hash = create_activation_token_hash(secrets, payload.activation_token)
    begin_immediate(session)
    activation = session.scalar(
        select(Activation).where(
            Activation.token_hash == token_hash,
            Activation.revoked_at.is_(None),
        )
    )
    if activation is None:
        raise HTTPException(status_code=403, detail="Token de activación inválido")
    license_row = session.get(License, activation.license_id)
    if license_row is None or license_row.status == "revoked":
        raise HTTPException(status_code=403, detail="Licencia inválida o revocada")
    current_time = now_epoch()
    if license_row.expires_at <= current_time:
        license_row.status = "expired"
        session.commit()
        raise HTTPException(status_code=403, detail="La licencia expiró")
    if activation.subject_ip != subject_ip:
        raise HTTPException(status_code=403, detail="La activación pertenece a otra IP")
    if license_row.product != payload.product:
        raise HTTPException(status_code=403, detail="Producto no autorizado")

    lease_expires_at = min(current_time + settings.lease_ttl_seconds, license_row.expires_at)
    activation.last_seen_at = current_time
    activation.lease_expires_at = lease_expires_at
    add_audit(
        session,
        event_type="license.lease_renewed",
        actor=subject_ip,
        subject=license_row.id,
        details={"activation_id": activation.id},
    )
    session.commit()

    lease_text = iso_z(lease_expires_at)
    canonical = canonical_lease(
        status="active",
        lease_expires_at=lease_text,
        subject=subject_ip,
        product=payload.product,
        activation_id=activation.id,
    )
    return LeaseResponse(
        status="active",
        lease_expires_at=lease_text,
        subject=subject_ip,
        product=payload.product,
        activation_id=activation.id,
        signature=signer.sign(canonical),
    )
