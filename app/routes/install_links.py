from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import Settings
from app.dependencies import get_secrets, get_session, get_settings_from_app
from app.models import InstallerLink
from app.security import AppSecrets
from app.services import create_installer_link_hash, now_epoch

router = APIRouter(tags=["installation"])


@router.get("/i/{token}", include_in_schema=False)
def temporary_installer_link(
    token: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings_from_app),
    secrets: AppSecrets = Depends(get_secrets),
) -> RedirectResponse:
    if len(token) < 32 or len(token) > 256:
        raise HTTPException(status_code=404, detail="Enlace no encontrado")
    token_hash = create_installer_link_hash(secrets, token)
    link = session.get(InstallerLink, token_hash)
    if link is None or link.expires_at <= now_epoch():
        raise HTTPException(status_code=410, detail="El enlace temporal expiró")
    return RedirectResponse(
        url=settings.public_install_url,
        status_code=307,
        headers={"Cache-Control": "no-store, max-age=0"},
    )
