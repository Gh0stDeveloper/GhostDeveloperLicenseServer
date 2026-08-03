from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture()
def test_environment(tmp_path: Path):
    secret_dir = tmp_path / "secrets"
    release_root = tmp_path / "releases"
    public_dir = tmp_path / "public"
    secret_dir.mkdir()
    release_root.mkdir()
    public_dir.mkdir()

    admin_token = "admin-" + "a" * 64
    (secret_dir / "admin-token").write_text(admin_token, encoding="utf-8")
    (secret_dir / "hmac-secret").write_text("hmac-" + "b" * 64, encoding="utf-8")

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    private_path = secret_dir / "license-private.pem"
    public_path = public_dir / "license-public.pem"
    private_path.write_bytes(private_pem)
    public_path.write_bytes(public_pem)

    package_path = release_root / "hextunnel-1.0.0.tar.gz"
    with tarfile.open(package_path, "w:gz") as archive:
        payload = b"#!/usr/bin/env bash\necho installed\n"
        info = tarfile.TarInfo("bin/hextunnel-private-install")
        info.mode = 0o700
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))

    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        admin_token_file=secret_dir / "admin-token",
        hmac_secret_file=secret_dir / "hmac-secret",
        private_key_file=private_path,
        public_key_file=public_path,
        release_root=release_root,
        download_base_url="https://ghostdeveloperdownloads.duckdns.org",
        public_install_url="https://ghostdeveloper.duckdns.org/install.sh",
        installer_link_base_url="https://ghostdeveloper.duckdns.org/i",
        max_clock_skew_seconds=300,
        nonce_ttl_seconds=600,
        download_ttl_seconds=300,
        lease_ttl_seconds=86400,
        enforce_source_ip=False,
        docs_enabled=True,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        yield {
            "client": client,
            "settings": settings,
            "admin_token": admin_token,
            "private_key": private_key,
            "public_key": private_key.public_key(),
            "package_path": package_path,
        }
