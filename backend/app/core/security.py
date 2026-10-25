"""Authentication for the local API and redaction of secrets in log output."""

from __future__ import annotations

import hmac
import re
from typing import Final

from fastapi import Header

from app.core.config import get_settings
from app.core.errors import unauthorized

REDACTED: Final[str] = "***REDACTED***"
BEARER_SCHEME: Final[str] = "bearer"

_BEARER_TOKEN: Final[re.Pattern[str]] = re.compile(rf"(?i)\b{BEARER_SCHEME}\s+([^\s]+)")
_AUTHORIZATION_HEADER: Final[re.Pattern[str]] = re.compile(
    r"(?i)\b(authorization\s*[:=]\s*)([^\s,;]+(?:\s+[^\s,;]+)?)"
)
# The leading boundary keeps substrings such as "task-done" from being redacted by mistake.
_SECRET_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\bsk-[A-Za-z0-9_\-]{3,}"),
    re.compile(r"\bgsk_[A-Za-z0-9_\-]{3,}"),
    re.compile(r"\bAIza[A-Za-z0-9_\-]{3,}"),
    re.compile(r"\bxai-[A-Za-z0-9_\-]{3,}"),
    re.compile(r"\bAQ\.[A-Za-z0-9_\-]{3,}"),
)


def sanitize_for_logs(text: str) -> str:
    """Replace anything that looks like an API key with a redaction marker.

    Covers the key shapes used by OpenAI-compatible providers, Groq, Google AI Studio and
    raw bearer tokens, so no secret can reach the log stream.

    Args:
        text: Arbitrary text headed for a log record.

    Returns:
        The same text with every credential-looking token redacted.
    """
    redacted = text
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(REDACTED, redacted)
    redacted = _AUTHORIZATION_HEADER.sub(rf"\g<1>{REDACTED}", redacted)
    return _BEARER_TOKEN.sub(f"Bearer {REDACTED}", redacted)


def extract_bearer_token(authorization: str | None) -> str | None:
    """Pull the credential out of an `Authorization` header value.

    Args:
        authorization: Raw header value, or `None` when the header is absent.

    Returns:
        The token without its scheme prefix, or `None` when the header is absent or malformed.
    """
    if not authorization:
        return None
    match = _BEARER_TOKEN.search(authorization)
    if match is None:
        return None
    return match.group(1)


def verify_api_key(authorization: str | None = Header(default=None)) -> str:
    """FastAPI dependency enforcing `Authorization: Bearer <AQUELARRE_API_KEY>`.

    The comparison uses `hmac.compare_digest` so the response time cannot be used to guess
    the key byte by byte.

    Args:
        authorization: Value of the request `Authorization` header.

    Returns:
        The presented bearer token.

    Raises:
        ApiError: 401 when the header is absent, malformed or does not match the configured key.
    """
    token = extract_bearer_token(authorization)
    if token is None:
        raise unauthorized()
    if not hmac.compare_digest(token, get_settings().aquelarre_api_key):
        raise unauthorized()
    return token
