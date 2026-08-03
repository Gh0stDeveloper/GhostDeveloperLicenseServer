from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str
    database_url: str
    admin_token_file: Path
    hmac_secret_file: Path
    private_key_file: Path
    public_key_file: Path
    release_root: Path
    download_base_url: str
    public_install_url: str
    installer_link_base_url: str
    max_clock_skew_seconds: int
    nonce_ttl_seconds: int
    download_ttl_seconds: int
    lease_ttl_seconds: int
    enforce_source_ip: bool
    docs_enabled: bool

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            environment=os.getenv("GHOST_LICENSE_ENVIRONMENT", "production"),
            database_url=os.getenv(
                "GHOST_LICENSE_DATABASE_URL",
                "sqlite:////var/lib/ghostdeveloper-license/license.db",
            ),
            admin_token_file=Path(
                os.getenv(
                    "GHOST_LICENSE_ADMIN_TOKEN_FILE",
                    "/etc/ghostdeveloper-license/secrets/admin-token",
                )
            ),
            hmac_secret_file=Path(
                os.getenv(
                    "GHOST_LICENSE_HMAC_SECRET_FILE",
                    "/etc/ghostdeveloper-license/secrets/key-hmac-secret",
                )
            ),
            private_key_file=Path(
                os.getenv(
                    "GHOST_LICENSE_PRIVATE_KEY_FILE",
                    "/etc/ghostdeveloper-license/secrets/license-private.pem",
                )
            ),
            public_key_file=Path(
                os.getenv(
                    "GHOST_LICENSE_PUBLIC_KEY_FILE",
                    "/var/www/ghostdeveloper/.well-known/hextunnel-license-public.pem",
                )
            ),
            release_root=Path(
                os.getenv(
                    "GHOST_LICENSE_RELEASE_ROOT",
                    "/var/lib/ghostdeveloper-license/releases",
                )
            ),
            download_base_url=os.getenv(
                "GHOST_LICENSE_DOWNLOAD_BASE_URL",
                "https://ghostdeveloperdownloads.duckdns.org",
            ).rstrip("/"),
            public_install_url=os.getenv(
                "GHOST_LICENSE_PUBLIC_INSTALL_URL",
                "https://ghostdeveloper.duckdns.org/install.sh",
            ),
            installer_link_base_url=os.getenv(
                "GHOST_LICENSE_INSTALLER_LINK_BASE_URL",
                "https://ghostdeveloperkeys.duckdns.org/i",
            ).rstrip("/"),
            max_clock_skew_seconds=int(
                os.getenv("GHOST_LICENSE_MAX_CLOCK_SKEW_SECONDS", "300")
            ),
            nonce_ttl_seconds=int(os.getenv("GHOST_LICENSE_NONCE_TTL_SECONDS", "600")),
            download_ttl_seconds=int(
                os.getenv("GHOST_LICENSE_DOWNLOAD_TTL_SECONDS", "300")
            ),
            lease_ttl_seconds=int(os.getenv("GHOST_LICENSE_LEASE_TTL_SECONDS", "86400")),
            enforce_source_ip=_env_bool("GHOST_LICENSE_ENFORCE_SOURCE_IP", True),
            docs_enabled=_env_bool("GHOST_LICENSE_DOCS_ENABLED", False),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
