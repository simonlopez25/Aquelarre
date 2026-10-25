"""Hybrid routing: classify the task, pick a provider, and enforce quotas.

This module is pure decision logic. It never opens a socket; `infrastructure` performs the call.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

from app.core.config import (
    GEMINI_PROVIDER,
    GROQ_PROVIDER,
    KILO_PROVIDER,
    OLLAMA_PROVIDER,
    OPENCODE_PROVIDER,
)
from app.core.security import sanitize_for_logs

logger: Final[logging.Logger] = logging.getLogger("app.router")

LONG_CONTEXT_CHARS: Final[int] = 6000
AUTO_MODE: Final[str] = "auto"
MANUAL_MODE: Final[str] = "manual"
DEFAULT_CAPACITY: Final[int] = 60
DEFAULT_REFILL_RATE: Final[float] = 1.0
DEFAULT_FAILURE_THRESHOLD: Final[int] = 3
DEFAULT_COOLDOWN_SECONDS: Final[float] = 300.0
NO_QUOTA_ERROR: Final[str] = "Ningún proveedor tiene cuota disponible en este momento"

_CODE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"```"
    r"|^\s*(?:def|class)\s+\w+"
    r"|^\s*import\s+[\w.]+"
    r"|^\s*from\s+[\w.]+\s+import\s+"
    r"|\bSELECT\b.+\bFROM\b"
    r"|</?[a-zA-Z][\w-]+/?>",
    re.IGNORECASE | re.MULTILINE,
)

_REASONING_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"paso a paso"
    r"|step by step"
    r"|explica(?:r)? por qu[ée]"
    r"|explain why"
    r"|demuestr\w*"
    r"|razona(?:r)?\b"
    r"|reason (?:about|through|why)",
    re.IGNORECASE,
)


class TaskType(StrEnum):
    """Task classes the router distinguishes when choosing a provider chain."""

    CODE = "code"
    REASONING = "reasoning"
    LONG_CONTEXT = "long_context"
    GENERAL = "general"


def _content_of(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    return ""


def classify_task(messages: list[dict]) -> TaskType:
    text = "\n".join(_content_of(message) for message in messages)
    if len(text) > LONG_CONTEXT_CHARS:
        return TaskType.LONG_CONTEXT
    if _CODE_PATTERN.search(text):
        return TaskType.CODE
    if _REASONING_PATTERN.search(text):
        return TaskType.REASONING
    return TaskType.GENERAL


@dataclass
class ProviderState:
    """Token bucket plus circuit breaker for a single provider.

    Attributes:
        name: Provider identifier shared with the LiteLLM model list.
        capacity: Bucket size in requests.
        refill_rate: Tokens restored per second.
        tokens: Tokens left in the bucket.
        last_refill: Unix timestamp of the last top-up.
        failure_count: Consecutive failures since the last success.
        failure_threshold: Failures that trip the breaker.
        cooldown_seconds: How long the breaker stays open.
        open_until: Unix timestamp until which the provider is forced open-circuit.
    """

    name: str
    capacity: int = DEFAULT_CAPACITY
    refill_rate: float = DEFAULT_REFILL_RATE
    tokens: float = DEFAULT_CAPACITY
    last_refill: float = field(default_factory=time.time)
    failure_count: int = 0
    failure_threshold: int = DEFAULT_FAILURE_THRESHOLD
    cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS
    open_until: float = 0.0

    def refill(self) -> None:
        now = time.time()
        elapsed = max(0.0, now - self.last_refill)
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

    def is_available(self) -> bool:
        if self.open_until > time.time():
            return False
        self.refill()
        return self.tokens >= 1.0

    def consume(self) -> bool:
        if not self.is_available():
            return False
        self.tokens -= 1.0
        return True

    def record_failure(self) -> None:
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self.open_until = time.time() + self.cooldown_seconds
            self.failure_count = 0

    def record_success(self) -> None:
        self.failure_count = 0
        self.open_until = 0.0


class QuotaManager:
    """Registry of provider buckets used to keep every chain within its limits.

    Attributes:
        states: Provider name mapped to its live bucket state.
    """

    def __init__(self, providers: list[str], cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS):
        self.states: dict[str, ProviderState] = {
            name: ProviderState(name=name, cooldown_seconds=cooldown_seconds) for name in providers
        }

    def pick_available(self, chain: list[str]) -> str | None:
        for name in chain:
            state = self.states.get(name)
            if state is not None and state.consume():
                return name
        return None

    def report(self, name: str, ok: bool) -> None:
        state = self.states.get(name)
        if state is None:
            return
        if ok:
            state.record_success()
        else:
            state.record_failure()

    def status(self) -> dict[str, dict]:
        snapshot: dict[str, dict] = {}
        for name, state in self.states.items():
            state.refill()
            snapshot[name] = {
                "tokens": round(state.tokens, 2),
                "capacity": state.capacity,
                "failure_count": state.failure_count,
                "cooldown_seconds": state.cooldown_seconds,
                "circuit_open": state.open_until > time.time(),
                "available": state.is_available(),
            }
        return snapshot


@dataclass
class RouteDecision:
    """Outcome of a routing decision.

    Attributes:
        provider: Provider selected to serve the request.
        task_type: Task class detected in the conversation.
        mode: `auto` or `manual`.
        reason: Short technical explanation of the choice.
    """

    provider: str
    task_type: TaskType
    mode: str
    reason: str


DEFAULT_CHAINS: Final[dict[TaskType, list[str]]] = {
    TaskType.CODE: [GROQ_PROVIDER, OPENCODE_PROVIDER, KILO_PROVIDER, OLLAMA_PROVIDER],
    TaskType.REASONING: [OPENCODE_PROVIDER, GEMINI_PROVIDER, KILO_PROVIDER, OLLAMA_PROVIDER],
    TaskType.LONG_CONTEXT: [GEMINI_PROVIDER, OPENCODE_PROVIDER, OLLAMA_PROVIDER],
    TaskType.GENERAL: [GROQ_PROVIDER, GEMINI_PROVIDER, KILO_PROVIDER, OLLAMA_PROVIDER],
}


class HybridRouter:
    """Choose a provider for a request, honouring manual overrides and active credentials.

    Attributes:
        quota: Manager holding the bucket state consulted on every decision.
        chains: Provider chains per task type, already limited to registered providers.
    """

    def __init__(
        self,
        quota: QuotaManager,
        chains: dict[TaskType, list[str]] | None = None,
    ) -> None:
        self.quota = quota
        self.chains = _limit_to_known_providers(chains or DEFAULT_CHAINS, quota.states)

    def decide(self, messages: list[dict], requested_model: str | None = None) -> RouteDecision:
        task_type = classify_task(messages)
        manual = self._decide_manual(task_type, requested_model)
        if manual is not None:
            return manual
        return self._decide_auto(task_type)

    def report_result(self, provider: str, ok: bool) -> None:
        self.quota.report(provider, ok)

    def _decide_manual(
        self,
        task_type: TaskType,
        requested_model: str | None,
    ) -> RouteDecision | None:
        if requested_model is None or requested_model not in self.quota.states:
            return None
        if self.quota.states[requested_model].consume():
            return RouteDecision(
                provider=requested_model,
                task_type=task_type,
                mode=MANUAL_MODE,
                reason=f"client selected {requested_model}",
            )
        logger.warning(
            "manual provider %s has no quota, falling back to auto",
            sanitize_for_logs(requested_model),
        )
        return None

    def _decide_auto(self, task_type: TaskType) -> RouteDecision:
        chain = self.chains.get(task_type, [])
        provider = self.quota.pick_available(chain)
        if provider is not None:
            return RouteDecision(
                provider=provider,
                task_type=task_type,
                mode=AUTO_MODE,
                reason=f"first available provider of the {task_type.value} chain",
            )
        return self._decide_last_resort(task_type)

    def _decide_last_resort(self, task_type: TaskType) -> RouteDecision:
        provider = self.quota.pick_available(list(self.quota.states))
        if provider is not None:
            return RouteDecision(
                provider=provider,
                task_type=task_type,
                mode=AUTO_MODE,
                reason="whole chain exhausted, used any provider with quota",
            )
        raise RuntimeError(NO_QUOTA_ERROR)


def _limit_to_known_providers(
    chains: dict[TaskType, list[str]],
    known: dict[str, ProviderState],
) -> dict[TaskType, list[str]]:
    """Drop providers that were never registered, i.e. those with no active credentials."""
    return {task: [name for name in chain if name in known] for task, chain in chains.items()}
