"""Routing decisions: classification, manual overrides, chain failover and quotas."""

from __future__ import annotations

import time

import pytest

from app.domain.router import (
    DEFAULT_CHAINS,
    NO_QUOTA_ERROR,
    HybridRouter,
    QuotaManager,
    TaskType,
    classify_task,
)


def _messages(content: str) -> list[dict[str, str]]:
    return [{"role": "user", "content": content}]


def _exhaust(quota: QuotaManager, name: str) -> None:
    """Empty a bucket and freeze its clock so a slow test run cannot refill it."""
    state = quota.states[name]
    state.tokens = 0.0
    state.last_refill = time.time()


def test_classify_detects_code_block() -> None:
    messages = _messages("```python\ndef add(a, b):\n    return a + b\n```")
    assert classify_task(messages) is TaskType.CODE


def test_classify_detects_reasoning_in_spanish() -> None:
    assert classify_task(_messages("Explica paso a paso por qué sube la temperatura")) is (
        TaskType.REASONING
    )


def test_classify_detects_long_context() -> None:
    assert classify_task(_messages("a" * 6001)) is TaskType.LONG_CONTEXT


def test_classify_defaults_to_general() -> None:
    assert classify_task(_messages("Hola, ¿qué tal estás?")) is TaskType.GENERAL


def test_classify_does_not_mistake_plain_english_for_code() -> None:
    messages = _messages("from the start and if a < b then c > d")
    assert classify_task(messages) is TaskType.GENERAL


def test_manual_override_is_respected_when_quota_exists() -> None:
    router = HybridRouter(QuotaManager(["ollama-coder", "groq-llama"]))

    decision = router.decide(_messages("hola"), requested_model="ollama-coder")

    assert decision.provider == "ollama-coder"
    assert decision.mode == "manual"


def test_manual_override_falls_back_to_auto_without_quota() -> None:
    quota = QuotaManager(["ollama-coder", "groq-llama"])
    _exhaust(quota, "ollama-coder")

    decision = HybridRouter(quota).decide(_messages("hola"), requested_model="ollama-coder")

    assert decision.mode == "auto"
    assert decision.provider == "groq-llama"


def test_chain_falls_over_when_the_first_provider_is_exhausted() -> None:
    quota = QuotaManager(["groq-llama", "ollama-coder"])
    _exhaust(quota, "groq-llama")

    decision = HybridRouter(quota).decide(_messages("```python\nprint(1)\n```"))

    assert decision.provider == "ollama-coder"
    assert decision.mode == "auto"


def test_chains_are_limited_to_registered_providers() -> None:
    router = HybridRouter(QuotaManager(["ollama-coder"]))

    assert set(router.chains) == set(DEFAULT_CHAINS)
    for chain in router.chains.values():
        assert chain == ["ollama-coder"]


def test_raises_when_no_provider_has_quota() -> None:
    quota = QuotaManager(["groq-llama"])
    _exhaust(quota, "groq-llama")

    with pytest.raises(RuntimeError, match=NO_QUOTA_ERROR):
        HybridRouter(quota).decide(_messages("hola"))


def test_circuit_opens_after_consecutive_failures() -> None:
    quota = QuotaManager(["ollama-coder"], cooldown_seconds=60)
    state = quota.states["ollama-coder"]

    for _ in range(state.failure_threshold):
        quota.report("ollama-coder", ok=False)

    assert state.open_until > time.time()
    assert state.is_available() is False


def test_report_ignores_unknown_providers() -> None:
    QuotaManager(["ollama-coder"]).report("not-registered", ok=False)


def test_status_reports_every_provider_as_json_safe_data() -> None:
    status = QuotaManager(["ollama-coder", "groq-llama"]).status()

    assert set(status) == {"ollama-coder", "groq-llama"}
    assert status["ollama-coder"]["available"] is True
    assert status["ollama-coder"]["circuit_open"] is False
