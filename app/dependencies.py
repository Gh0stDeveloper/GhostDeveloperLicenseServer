from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import Database
from app.security import AppSecrets, constant_time_bearer_check
from app.signing import AuthorizationSigner


def get_database(request: Request) -> Database:
    return request.app.state.database


def get_session(database: Database = Depends(get_database)) -> Generator[Session, None, None]:
    yield from database.sessions()


def get_settings_from_app(request: Request) -> Settings:
    return request.app.state.settings


def get_secrets(request: Request) -> AppSecrets:
    return request.app.state.secrets


def get_signer(request: Request) -> AuthorizationSigner:
    return request.app.state.signer


def require_admin(
    request: Request,
    secrets: AppSecrets = Depends(get_secrets),
) -> None:
    constant_time_bearer_check(request, secrets.admin_token)
