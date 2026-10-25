"""Translation between provider payloads and the Aquelarre HTTP contract."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Final
from uuid import uuid4

from app.core.errors import (
    ApiError,
    provider_rejected,
    provider_unavailable,
    quota_exhausted,
)
from app.domain.router import RouteDecision
from app.domain.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    ProviderStatus,
    RouteInfo,
)
from app.infrastructure.errors import LLMErrorKind

COMPLETION_ID_PREFIX: Final[str] = "chatcmpl-"

# Only rate limits and credentials have a defined answer; everything else is a generic 500.
_ERROR_BY_KIND: Final[dict[LLMErrorKind, Callable[[], ApiError]]] = {
    LLMErrorKind.RATE_LIMIT: quota_exhausted,
    LLMErrorKind.AUTH: provider_rejected,
}


def completion_options(body: ChatRequest) -> dict[str, Any]:
    options: dict[str, Any] = {}
    if body.temperature is not None:
        options["temperature"] = body.temperature
    if body.max_tokens is not None:
        options["max_tokens"] = body.max_tokens
    return options


def error_for(kind: LLMErrorKind) -> ApiError:
    return _ERROR_BY_KIND.get(kind, provider_unavailable)()


def to_health_response(status: dict[str, dict]) -> HealthResponse:
    return HealthResponse(
        status="ok",
        providers={name: ProviderStatus(**values) for name, values in status.items()},
    )


def token_counts(payload: dict[str, Any]) -> tuple[int, int]:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return 0, 0
    return _as_int(usage.get("prompt_tokens")), _as_int(usage.get("completion_tokens"))


def to_chat_response(payload: dict[str, Any], decision: RouteDecision) -> ChatResponse:
    return ChatResponse(
        id=str(payload.get("id") or f"{COMPLETION_ID_PREFIX}{uuid4().hex}"),
        created=int(payload.get("created") or time.time()),
        model=str(payload.get("model") or decision.provider),
        choices=list(payload.get("choices") or []),
        usage=dict(payload.get("usage") or {}),
        aquelarre=RouteInfo(
            provider=decision.provider,
            task_type=decision.task_type.value,
            mode=decision.mode,
            reason=decision.reason,
        ),
    )


def _as_int(value: Any) -> int:
    return value if isinstance(value, int) else 0