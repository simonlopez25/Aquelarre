"""Credential verification and secret redaction."""

from __future__ import annotations

import hmac
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.security import REDACTED, sanitize_for_logs, verify_api_key

SECRET_KEYS = [
    "sk-abc123456789",
    "gsk_abc123456789",
    "AIzaSyExample123456",
    "xai-abc123456789",
    "AQ.ExampleTestKey12345678901234567890",
]


@pytest.mark.parametrize("secret", SECRET_KEYS)
def test_sanitize_for_logs_redacts_provider_keys(secret: str) -> None:
    assert secret not in sanitize_for_logs(f"api_key={secret}")
    assert REDACTED in sanitize_for_logs(f"Authorization: Bearer {secret}")


def test_sanitize_for_logs_redacts_bare_bearer_tokens() -> None:
    secret = uuid4().hex + uuid4().hex

    assert secret not in sanitize_for_logs(f"sent Bearer {secret} upstream")


def test_sanitize_for_logs_keeps_ordinary_text() -> None:
    text = "task-done disk-usage latency 120ms"

    assert sanitize_for_logs(text) == text


def test_verify_api_key_accepts_the_configured_key() -> None:
    token = get_settings().aquelarre_api_key

    assert verify_api_key(f"Bearer {token}") == token


@pytest.mark.parametrize(
    "authorization",
    [None, "Bearer wrong-key", "Basic dXNlcjpwYXNz", "random"],
)
def test_verify_api_key_rejects_other_credentials(authorization: str | None) -> None:
    with pytest.raises(ApiError) as raised:
        verify_api_key(authorization)

    assert raised.value.status_code == 401
    assert raised.value.detail["es"]
    assert raised.value.detail["en"]


def test_verify_api_key_uses_constant_time_comparison() -> None:
    token = get_settings().aquelarre_api_key

    with patch("app.core.security.hmac.compare_digest", wraps=hmac.compare_digest) as compared:
        verify_api_key(f"Bearer {token}")

    compared.assert_called_once_with(token, token)
