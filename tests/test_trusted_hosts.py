from __future__ import annotations


def test_public_installer_host_is_allowed(test_environment: dict) -> None:
    client = test_environment["client"]

    public_response = client.get(
        "/health",
        headers={"host": "ghostdeveloper.duckdns.org"},
    )
    assert public_response.status_code == 200

    rejected_response = client.get(
        "/health",
        headers={"host": "untrusted.example"},
    )
    assert rejected_response.status_code == 400
