from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.config import Settings
from app.dependencies import get_settings_from_app

router = APIRouter(tags=["public-key"])


@router.get(
    "/.well-known/hextunnel-license-public.pem",
    response_class=FileResponse,
    include_in_schema=False,
)
def public_key(settings: Settings = Depends(get_settings_from_app)) -> FileResponse:
    if not settings.public_key_file.is_file():
        raise HTTPException(status_code=404, detail="Clave pública no disponible")
    return FileResponse(
        settings.public_key_file,
        media_type="application/x-pem-file",
        headers={"Cache-Control": "public, max-age=3600"},
    )
