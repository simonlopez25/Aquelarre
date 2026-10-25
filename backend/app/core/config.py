"""Application settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Final

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

# The dotenv file lives at the repository root so Docker Compose and local runs read the same file.
REPO_ENV_FILE: Final[Path] = Path(__file__).resolve().parents[3] / ".env"

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
