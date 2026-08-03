from __future__ import annotations

import time

import pytest
from pydantic import ValidationError

from app.schemas import AuthorizeRequest, normalize_license_key


CANONICAL_KEY = "HT-A166-CB37-0FC1-9DBA-AC7D-EBAA"


def request_with_key(key: str) -> AuthorizeRequest:
    return AuthorizeRequest(
        key=key,
        ip="203.0.113.10",
        nonce="a" * 48,
        timestamp=int(time.time()),
        product="hextunnel",
        action="install",
    )


@pytest.mark.parametrize(
    "copied_key",
    [
        CANONICAL_KEY,
        CANONICAL_KEY.lower(),
        f"  {CANONICAL_KEY}\n",
        CANONICAL_KEY.replace("-", "\u2011"),
        CANONICAL_KEY.replace("-", "\u2013"),
        CANONICAL_KEY.replace("-", "\uff0d"),
        "HT-A166-CB37\u200b-0FC1-9DBA-AC7D-EBAA",
        "\ufeffHT-A166-CB37-0FC1-9DBA-AC7D-EBAA\ufeff",
    ],
)
def test_authorize_request_normalizes_copied_key(copied_key: str) -> None:
    assert normalize_license_key(copied_key) == CANONICAL_KEY
    assert request_with_key(copied_key).key == CANONICAL_KEY


@pytest.mark.parametrize(
    "invalid_key",
    [
        "HT-A166-CB37-0FC1-9DBA-AC7D",
        "HT-A166-CB37-0FC1-9DBA-AC7D-EBAZ",
        "NOT-A-HEX-TUNNEL-KEY",
        "",
    ],
)
def test_authorize_request_rejects_invalid_key_format(invalid_key: str) -> None:
    with pytest.raises(ValidationError):
        request_with_key(invalid_key)
