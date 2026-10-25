"""Tests for the HTTP mappers: options, errors, token counts and response shaping."""

from __future__ import annotations

from typing import Any

from app.api.mappers import (
    COMPLETION_ID_PREFIX,
    completion_options,
    error_for,
    to_chat_response,
    to_health_response,
    token_counts,
)
from app.core.errors import ApiError
from app.domain.router import RouteDecision, TaskType
from app.domain.schemas import ChatRequest, HealthResponse, ProviderStatus
from app.infrastructure.errors import LLMErrorKind


def _decision(provider: str = "ollama-coder", mode: str = "auto") -> RouteDecision:
    return RouteDecision(
        provider=provider,
        task_type=TaskType.GENERAL,
        mode=mode,
        reason="test reason",
    )


def _payload(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "chatcmpl-123",
        "created": 1_700_000_000,
        "model": "stub-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "hello"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }
    base.update(overrides)
    return base


def test_completion_options_returns_default_temperature() -> None:
    body = ChatRequest(messages=[{"role": "user", "content": "hola"}])
    assert completion_options(body) == {"temperature": 0.7}


def test_completion_options_includes_temperature() -> None:
    body = ChatRequest(
        messages=[{"role": "user", "content": "hola"}],
        temperature=0.3,
    )
    assert completion_options(body) == {"temperature": 0.3}


def test_completion_options_includes_max_tokens() -> None:
    body = ChatRequest(
        messages=[{"role": "user", "content": "hola"}],
        max_tokens=100,
    )
    assert completion_options(body) == {"temperature": 0.7, "max_tokens": 100}


def test_completion_options_includes_both() -> None:
    body = ChatRequest(
        messages=[{"role": "user", "content": "hola"}],
        temperature=0.5,
        max_tokens=200,
    )
    assert completion_options(body) == {"temperature": 0.5, "max_tokens": 200}


def test_completion_options_skips_none_values() -> None:
    body = ChatRequest(
        messages=[{"role": "user", "content": "hola"}],
        temperature=0.0,
        max_tokens=0,
    )
    assert completion_options(body) == {"temperature": 0.0, "max_tokens": 0}


def test_error_for_rate_limit_maps_to_quota_exhausted() -> None:
    error = error_for(LLMErrorKind.RATE_LIMIT)
    assert isinstance(error, ApiError)
    assert error.status_code == 503
    assert error.code == "quota_exhausted"


def test_error_for_auth_maps_to_provider_rejected() -> None:
    error = error_for(LLMErrorKind.AUTH)
    assert isinstance(error, ApiError)
    assert error.status_code == 502
    assert error.code == "provider_rejected"


def test_error_for_timeout_maps_to_provider_unavailable() -> None:
    error = error_for(LLMErrorKind.TIMEOUT)
    assert isinstance(error, ApiError)
    assert error.status_code == 500
    assert error.code == "provider_unavailable"


def test_error_for_unknown_maps_to_provider_unavailable() -> None:
    error = error_for(LLMErrorKind.UNKNOWN)
    assert isinstance(error, ApiError)
    assert error.status_code == 500
    assert error.code == "provider_unavailable"


def test_error_for_network_maps_to_provider_unavailable() -> None:
    error = error_for(LLMErrorKind.NETWORK)
    assert isinstance(error, ApiError)
    assert error.status_code == 500
    assert error.code == "provider_unavailable"


def test_token_counts_returns_zeros_when_usage_missing() -> None:
    assert token_counts({}) == (0, 0)


def test_token_counts_returns_zeros_when_usage_not_dict() -> None:
    assert token_counts({"usage": "invalid"}) == (0, 0)


def test_token_counts_returns_counts_from_payload() -> None:
    payload = {"usage": {"prompt_tokens": 12, "completion_tokens": 4}}
    assert token_counts(payload) == (12, 4)


def test_token_counts_treats_non_int_as_zero() -> None:
    payload = {"usage": {"prompt_tokens": "many", "completion_tokens": 4}}
    assert token_counts(payload) == (0, 4)


def test_to_chat_response_uses_payload_fields() -> None:
    payload = _payload()
    response = to_chat_response(payload, _decision())

    assert response.id == "chatcmpl-123"
    assert response.created == 1_700_000_000
    assert response.model == "stub-model"
    assert response.object == "chat.completion"
    assert response.usage == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    assert response.aquelarre.provider == "ollama-coder"
    assert response.aquelarre.mode == "auto"
    assert response.aquelarre.task_type == "general"


def test_to_chat_response_falls_back_to_decision_provider_when_model_missing() -> None:
    payload = _payload()
    payload.pop("model")
    response = to_chat_response(payload, _decision(provider="groq-llama"))

    assert response.model == "groq-llama"


def test_to_chat_response_generates_id_when_missing() -> None:
    payload = _payload()
    payload.pop("id")
    response = to_chat_response(payload, _decision())

    assert response.id.startswith(COMPLETION_ID_PREFIX)
    assert len(response.id) > len(COMPLETION_ID_PREFIX)


def test_to_chat_response_uses_current_time_when_created_missing() -> None:
    payload = _payload()
    payload.pop("created")
    response = to_chat_response(payload, _decision())

    assert isinstance(response.created, int)
    assert response.created > 0


def test_to_chat_response_keeps_choices_from_payload() -> None:
    payload = _payload()
    response = to_chat_response(payload, _decision())

    assert len(response.choices) == 1
    assert response.choices[0]["message"]["content"] == "hello"


def test_to_health_response_builds_provider_status() -> None:
    status = {
        "ollama-coder": {
            "tokens": 60.0,
            "capacity": 60,
            "failure_count": 0,
            "cooldown_seconds": 300.0,
            "circuit_open": False,
            "available": True,
        }
    }
    response = to_health_response(status)

    assert isinstance(response, HealthResponse)
    assert response.status == "ok"
    assert "ollama-coder" in response.providers
    assert isinstance(response.providers["ollama-coder"], ProviderStatus)
    assert response.providers["ollama-coder"].tokens == 60.0
    assert response.providers["ollama-coder"].available is True