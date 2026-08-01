from __future__ import annotations

import base64
import time
from urllib.parse import urlparse

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

from app.signing import canonical_authorization, canonical_lease


def admin_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def register_release(env: dict) -> dict:
    response = env["client"].post(
        "/api/v1/admin/releases",
        headers=admin_headers(env["admin_token"]),
        json={
            "product": "hextunnel",
            "version": "1.0.0",
            "relative_path": "hextunnel-1.0.0.tar.gz",
            "entrypoint": "bin/hextunnel-private-install",
            "activate": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_license(env: dict, **overrides) -> dict:
    payload = {
        "product": "hextunnel",
        "owner_telegram_id": "123456789",
        "owner_username": "cliente",
        "expires_in_minutes": 240,
        "activation_limit": 1,
    }
    payload.update(overrides)
    response = env["client"].post(
        "/api/v1/admin/licenses",
        headers=admin_headers(env["admin_token"]),
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


def authorize(env: dict, key: str, nonce: str = "a" * 48) -> dict:
    response = env["client"].post(
        "/api/v1/install/authorize",
        json={
            "key": key,
            "ip": "203.0.113.10",
            "nonce": nonce,
            "timestamp": int(time.time()),
            "product": "hextunnel",
            "action": "install",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_health_and_admin_authentication(test_environment: dict) -> None:
    client = test_environment["client"]
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "online"

    unauthorized = client.get("/api/v1/admin/licenses")
    assert unauthorized.status_code == 401

    authorized = client.get(
        "/api/v1/admin/licenses",
        headers=admin_headers(test_environment["admin_token"]),
    )
    assert authorized.status_code == 200
    assert authorized.json()["total"] == 0


def test_license_authorization_signature_download_and_lease(test_environment: dict) -> None:
    env = test_environment
    release = register_release(env)
    license_data = create_license(env)
    assert license_data["key"].startswith("HT-")
    assert release["sha256"]

    authorization = authorize(env, license_data["key"])
    assert authorization["status"] == "valid"
    assert authorization["subject"] == "203.0.113.10"
    assert authorization["package_sha256"] == release["sha256"]

    canonical = canonical_authorization(
        status=authorization["status"],
        expires_at=authorization["expires_at"].replace("+00:00", "Z"),
        download_expires_at=authorization["download_expires_at"].replace("+00:00", "Z"),
        nonce=authorization["nonce"],
        subject=authorization["subject"],
        version=authorization["version"],
        download_url=authorization["download_url"],
        package_sha256=authorization["package_sha256"],
        entrypoint=authorization["entrypoint"],
    )
    env["public_key"].verify(
        base64.b64decode(authorization["signature"]),
        canonical.encode("utf-8"),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )

    download_path = urlparse(authorization["download_url"]).path
    download = env["client"].get(download_path)
    assert download.status_code == 200
    assert download.content.startswith(b"\x1f\x8b")
    reused = env["client"].get(download_path)
    assert reused.status_code == 404

    lease = env["client"].post(
        "/api/v1/licenses/lease",
        json={
            "activation_token": authorization["activation_token"],
            "ip": "203.0.113.10",
            "product": "hextunnel",
        },
    )
    assert lease.status_code == 200, lease.text
    lease_data = lease.json()
    canonical_value = canonical_lease(
        status=lease_data["status"],
        lease_expires_at=lease_data["lease_expires_at"].replace("+00:00", "Z"),
        subject=lease_data["subject"],
        product=lease_data["product"],
        activation_id=lease_data["activation_id"],
    )
    env["public_key"].verify(
        base64.b64decode(lease_data["signature"]),
        canonical_value.encode("utf-8"),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )


def test_nonce_replay_and_revocation(test_environment: dict) -> None:
    env = test_environment
    register_release(env)
    license_data = create_license(env)
    nonce = "b" * 48
    authorize(env, license_data["key"], nonce=nonce)

    replay = env["client"].post(
        "/api/v1/install/authorize",
        json={
            "key": license_data["key"],
            "ip": "203.0.113.10",
            "nonce": nonce,
            "timestamp": int(time.time()),
            "product": "hextunnel",
            "action": "install",
        },
    )
    assert replay.status_code == 409

    revoked = env["client"].post(
        f"/api/v1/admin/licenses/{license_data['id']}/revoke",
        headers=admin_headers(env["admin_token"]),
        json={"reason": "Prueba de revocación"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"

    denied = env["client"].post(
        "/api/v1/install/authorize",
        json={
            "key": license_data["key"],
            "ip": "203.0.113.10",
            "nonce": "c" * 48,
            "timestamp": int(time.time()),
            "product": "hextunnel",
            "action": "install",
        },
    )
    assert denied.status_code == 403


def test_rejects_stale_timestamp_and_unsafe_release_path(test_environment: dict) -> None:
    env = test_environment
    unsafe = env["client"].post(
        "/api/v1/admin/releases",
        headers=admin_headers(env["admin_token"]),
        json={
            "product": "hextunnel",
            "version": "1.0.0",
            "relative_path": "../secret.tar.gz",
        },
    )
    assert unsafe.status_code == 422

    register_release(env)
    license_data = create_license(env)
    stale = env["client"].post(
        "/api/v1/install/authorize",
        json={
            "key": license_data["key"],
            "ip": "203.0.113.10",
            "nonce": "d" * 48,
            "timestamp": int(time.time()) - 3600,
            "product": "hextunnel",
            "action": "install",
        },
    )
    assert stale.status_code == 400


def test_reset_activation_allows_reactivation(test_environment: dict) -> None:
    env = test_environment
    register_release(env)
    license_data = create_license(env)
    authorize(env, license_data["key"], nonce="e" * 48)

    reset = env["client"].post(
        f"/api/v1/admin/licenses/{license_data['id']}/reset-activation",
        headers=admin_headers(env["admin_token"]),
        json={"reason": "Cambio autorizado de VPS"},
    )
    assert reset.status_code == 200, reset.text
    assert reset.json()["activation_count"] == 0

    second = env["client"].post(
        "/api/v1/install/authorize",
        json={
            "key": license_data["key"],
            "ip": "198.51.100.25",
            "nonce": "f" * 48,
            "timestamp": int(time.time()),
            "product": "hextunnel",
            "action": "install",
        },
    )
    assert second.status_code == 200, second.text
    assert second.json()["subject"] == "198.51.100.25"
