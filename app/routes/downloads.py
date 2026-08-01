from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import Settings
from app.dependencies import get_secrets, get_session, get_settings_from_app
from app.models import DownloadToken, Release
from app.security import AppSecrets, request_source_ip
from app.services import (
    add_audit,
    begin_immediate,
    create_download_token_hash,
    now_epoch,
)

router = APIRouter(tags=["downloads"])


@router.get("/releases/{token}", response_class=FileResponse)
def download_release(
    token: str,
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings_from_app),
    secrets: AppSecrets = Depends(get_secrets),
) -> FileResponse:
    if len(token) < 32 or len(token) > 256:
        raise HTTPException(status_code=404, detail="Token de descarga inválido")
    source_ip = request_source_ip(request) if settings.enforce_source_ip else None
    token_hash = create_download_token_hash(secrets, token)
    current_time = now_epoch()

    begin_immediate(session)
    conditions = [
        DownloadToken.token_hash == token_hash,
        DownloadToken.consumed_at.is_(None),
        DownloadToken.expires_at > current_time,
    ]
    if source_ip is not None:
        conditions.append(DownloadToken.subject_ip == source_ip)
    row = session.scalar(select(DownloadToken).where(*conditions))
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El enlace no existe, expiró o ya fue utilizado",
        )
    result = session.execute(
        update(DownloadToken)
        .where(
            DownloadToken.token_hash == token_hash,
            DownloadToken.consumed_at.is_(None),
        )
        .values(consumed_at=current_time)
    )
    if result.rowcount != 1:
        session.rollback()
        raise HTTPException(status_code=409, detail="El enlace ya fue utilizado")

    release = session.get(Release, row.release_id)
    if release is None:
        session.rollback()
        raise HTTPException(status_code=404, detail="Release no encontrada")
    package = Path(release.file_path)
    if not package.is_file():
        session.rollback()
        raise HTTPException(status_code=503, detail="El paquete no está disponible")

    add_audit(
        session,
        event_type="release.downloaded",
        actor=row.subject_ip,
        subject=row.license_id,
        details={"release_id": release.id, "version": release.version},
    )
    session.commit()
    return FileResponse(
        path=package,
        media_type="application/gzip",
        filename=f"hextunnel-{release.version}.tar.gz",
        headers={"Cache-Control": "no-store, private"},
    )
