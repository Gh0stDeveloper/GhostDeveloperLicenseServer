from __future__ import annotations


def test_installer_link_uses_public_installer_domain(test_environment: dict) -> None:
    response = test_environment["client"].post(
        "/api/v1/admin/installer-links",
        headers={
            "Authorization": f"Bearer {test_environment['admin_token']}",
        },
        json={
            "expires_in_minutes": 15,
            "created_by_telegram_id": "987654321",
            "source_chat_id": "-1001234567890",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["url"].startswith(
        "https://ghostdeveloper.duckdns.org/i/"
    )
