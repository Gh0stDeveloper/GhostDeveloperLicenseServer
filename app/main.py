from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app import __version__
from app.config import Settings, get_settings
from app.db import Database
from app.routes import admin, authorize, downloads, health, install_links, lease, well_known
from app.security import load_app_secrets
from app.signing import AuthorizationSigner


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = resolved
        app.state.database = Database(resolved.database_url)
        app.state.database.initialize()
        app.state.secrets = load_app_secrets(
            resolved.admin_token_file,
            resolved.hmac_secret_file,
        )
        app.state.signer = AuthorizationSigner.from_file(resolved.private_key_file)
        resolved.release_root.mkdir(parents=True, exist_ok=True)
        yield
        app.state.database.engine.dispose()

    docs_url = "/docs" if resolved.docs_enabled else None
    openapi_url = "/openapi.json" if resolved.docs_enabled else None
    application = FastAPI(
        title="Ghost Developer License Server",
        version=__version__,
        docs_url=docs_url,
        redoc_url=None,
        openapi_url=openapi_url,
        lifespan=lifespan,
    )
    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=[
            "ghostdeveloper.duckdns.org",
            "ghostdeveloperkeys.duckdns.org",
            "ghostdeveloperdownloads.duckdns.org",
            "127.0.0.1",
            "localhost",
            "testserver",
        ],
    )
    application.include_router(health.router)
    application.include_router(well_known.router)
    application.include_router(install_links.router)
    application.include_router(authorize.router)
    application.include_router(lease.router)
    application.include_router(downloads.router)
    application.include_router(admin.router)
    return application


app = create_app()
