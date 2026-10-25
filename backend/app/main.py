"""Composition root: assembles the application and holds no business logic."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Final

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.handlers import register_exception_handlers
from app.api.routes import router as api_router
from app.core.config import Settings, get_settings
from app.core.logging_setup import configure_logging
from app.domain.router import HybridRouter, QuotaManager
from app.infrastructure import db
from app.infrastructure.litellm_client import create_client

TITLE: Final[str] = "Aquelarre"
VERSION: Final[str] = "0.1.0"

# The extension runs both as a localhost page and as a vscode-webview document, and each sends
# a different Origin; localhost may carry any port while the webview origin carries a random id.
STATIC_ORIGINS: Final[list[str]] = ["http://localhost", "http://127.0.0.1"]
ORIGIN_PATTERN: Final[str] = (
    r"^(?:https?://(?:localhost|127\.0\.0\.1)(?::\d+)?|vscode-webview://\S+)$"
)
ALLOWED_METHODS: Final[list[str]] = ["GET", "POST"]
ALLOWED_HEADERS: Final[list[str]] = ["Authorization", "Content-Type"]


def create_app(settings: Settings | None = None) -> FastAPI:
    current = settings or get_settings()
    configure_logging(current.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        db.init_db(current.database_url)
        # Built during startup so a broken provider config aborts the boot instead of the
        # first request; a client injected by a test is left untouched.
        if application.state.litellm_client is None:
            application.state.litellm_client = create_client(current)
        yield

    application = FastAPI(title=TITLE, version=VERSION, lifespan=lifespan)
    application.state.settings = current
    application.state.quota = QuotaManager(current.active_providers(), current.cooldown_seconds)
    application.state.hybrid_router = HybridRouter(application.state.quota)
    application.state.litellm_client = None

    application.add_middleware(
        CORSMiddleware,
        allow_origins=STATIC_ORIGINS,
        allow_origin_regex=ORIGIN_PATTERN,
        allow_methods=ALLOWED_METHODS,
        allow_headers=ALLOWED_HEADERS,
    )
    register_exception_handlers(application)
    application.include_router(api_router)
    return application


app: Final[FastAPI] = create_app()