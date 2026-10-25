"""HTTP endpoints. Transport only: every decision belongs to another layer."""

from __future__ import annotations

import logging
import time
from typing import Final, cast

from fastapi import APIRouter, Depends, Request, Response

from app.api.mappers import (
    completion_options,
    error_for,
    to_chat_response,
    to_health_response,
    token_counts,
)
from app.core.errors import quota_exhausted, streaming_unsupported
from app.core.security import sanitize_for_logs, verify_api_key
from app.domain.router import HybridRouter, RouteDecision
from app.domain.schemas import ChatRequest, ChatResponse, HealthResponse
from app.infrastructure import db
from app.infrastructure.errors import LLMError
from app.infrastructure.litellm_client import LiteLLMClient

logger: Final[logging.Logger] = logging.getLogger("app.api.routes")

PROVIDER_HEADER: Final[str] = "X-Aquelarre-Provider"
MODE_HEADER: Final[str] = "X-Aquelarre-Mode"

router: Final[APIRouter] = APIRouter()


@router.post("/v1/chat/completions", response_model=ChatResponse)
async def chat_completions(
    request: Request,
    body: ChatRequest,
    response: Response,
    _token: str = Depends(verify_api_key),
) -> ChatResponse:
    if body.stream:
        raise streaming_unsupported()

    hybrid_router: HybridRouter = request.app.state.hybrid_router
    client: LiteLLMClient = request.app.state.litellm_client
    messages = body.to_llm_messages()
    decision = _decide(hybrid_router, messages, body.model)

    started = time.monotonic()
    ok, result = await client.complete(
        decision.provider,
        messages,
        **completion_options(body),
    )
    latency_ms = int((time.monotonic() - started) * 1000)
    hybrid_router.report_result(decision.provider, ok)

    if not ok:
        error = cast(LLMError, result)
        logger.warning(
            "request failed on %s after %dms: %s",
            decision.provider,
            latency_ms,
            error.detail,
        )
        _record_usage(decision, tokens_in=0, tokens_out=0, latency_ms=latency_ms, ok=False)
        raise error_for(error.kind)

    payload = cast(dict, result)
    tokens_in, tokens_out = token_counts(payload)
    _record_usage(decision, tokens_in, tokens_out, latency_ms, ok=True)

    response.headers[PROVIDER_HEADER] = decision.provider
    response.headers[MODE_HEADER] = decision.mode
    return to_chat_response(payload, decision)


@router.get("/health")
def health(request: Request) -> HealthResponse:
    quota = request.app.state.quota
    return to_health_response(quota.status())


def _decide(
    hybrid_router: HybridRouter,
    messages: list[dict[str, str]],
    requested_model: str | None,
) -> RouteDecision:
    try:
        return hybrid_router.decide(messages, requested_model)
    except RuntimeError as exc:
        logger.warning("routing refused: %s", sanitize_for_logs(str(exc)))
        raise quota_exhausted() from None


def _record_usage(
    decision: RouteDecision,
    tokens_in: int,
    tokens_out: int,
    latency_ms: int,
    ok: bool,
) -> None:
    db.log_usage(
        provider=decision.provider,
        task_type=decision.task_type.value,
        mode=decision.mode,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=latency_ms,
        ok=ok,
    )