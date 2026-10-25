"""Exception-free wrapper around the LiteLLM router.

LiteLLM owns the network call and its own retry/failover chain. This module owns the boundary:
whatever happens on the wire comes back as a classified value, never as a raw exception.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

import litellm
import yaml

from app.core.config import Settings, get_settings, resolve_env_references
from app.core.security import sanitize_for_logs

logger: Final[logging.Logger] = logging.getLogger("app.litellm")

DEFAULT_CONFIG_PATH: Final[Path] = (
    Path(__file__).resolve().parents[2] / "config" / "litellm_config.yaml"
)
DEFAULT_TIMEOUT_SECONDS: Final[float] = 120.0
DEFAULT_ROUTING_STRATEGY: Final[str] = "simple-shuffle"
DEFAULT_NUM_RETRIES: Final[int] = 1
DEFAULT_MODEL_NAME: Final[str] = "unknown"


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


class LiteLLMClient:
    """Completes requests through a preconfigured `litellm.Router` without raising.

    Attributes:
        timeout: Seconds after which a request is abandoned and reported as a timeout.
    """

    def __init__(self, router: litellm.Router, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self._router = router
        self.timeout = timeout

    async def complete(
        self,
        model: str,
        messages: list[dict],
        **kwargs: Any,
    ) -> tuple[bool, dict[str, Any] | LLMError]:
        """Ask the provider chain for a completion.

        Args:
            model: LiteLLM model name, i.e. the Aquelarre provider identifier.
            messages: Conversation as plain `{"role": ..., "content": ...}` dictionaries.
            kwargs: Completion options such as `temperature` or `max_tokens`.

        Returns:
            `(True, payload)` on success, or `(False, LLMError)` describing the failure.
        """
        try:
            response = await asyncio.wait_for(
                self._router.acompletion(model=model, messages=messages, **kwargs),
                timeout=self.timeout,
            )
        except litellm.exceptions.RateLimitError as exc:
            return False, _classify(LLMErrorKind.RATE_LIMIT, exc)
        except litellm.exceptions.Timeout as exc:
            return False, _classify(LLMErrorKind.TIMEOUT, exc)
        except (
            litellm.exceptions.AuthenticationError,
            litellm.exceptions.PermissionDeniedError,
        ) as exc:
            return False, _classify(LLMErrorKind.AUTH, exc)
        except litellm.exceptions.APIConnectionError as exc:
            return False, _classify(LLMErrorKind.NETWORK, exc)
        except TimeoutError:
            return False, _timeout_error(self.timeout)
        except litellm.exceptions.APIError as exc:
            return False, _classify(LLMErrorKind.UNKNOWN, exc)
        except Exception as exc:
            # Providers raise errors outside LiteLLM's APIError hierarchy; the transport layer
            # must still receive a classified failure instead of a raw traceback.
            return False, _classify(LLMErrorKind.UNKNOWN, exc)

        logger.info("completion served by %s", sanitize_for_logs(model))
        return True, _as_dict(response)


def _timeout_error(timeout: float) -> LLMError:
    detail = f"no answer within {timeout:g}s"
    logger.warning("completion failed (%s): %s", LLMErrorKind.TIMEOUT.value, detail)
    return LLMError(kind=LLMErrorKind.TIMEOUT, detail=detail)


def _classify(kind: LLMErrorKind, exc: BaseException) -> LLMError:
    detail = sanitize_for_logs(f"{type(exc).__name__}: {exc}")
    logger.warning("completion failed (%s): %s", kind.value, detail)
    return LLMError(kind=kind, detail=detail)


def _as_dict(response: Any) -> dict[str, Any]:
    """Return the upstream completion as a plain dictionary."""
    if isinstance(response, dict):
        return response
    dump = getattr(response, "model_dump", None)
    if callable(dump):
        return dump()
    legacy = getattr(response, "dict", None)
    if callable(legacy):
        return legacy()
    raise TypeError(f"unexpected completion payload of type {type(response).__name__}")


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _resolve_models(entries: list[dict], settings: Settings) -> tuple[list[dict], set[str]]:
    """Resolve placeholders and drop the providers whose credentials are absent.

    Args:
        entries: Raw `model_list` block from the YAML.
        settings: Supplies fallbacks for placeholders that have a settings default.

    Returns:
        The usable model entries and the names of the providers that were dropped.
    """
    defaults = settings.provider_env_defaults()
    usable: list[dict] = []
    dropped: set[str] = set()
    for entry in entries:
        resolved, missing = resolve_env_references(entry, defaults)
        name = str(entry.get("model_name", DEFAULT_MODEL_NAME))
        if missing:
            dropped.add(name)
            logger.info(
                "provider %s disabled: %s not set",
                sanitize_for_logs(name),
                ", ".join(missing),
            )
            continue
        usable.append(resolved)
    return usable, dropped


def _resolve_fallbacks(fallbacks: list[dict], dropped: set[str]) -> list[dict]:
    """Remove dropped providers from both ends of every fallback relation."""
    kept: list[dict] = []
    for entry in fallbacks:
        for primary, targets in entry.items():
            if primary in dropped:
                continue
            alive = [target for target in targets if target not in dropped]
            if alive:
                kept.append({primary: alive})
    return kept


def _apply_litellm_settings(settings: dict) -> None:
    litellm.drop_params = bool(settings.get("drop_params", True))


def create_client(
    settings: Settings | None = None,
    config_path: Path | None = None,
) -> LiteLLMClient:
    """Build the LiteLLM router from the YAML configuration.

    Args:
        settings: Settings supplying placeholder fallbacks. Defaults to the process settings.
        config_path: Configuration file. Defaults to `backend/config/litellm_config.yaml`.

    Returns:
        A client ready to complete requests.

    Raises:
        OSError: if the configuration file cannot be read.
        yaml.YAMLError: if the configuration file is not valid YAML.
    """
    current = settings or get_settings()
    config = _load_yaml(config_path or DEFAULT_CONFIG_PATH)

    model_list, dropped = _resolve_models(config.get("model_list", []), current)
    litellm_settings = config.get("litellm_settings", {})
    router_settings = config.get("router_settings", {})
    timeout = float(litellm_settings.get("request_timeout", DEFAULT_TIMEOUT_SECONDS))

    router = litellm.Router(
        model_list=model_list,
        fallbacks=_resolve_fallbacks(router_settings.get("fallbacks", []), dropped),
        routing_strategy=router_settings.get("routing_strategy", DEFAULT_ROUTING_STRATEGY),
        num_retries=int(litellm_settings.get("num_retries", DEFAULT_NUM_RETRIES)),
        timeout=timeout,
    )
    _apply_litellm_settings(litellm_settings)
    logger.info(
        "litellm router ready with %d providers",
        len(model_list),
    )
    return LiteLLMClient(router=router, timeout=timeout)
