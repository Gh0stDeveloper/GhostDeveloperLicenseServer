from __future__ import annotations


def admin_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_reseller_name_is_normalized_and_control_characters_are_rejected(
    test_environment: dict,
) -> None:
    env = test_environment
    normalized = env["client"].post(
        "/api/v1/admin/licenses",
        headers=admin_headers(env["admin_token"]),
        json={
            "product": "hextunnel",
            "issued_by_telegram_id": "100",
            "reseller_name": "  Reseller   Norte  ",
            "expires_in_minutes": 60,
        },
    )
    assert normalized.status_code == 201, normalized.text
    assert normalized.json()["reseller_name"] == "Reseller Norte"

    for unsafe in ("Reseller\nFalso", "<b>Reseller</b>", "Reseller\u001b[31m"):
        response = env["client"].post(
            "/api/v1/admin/licenses",
            headers=admin_headers(env["admin_token"]),
            json={
                "product": "hextunnel",
                "issued_by_telegram_id": "100",
                "reseller_name": unsafe,
                "expires_in_minutes": 60,
            },
        )
        assert response.status_code == 422, response.text
