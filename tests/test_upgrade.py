from __future__ import annotations

import time


def admin_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_upgrade_reuses_bound_activation(test_environment: dict) -> None:
    env = test_environment
    release = env["client"].post(
        "/api/v1/admin/releases",
        headers=admin_headers(env["admin_token"]),
        json={
            "product": "hextunnel",
            "version": "1.0.1",
            "relative_path": "hextunnel-1.0.0.tar.gz",
            "entrypoint": "bin/hextunnel-private-install",
            "activate": True,
        },
    )
    assert release.status_code == 201, release.text

    created = env["client"].post(
        "/api/v1/admin/licenses",
        headers=admin_headers(env["admin_token"]),
        json={
            "product": "hextunnel",
            "owner_telegram_id": "123456789",
            "expires_in_minutes": 240,
            "activation_limit": 1,
        },
    )
    assert created.status_code == 201, created.text
    key = created.json()["key"]

    install = env["client"].post(
        "/api/v1/install/authorize",
        json={
            "key": key,
            "ip": "203.0.113.10",
            "nonce": "1" * 48,
            "timestamp": int(time.time()),
            "product": "hextunnel",
            "action": "install",
        },
    )
    assert install.status_code == 200, install.text

    upgrade = env["client"].post(
        "/api/v1/install/authorize",
        json={
            "key": key,
            "ip": "203.0.113.10",
            "nonce": "2" * 48,
            "timestamp": int(time.time()),
            "product": "hextunnel",
            "action": "upgrade",
        },
    )
    assert upgrade.status_code == 200, upgrade.text
    payload = upgrade.json()
    assert payload["status"] == "valid"
    assert payload["subject"] == "203.0.113.10"
    assert payload["version"] == "1.0.1"
    assert payload["activation_token"] != install.json()["activation_token"]

    listed = env["client"].get(
        "/api/v1/admin/licenses",
        headers=admin_headers(env["admin_token"]),
    )
    assert listed.status_code == 200
    assert listed.json()["items"][0]["activation_count"] == 1
