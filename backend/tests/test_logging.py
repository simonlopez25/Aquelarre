"""Tests for the logging setup: secret redaction filter and level resolution."""

from __future__ import annotations

import logging

from app.core.logging_setup import (
    DEFAULT_LEVEL,
    SecretRedactionFilter,
    _resolve_level,
    _sanitize_args,
    _sanitize_value,
)


def test_resolve_level_known() -> None:
    assert _resolve_level("DEBUG") == logging.DEBUG
    assert _resolve_level("INFO") == logging.INFO
    assert _resolve_level("WARNING") == logging.WARNING
    assert _resolve_level("ERROR") == logging.ERROR


def test_resolve_level_unknown_falls_back_to_info() -> None:
    assert _resolve_level("NONSENSE") == DEFAULT_LEVEL


def test_resolve_level_case_insensitive() -> None:
    assert _resolve_level("debug") == logging.DEBUG
    assert _resolve_level("info") == logging.INFO


def test_sanitize_value_redacts_strings() -> None:
    assert _sanitize_value("sk-abc123456789") == "***REDACTED***"
    assert _sanitize_value("hello world") == "hello world"


def test_sanitize_value_passes_non_strings() -> None:
    assert _sanitize_value(42) == 42
    assert _sanitize_value(None) is None


def test_sanitize_args_dict() -> None:
    args = {"key": "sk-abc123456789", "count": 5}
    result = _sanitize_args(args)
    assert result == {"key": "***REDACTED***", "count": 5}


def test_sanitize_args_tuple() -> None:
    args = ("sk-abc123456789", 42)
    result = _sanitize_args(args)
    assert result == ("***REDACTED***", 42)


def test_sanitize_args_single_value() -> None:
    assert _sanitize_args("gsk_abc123456789") == "***REDACTED***"
    assert _sanitize_args(42) == 42


def test_filter_redacts_record_message() -> None:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="api_key=sk-abc123456789",
        args=(),
        exc_info=None,
    )
    SecretRedactionFilter().filter(record)
    assert "sk-abc123456789" not in record.msg
    assert "***REDACTED***" in record.msg


def test_filter_redacts_record_args() -> None:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="key=%s",
        args=("sk-abc123456789",),
        exc_info=None,
    )
    SecretRedactionFilter().filter(record)
    assert record.args == ("***REDACTED***",)


def test_filter_redacts_exception_text() -> None:
    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname="",
        lineno=0,
        msg="error",
        args=(),
        exc_info=None,
    )
    record.exc_text = "Authorization: Bearer sk-abc123456789"
    SecretRedactionFilter().filter(record)
    assert "sk-abc123456789" not in record.exc_text
    assert "***REDACTED***" in record.exc_text


def test_filter_always_returns_true() -> None:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="test",
        args=(),
        exc_info=None,
    )
    assert SecretRedactionFilter().filter(record) is True