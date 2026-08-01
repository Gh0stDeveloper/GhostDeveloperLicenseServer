from __future__ import annotations

from fastapi import APIRouter, Depends

from app import __version__
from app.config import Settings
from app.db import Database
from app.dependencies import get_database, get_settings_from_app
from app.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(
    database: Database = Depends(get_database),
    settings: Settings = Depends(get_settings_from_app),
) -> HealthResponse:
    database.check()
    return HealthResponse(
        status="online",
        service="ghostdeveloper-license-api",
        version=__version__,
        environment=settings.environment,
    )
