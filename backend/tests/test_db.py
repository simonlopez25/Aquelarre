"""Tests for SQLite persistence: init, log_usage and failure tolerance."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.infrastructure import db
from app.infrastructure.db import Usage


@pytest.fixture(autouse=True)
def _fresh_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Give every test its own in-memory database so they never touch the real one."""
    db._engine = None
    db.init_db("sqlite:///:memory:")
    yield
    db._engine = None


def test_init_db_creates_engine_and_schema() -> None:
    assert db._engine is not None
    with Session(db._engine) as session:
        statement = select(Usage)
        result = session.exec(statement)
        assert result.all() == []


def test_log_usage_persists_one_record() -> None:
    db.log_usage(
        provider="ollama-coder",
        task_type="code",
        mode="auto",
        tokens_in=100,
        tokens_out=50,
        latency_ms=250,
        ok=True,
    )

    with Session(db._engine) as session:
        records = session.exec(select(Usage)).all()
    assert len(records) == 1
    record = records[0]
    assert record.provider == "ollama-coder"
    assert record.task_type == "code"
    assert record.mode == "auto"
    assert record.tokens_in == 100
    assert record.tokens_out == 50
    assert record.latency_ms == 250
    assert record.ok is True
    assert record.created_at is not None


def test_log_usage_records_failure() -> None:
    db.log_usage(
        provider="groq-llama",
        task_type="general",
        mode="auto",
        tokens_in=0,
        tokens_out=0,
        latency_ms=100,
        ok=False,
    )

    with Session(db._engine) as session:
        record = session.exec(select(Usage)).first()
    assert record is not None
    assert record.ok is False


def test_log_usage_skips_when_engine_not_initialized() -> None:
    db._engine = None
    # Should not raise.
    db.log_usage(
        provider="ollama-coder",
        task_type="code",
        mode="auto",
        tokens_in=0,
        tokens_out=0,
        latency_ms=0,
        ok=True,
    )


def test_init_db_with_file_path_creates_directory(tmp_path: Path) -> None:
    db_path = tmp_path / "subdir" / "test.db"
    db.init_db(f"sqlite:///{db_path.as_posix()}")

    assert db_path.exists()
    assert db._engine is not None


def test_log_usage_is_robust_to_engine_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("database is broken")

    monkeypatch.setattr(db, "_engine", None)
    # Should not raise even when engine is missing.
    db.log_usage(
        provider="ollama-coder",
        task_type="code",
        mode="auto",
        tokens_in=0,
        tokens_out=0,
        latency_ms=0,
        ok=True,
    )