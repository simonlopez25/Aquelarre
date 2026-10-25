"""Application settings loaded from environment variables."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

# The dotenv file lives at the repository root so Docker Compose and local runs read the same file.
REPO_ENV_FILE: Final[Path] = Path(__file__).resolve().parents[3] / ".env"

# LiteLLM spells out placeholders as os.environ/NAME; the YAML is written in that same dialect.
_ENV_REFERENCE: Final[re.Pattern[str]] = re.compile(r"os\.env(?:iron)?/([A-Za-z_]\w*)")

GROQ_PROVIDER: Final[str] = "groq-llama"
GEMINI_PROVIDER: Final[str] = "gemini-flash"
KILO_PROVIDER: Final[str] = "kilo-free"
OLLAMA_PROVIDER: Final[str] = "ollama-coder"
OPENCODE_PROVIDER: Final[str] = "opencode-deepseek"

PROVIDERS_WITHOUT_KEY: Final[tuple[str, ...]] = (
    OLLAMA_PROVIDER,
    OPENCODE_PROVIDER,
    KILO_PROVIDER,
)

STARTUP_ERROR_ES: Final[str] = (
    "Configuración inválida de Aquelarre: faltan variables de entorno obligatorias: {missing}. "
    "Copia backend/.env.example a .env en la raíz del repo y completa los valores."
)
STARTUP_ERROR_EN: Final[str] = (
    "Invalid Aquelarre configuration: required environment variables missing: {missing}. "
    "Copy backend/.env.example to .env at the repository root and fill in the values."
)


class Settings(BaseSettings):
    """Environment-backed configuration for the whole backend.

    Every value read from the environment lives here; no other module is allowed to call
    `os.getenv`.
    """

    model_config = SettingsConfigDict(env_file=REPO_ENV_FILE, extra="ignore")

    aquelarre_api_key: str
    groq_api_key: str | None = None
    gemini_api_key: str | None = None
    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "qwen2.5-coder:7b"
    opencode_base_url: str = "http://host.docker.internal:55890/v1"
    opencode_model: str = "deepseek-v4.1-flash-free"
    kilo_base_url: str = "https://api.kilo.ai/api/gateway/v1"
    database_url: str = "sqlite:///./data/aquelarre.db"
    log_level: str = "INFO"
    cooldown_seconds: int = 300

    def active_providers(self) -> list[str]:
        """Return the provider names that can serve traffic with the current credentials.

        Providers requiring a key are dropped silently when the key is absent, so a missing
        optional credential never prevents startup.
        """
        active = list(PROVIDERS_WITHOUT_KEY)
        if self.groq_api_key:
            active.append(GROQ_PROVIDER)
        if self.gemini_api_key:
            active.append(GEMINI_PROVIDER)
        return active

    def provider_env_defaults(self) -> dict[str, str]:
        """Return fallback values for the LiteLLM placeholders that have a settings default.

        Environment variables always win; these only keep a provider alive when its URL or
        model name was never exported, so an unset variable never disables a keyless provider.
        """
        return {
            "OLLAMA_BASE_URL": self.ollama_base_url,
            "OLLAMA_MODEL": self.ollama_model,
            "OPENCODE_BASE_URL": self.opencode_base_url,
            "OPENCODE_MODEL": self.opencode_model,
            "KILO_BASE_URL": self.kilo_base_url,
        }


def resolve_env_references(value: Any, defaults: Mapping[str, str]) -> tuple[Any, list[str]]:
    """Replace every `os.environ/NAME` placeholder inside a LiteLLM config value.

    Args:
        value: Nested configuration loaded from YAML.
        defaults: Values to use when the variable is absent from the environment.

    Returns:
        A tuple of the resolved value and the names that could not be resolved anywhere.
    """
    if isinstance(value, str):
        return _resolve_string(value, defaults)
    if isinstance(value, dict):
        return _resolve_mapping(value, defaults)
    if isinstance(value, list):
        return _resolve_sequence(value, defaults)
    return value, []


def _resolve_string(raw: str, defaults: Mapping[str, str]) -> tuple[str, list[str]]:
    missing: list[str] = []

    def substitute(match: re.Match[str]) -> str:
        name = match.group(1)
        resolved = os.environ.get(name) or defaults.get(name)
        if not resolved:
            missing.append(name)
            return match.group(0)
        return resolved

    return _ENV_REFERENCE.sub(substitute, raw), missing


def _resolve_mapping(
    value: dict[Any, Any],
    defaults: Mapping[str, str],
) -> tuple[dict[Any, Any], list[str]]:
    missing: list[str] = []
    resolved: dict[Any, Any] = {}
    for key, item in value.items():
        resolved_item, item_missing = resolve_env_references(item, defaults)
        resolved[key] = resolved_item
        missing.extend(item_missing)
    return resolved, missing


def _resolve_sequence(
    value: list[Any],
    defaults: Mapping[str, str],
) -> tuple[list[Any], list[str]]:
    missing: list[str] = []
    resolved: list[Any] = []
    for item in value:
        resolved_item, item_missing = resolve_env_references(item, defaults)
        resolved.append(resolved_item)
        missing.extend(item_missing)
    return resolved, missing


def _format_startup_error(exc: ValidationError) -> str:
    missing = ", ".join(str(item["loc"][0]).upper() for item in exc.errors())
    return (
        f"{STARTUP_ERROR_ES.format(missing=missing)} / "
        f"{STARTUP_ERROR_EN.format(missing=missing)}"
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings, aborting startup when they are invalid.

    Raises:
        SystemExit: if a required environment variable such as `AQUELARRE_API_KEY` is missing.
    """
    try:
        return Settings()
    except ValidationError as exc:
        raise SystemExit(_format_startup_error(exc)) from exc
