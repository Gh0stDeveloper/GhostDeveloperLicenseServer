from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.dependencies import (
    get_secrets,
    get_session,
    get_settings_from_app,
    require_admin,
)
from app.models import Activation, License, Release
from app.schemas import (
    LicenseCreateRequest,
    LicenseCreatedResponse,
    LicenseListResponse,
    LicenseResponse,
    ReleaseActivateRequest,
    ReleaseCreateRequest,
    ReleaseResponse,
    ResetActivationRequest,
    RevokeRequest,
)
from app.security import AppSecrets
from app.services import (
    add_audit,
    begin_immediate,
    generate_unique_license,
    license_to_response,
    now_epoch,
    release_to_response,
    resolve_release_path,
    sha256_file,
    validate_release_archive,
)

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


@router.post("/licenses", response_model=LicenseCreatedResponse, status_code=201)
def create_license(
    payload: LicenseCreateRequest,
    session: Session = Depends(get_session),
    secrets: AppSecrets = Depends(get_secrets),
) -> LicenseCreatedResponse:
    begin_immediate(session)
    current_time = now_epoch()

    if payload.owner_telegram_id:
        existing = session.scalar(
            select(License)
            .where(
                License.product == payload.product,
                License.owner_telegram_id == payload.owner_telegram_id,
                License.status.in_(("active", "activated")),
                License.expires_at > current_time,
            )
            .order_by(License.created_at.desc())
        )
        if existing is not None:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El usuario ya tiene una licencia activa",
            )

    key, key_hash = generate_unique_license(session, secrets)
    row = License(
        id=str(uuid.uuid4()),
        key_hash=key_hash,
        key_prefix=key[:12],
        product=payload.product,
        owner_telegram_id=payload.owner_telegram_id,
        owner_username=payload.owner_username,
        status="active",
        created_at=current_time,
        expires_at=current_time + payload.expires_in_minutes * 60,
        activation_limit=payload.activation_limit,
        activation_count=0,
        metadata_json=json.dumps(payload.metadata, separators=(",", ":"), sort_keys=True),
    )
    session.add(row)
    add_audit(
        session,
        event_type="license.created",
        actor="admin-api",
        subject=row.id,
        details={"product": row.product, "owner_telegram_id": row.owner_telegram_id},
    )
    session.commit()
    return LicenseCreatedResponse(**license_to_response(row).model_dump(), key=key)


@router.get("/licenses", response_model=LicenseListResponse)
def list_licenses(
    status_filter: str | None = Query(default=None, alias="status"),
    product: str | None = None,
    owner_telegram_id: str | None = Query(default=None, max_length=32),
    active_only: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> LicenseListResponse:
    conditions = []
    if status_filter:
        conditions.append(License.status == status_filter)
    if product:
        conditions.append(License.product == product)
    if owner_telegram_id:
        conditions.append(License.owner_telegram_id == owner_telegram_id)
    if active_only:
        conditions.extend(
            [
                License.status.in_(("active", "activated")),
                License.expires_at > now_epoch(),
            ]
        )
    query = select(License).order_by(License.created_at.desc()).limit(limit).offset(offset)
    count_query = select(func.count()).select_from(License)
    if conditions:
        query = query.where(*conditions)
        count_query = count_query.where(*conditions)
    items = [license_to_response(item) for item in session.scalars(query).all()]
    total = int(session.scalar(count_query) or 0)
    return LicenseListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/licenses/{license_id}", response_model=LicenseResponse)
def get_license(
    license_id: str,
    session: Session = Depends(get_session),
) -> LicenseResponse:
    row = session.get(License, license_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Licencia no encontrada")
    return license_to_response(row)


@router.post("/licenses/{license_id}/revoke", response_model=LicenseResponse)
def revoke_license(
    license_id: str,
    payload: RevokeRequest,
    session: Session = Depends(get_session),
) -> LicenseResponse:
    begin_immediate(session)
    row = session.get(License, license_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Licencia no encontrada")
    current_time = now_epoch()
    row.status = "revoked"
    row.revoked_at = current_time
    row.revoke_reason = payload.reason
    session.execute(
        update(Activation)
        .where(Activation.license_id == row.id, Activation.revoked_at.is_(None))
        .values(revoked_at=current_time)
    )
    add_audit(
        session,
        event_type="license.revoked",
        actor="admin-api",
        subject=row.id,
        details={"reason": payload.reason},
    )
    session.commit()
    return license_to_response(row)


@router.post("/licenses/{license_id}/reset-activation", response_model=LicenseResponse)
def reset_activation(
    license_id: str,
    payload: ResetActivationRequest,
    session: Session = Depends(get_session),
) -> LicenseResponse:
    begin_immediate(session)
    row = session.get(License, license_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Licencia no encontrada")
    session.execute(delete(Activation).where(Activation.license_id == row.id))
    row.activation_count = 0
    row.bound_ip = None
    row.activated_at = None
    if row.status == "activated":
        row.status = "active"
    add_audit(
        session,
        event_type="license.activation_reset",
        actor="admin-api",
        subject=row.id,
        details={"reason": payload.reason},
    )
    session.commit()
    return license_to_response(row)


@router.post("/releases", response_model=ReleaseResponse, status_code=201)
def create_release(
    payload: ReleaseCreateRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings_from_app),
) -> ReleaseResponse:
    package = resolve_release_path(settings, payload.relative_path)
    validate_release_archive(package, payload.entrypoint)
    checksum = sha256_file(package)
    begin_immediate(session)
    if payload.activate:
        session.execute(
            update(Release)
            .where(Release.product == payload.product, Release.active.is_(True))
            .values(active=False)
        )
    release = Release(
        id=str(uuid.uuid4()),
        product=payload.product,
        version=payload.version,
        file_path=str(package),
        sha256=checksum,
        entrypoint=payload.entrypoint,
        active=payload.activate,
        created_at=now_epoch(),
    )
    session.add(release)
    add_audit(
        session,
        event_type="release.created",
        actor="admin-api",
        subject=release.id,
        details={"product": release.product, "version": release.version, "sha256": checksum},
    )
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una release con ese producto y versión",
        ) from exc
    return release_to_response(release, settings.release_root)


@router.post("/releases/{release_id}/activate", response_model=ReleaseResponse)
def activate_release(
    release_id: str,
    payload: ReleaseActivateRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings_from_app),
) -> ReleaseResponse:
    begin_immediate(session)
    release = session.get(Release, release_id)
    if release is None:
        raise HTTPException(status_code=404, detail="Release no encontrada")
    package = resolve_release_path(
        settings,
        str(release_to_response(release, settings.release_root).relative_path),
    )
    validate_release_archive(package, release.entrypoint)
    checksum = sha256_file(package)
    if checksum != release.sha256:
        raise HTTPException(status_code=409, detail="El paquete cambió desde que fue registrado")
    session.execute(
        update(Release)
        .where(Release.product == release.product, Release.id != release.id)
        .values(active=False)
    )
    release.active = True
    add_audit(
        session,
        event_type="release.activated",
        actor="admin-api",
        subject=release.id,
        details={
            "product": release.product,
            "version": release.version,
            "reason": payload.reason,
        },
    )
    session.commit()
    return release_to_response(release, settings.release_root)


@router.get("/releases", response_model=list[ReleaseResponse])
def list_releases(
    product: str | None = None,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings_from_app),
) -> list[ReleaseResponse]:
    query = select(Release).order_by(Release.created_at.desc())
    if product:
        query = query.where(Release.product == product)
    return [
        release_to_response(item, settings.release_root)
        for item in session.scalars(query).all()
    ]
