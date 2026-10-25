"""SQLite persistence for request usage records."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Field, Session, SQLModel, create_engine

from app.core.security import sanitize_for_logs

logger: Final[logging.Logger] = logging.getLogger("app.db")

SQLITE_PREFIX: Final[str] = "sqlite:"
SQLITE_SEPARATOR: Final[str] = "sqlite:///"
MEMORY_DATABASE: Final[str] = ":memory:"

_engine: Engine | None = None


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Usage(SQLModel, table=True):
    """One row per served request.

    Attributes:
        id: Surrogate primary key.
        provider: Provider that answered.
        task_type: Task class the router detected.
        mode: `auto` when the router chose, `manual` when the client forced a provider.
        tokens_in: Prompt tokens reported upstream.
        tokens_out: Completion tokens reported upstream.
        latency_ms: Wall-clock duration of the upstream call.
        ok: Whether the call succeeded.
        created_at: UTC timestamp of the record.
    """

    id: int | None = Field(default=None, primary_key=True)
    provider: str = Field(index=True)
    task_type: str
    mode: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    ok: bool = True
    created_at: datetime = Field(default_factory=_utc_now)


def _connect_args(database_url: str) -> dict[str, bool]:
    if not database_url.startswith(SQLITE_PREFIX):
        return {}
    return {"check_same_thread": False}


def _ensure_parent_directory(database_url: str) -> None:
    if not database_url.startswith(SQLITE_PREFIX):
        return
    raw_path = database_url.split(SQLITE_SEPARATOR, 1)[-1]
    if not raw_path or raw_path == MEMORY_DATABASE:
        return
    Path(raw_path).parent.mkdir(parents=True, exist_ok=True)


def init_db(database_url: str) -> None:
    global _engine
    _ensure_parent_directory(database_url)
    _engine = create_engine(database_url, connect_args=_connect_args(database_url))
    SQLModel.metadata.create_all(_engine)
    logger.info("usage database ready")


def log_usage(
    provider: str,
    task_type: str,
    mode: str,
    tokens_in: int,
    tokens_out: int,
    latency_ms: int,
    ok: bool,
) -> None:
    if _engine is None:
        logger.warning("usage record skipped: database was not initialised")
        return

    record = Usage(
        provider=provider,
        task_type=task_type,
        mode=mode,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=latency_ms,
        ok=ok,
    )
    try:
        with Session(_engine) as session:
            session.add(record)
            session.commit()
    except SQLAlchemyError as exc:
        logger.warning("usage record failed: %s", sanitize_for_logs(str(exc)))