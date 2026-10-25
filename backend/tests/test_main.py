"""HTTP contract of the application, with LiteLLM replaced by a stub."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from app.domain.router import HybridRouter
from app.infrastructure.errors import LLMError, LLMErrorKind
from app.infrastructure.litellm_client import LiteLLMClient

ENDPOINT = "/v1/chat/completions"
BODY: dict[str, Any] = {"messages": [{"role": "user", "content": "hola"}]}


def _post(
    client: TestClient,
    headers: dict[str, str],
    body: dict[str, Any] | None = None,
) -> Response:
    return client.post(ENDPOINT, headers=headers, json=body or BODY)


def test_missing_api_key_returns_401(client: TestClient) -> None:
    response = client.post(ENDPOINT, json=BODY)

    assert response.status_code == 401
    detail = response.json()["detail"]
    assert detail["code"] == "unauthorized"
    assert detail["es"] and detail["en"]


def test_wrong_api_key_returns_401(client: TestClient) -> None:
    response = _post(client, {"Authorization": "Bearer not-the-key"})

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "unauthorized"


def test_success_returns_openai_body_and_routing_headers(
    client: TestClient,
    auth_headers: dict[str, str],
    mock_completion: Any,
) -> None:
    response = _post(client, auth_headers)

    assert response.status_code == 200
    assert response.headers["X-Aquelarre-Provider"]
    assert response.headers["X-Aquelarre-Mode"] == "auto"

    body = response.json()
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["content"] == "hello from the stub"
    assert body["aquelarre"]["mode"] == "auto"
    assert body["aquelarre"]["provider"] == response.headers["X-Aquelarre-Provider"]


def test_forcing_a_provider_reports_manual_mode(
    client: TestClient,
    auth_headers: dict[str, str],
    mock_completion: Any,
) -> None:
    response = _post(client, auth_headers, {**BODY, "model": "ollama-coder"})

    assert response.status_code == 200
    assert response.headers["X-Aquelarre-Mode"] == "manual"
    assert response.headers["X-Aquelarre-Provider"] == "ollama-coder"


def test_no_quota_returns_503(client: TestClient, auth_headers: dict[str, str]) -> None:
    with patch.object(HybridRouter, "decide", side_effect=RuntimeError("no quota")):
        response = _post(client, auth_headers)

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "quota_exhausted"
    assert detail["es"] and detail["en"]


@pytest.mark.parametrize(
    ("kind", "status", "code"),
    [
        (LLMErrorKind.RATE_LIMIT, 503, "quota_exhausted"),
        (LLMErrorKind.AUTH, 502, "provider_rejected"),
        (LLMErrorKind.TIMEOUT, 500, "provider_unavailable"),
        (LLMErrorKind.UNKNOWN, 500, "provider_unavailable"),
    ],
)
def test_provider_failures_map_to_bilingual_errors(
    client: TestClient,
    auth_headers: dict[str, str],
    mock_completion: Any,
    kind: LLMErrorKind,
    status: int,
    code: str,
) -> None:
    mock_completion.complete.return_value = (False, LLMError(kind=kind, detail="internal detail"))

    response = _post(client, auth_headers)

    assert response.status_code == status
    detail = response.json()["detail"]
    assert detail["code"] == code
    assert "internal detail" not in str(detail)


def test_streaming_is_rejected_with_a_bilingual_400(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = _post(client, auth_headers, {**BODY, "stream": True})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "streaming_unsupported"


def test_health_needs_no_api_key_and_lists_providers(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "ollama-coder" in payload["providers"]


class _SlowRouter:
    async def acompletion(self, **kwargs: Any) -> dict[str, Any]:
        await asyncio.sleep(5)
        return {}


async def test_complete_reports_timeout_without_touching_the_network() -> None:
    client = LiteLLMClient(router=_SlowRouter(), timeout=0.01)

    ok, result = await client.complete("groq-llama", [{"role": "user", "content": "hola"}])

    assert ok is False
    assert isinstance(result, LLMError)
    assert result.kind is LLMErrorKind.TIMEOUT
