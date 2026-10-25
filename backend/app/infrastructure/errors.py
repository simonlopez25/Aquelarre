"""Classified completion failures.

Kept apart from the client so that reporting a failure never requires loading LiteLLM.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class LLMErrorKind(StrEnum):
    """Failure classes the HTTP layer turns into status codes."""

    RATE_LIMIT = "rate_limit"
    AUTH = "auth"
    TIMEOUT = "timeout"
    NETWORK = "network"
    UNKNOWN = "unknown"


@dataclass
class LLMError:
    """A completion failure that is safe to write to the logs.

    Attributes:
        kind: Class used to choose the HTTP status.
        detail: Redacted description, for internal logs only.
    """

    kind: LLMErrorKind
    detail: str