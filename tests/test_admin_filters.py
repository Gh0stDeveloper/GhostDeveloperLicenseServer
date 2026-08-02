from __future__ import annotations

import io
import tarfile


def admin_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_license(env: dict, owner: str, minutes: int = 240) -> dict:
    response = env["client"].post(
        "/api/v1/admin/licenses",
        headers=admin_headers(env["admin_token"]),
        json={
            "product": "hextunnel",
            "owner_telegram_id": owner,
            "owner_username": f"user-{owner}",
            "expires_in_minutes": minutes,
            "activation_limit": 1,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def register_release(env: dict, version: str, filename: str, activate: bool) -> dict:
    path = env["settings"].release_root / filename
    with tarfile.open(path, "w:gz") as archive:
        payload = b"#!/usr/bin/env bash\necho installed\n"
        info = tarfile.TarInfo("bin/hextunnel-private-install")
        info.mode = 0o700
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    response = env["client"].post(
        "/api/v1/admin/releases",
        headers=admin_headers(env["admin_token"]),
        json={
            "product": "hextunnel",
            "version": version,
            "relative_path": filename,
            "entrypoint": "bin/hextunnel-private-install",
            "activate": activate,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_license_list_filters_by_owner_and_active_state(test_environment: dict) -> None:
    env = test_environment
    first = create_license(env, "1001")
    create_license(env, "1002")
    revoked = env["client"].post(
        f"/api/v1/admin/licenses/{first['id']}/revoke",
        headers=admin_headers(env["admin_token"]),
        json={"reason": "Prueba de filtro"},
    )
    assert revoked.status_code == 200, revoked.text

    owner_result = env["client"].get(
        "/api/v1/admin/licenses?product=hextunnel&owner_telegram_id=1002",
        headers=admin_headers(env["admin_token"]),
    )
    assert owner_result.status_code == 200, owner_result.text
    assert owner_result.json()["total"] == 1
    assert owner_result.json()["items"][0]["owner_telegram_id"] == "1002"

    active_result = env["client"].get(
        "/api/v1/admin/licenses?product=hextunnel&owner_telegram_id=1001&active_only=true",
        headers=admin_headers(env["admin_token"]),
    )
    assert active_result.status_code == 200, active_result.text
    assert active_result.json()["total"] == 0


def test_existing_release_can_be_promoted_without_reupload(test_environment: dict) -> None:
    env = test_environment
    first = register_release(env, "1.0.1", "hextunnel-1.0.1.tar.gz", True)
    second = register_release(env, "1.0.2", "hextunnel-1.0.2.tar.gz", False)
    assert first["active"] is True
    assert second["active"] is False

    promoted = env["client"].post(
        f"/api/v1/admin/releases/{second['id']}/activate",
        headers=admin_headers(env["admin_token"]),
        json={"reason": "Promoción de prueba"},
    )
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["active"] is True

    releases = env["client"].get(
        "/api/v1/admin/releases?product=hextunnel",
        headers=admin_headers(env["admin_token"]),
    )
    assert releases.status_code == 200, releases.text
    by_version = {item["version"]: item for item in releases.json()}
    assert by_version["1.0.1"]["active"] is False
    assert by_version["1.0.2"]["active"] is True
