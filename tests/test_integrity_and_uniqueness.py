from __future__ import annotations

import time


def admin_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def license_payload(owner: str) -> dict:
    return {
        "product": "hextunnel",
        "owner_telegram_id": owner,
        "owner_username": f"user-{owner}",
        "issued_by_telegram_id": owner,
        "reseller_name": f"Reseller {owner}",
        "expires_in_minutes": 240,
        "activation_limit": 1,
    }


def test_api_allows_multiple_keys_for_same_issuer(test_environment: dict) -> None:
    env = test_environment
    first = env["client"].post(
        "/api/v1/admin/licenses",
        headers=admin_headers(env["admin_token"]),
        json=license_payload("7001"),
    )
    assert first.status_code == 201, first.text

    second = env["client"].post(
        "/api/v1/admin/licenses",
        headers=admin_headers(env["admin_token"]),
        json=license_payload("7001"),
    )
    assert second.status_code == 201, second.text
    assert second.json()["id"] != first.json()["id"]
    assert second.json()["key"] != first.json()["key"]

    listed = env["client"].get(
        "/api/v1/admin/licenses?issued_by_telegram_id=7001",
        headers=admin_headers(env["admin_token"]),
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 2


def test_authorization_rejects_tampered_active_release(test_environment: dict) -> None:
    env = test_environment
    release = env["client"].post(
        "/api/v1/admin/releases",
        headers=admin_headers(env["admin_token"]),
        json={
            "product": "hextunnel",
            "version": "1.0.0-integrity",
            "relative_path": "hextunnel-1.0.0.tar.gz",
            "entrypoint": "bin/hextunnel-private-install",
            "activate": True,
        },
    )
    assert release.status_code == 201, release.text

    license_response = env["client"].post(
        "/api/v1/admin/licenses",
        headers=admin_headers(env["admin_token"]),
        json=license_payload("7002"),
    )
    assert license_response.status_code == 201, license_response.text

    package = env["settings"].release_root / "hextunnel-1.0.0.tar.gz"
    with package.open("ab") as handle:
        handle.write(b"tampered-after-registration")

    authorization = env["client"].post(
        "/api/v1/install/authorize",
        json={
            "key": license_response.json()["key"],
            "ip": "203.0.113.10",
            "nonce": "9" * 48,
            "timestamp": int(time.time()),
            "product": "hextunnel",
            "action": "install",
        },
    )
    assert authorization.status_code == 503, authorization.text
    assert authorization.json()["detail"] == (
        "La integridad del paquete publicado no coincide con la release registrada"
    )
