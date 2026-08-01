from __future__ import annotations

import hashlib
import hmac
import ipaddress
import secrets
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, Request, status


@dataclass(frozen=True, slots=True)
class AppSecrets:
    admin_token: str
    hmac_secret: bytes


def _read_text_secret(path: Path, minimum_length: int) -> str:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"No se pudo leer el secreto requerido: {path}") from exc
    if len(value) < minimum_length:
        raise RuntimeError(f"El secreto {path} es demasiado corto")
    return value


def load_app_secrets(admin_token_file: Path, hmac_secret_file: Path) -> AppSecrets:
    admin_token = _read_text_secret(admin_token_file, 32)
    hmac_value = _read_text_secret(hmac_secret_file, 32)
    return AppSecrets(admin_token=admin_token, hmac_secret=hmac_value.encode("utf-8"))


def hmac_digest(secret: bytes, value: str) -> str:
    return hmac.new(secret, value.encode("utf-8"), hashlib.sha256).hexdigest()


def generate_license_key() -> str:
    body = secrets.token_hex(12).upper()
    groups = [body[index : index + 4] for index in range(0, len(body), 4)]
    return "HT-" + "-".join(groups)


def generate_url_token() -> str:
    return secrets.token_urlsafe(32)


def constant_time_bearer_check(request: Request, expected: str) -> None:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token or not secrets.compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales administrativas inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )


def normalize_ip(value: str) -> str:
    try:
        return ipaddress.ip_address(value).compressed
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Dirección IP inválida") from exc


def request_source_ip(request: Request) -> str:
    if request.client is None:
        raise HTTPException(status_code=400, detail="No se pudo identificar la IP de origen")
    return normalize_ip(request.client.host)
