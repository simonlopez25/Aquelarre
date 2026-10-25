"""Logging configuration that keeps credentials out of the log stream."""

from __future__ import annotations

import logging
import sys
from typing import Final

from app.core.security import sanitize_for_logs

LOG_FORMAT: Final[str] = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOGGED_NAMESPACES: Final[tuple[str, ...]] = ("app", "litellm")
DEFAULT_LEVEL: Final[int] = logging.INFO


class SecretRedactionFilter(logging.Filter):
    """Rewrite log records in place so no credential-looking token reaches a handler."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Sanitize the message, its arguments and any captured traceback.

        Args:
            record: The record about to be emitted.

        Returns:
            Always `True`; the record is only rewritten, never dropped.
        """
        record.msg = sanitize_for_logs(str(record.msg))
        record.args = _sanitize_args(record.args)
        if record.exc_text:
            record.exc_text = sanitize_for_logs(record.exc_text)
        return True


def _sanitize_value(value: object) -> object:
    """Redact strings only, so numeric placeholders such as `%d` keep working."""
    if isinstance(value, str):
        return sanitize_for_logs(value)
    return value


def _sanitize_args(args: object) -> object:
    if isinstance(args, dict):
        return {key: _sanitize_value(value) for key, value in args.items()}
    if isinstance(args, tuple):
        return tuple(_sanitize_value(value) for value in args)
    return _sanitize_value(args)


def _resolve_level(level: str) -> int:
    resolved = getattr(logging, level.upper(), None)
    return resolved if isinstance(resolved, int) else DEFAULT_LEVEL


def configure_logging(level: str = "INFO") -> None:
    """Install a stdout handler with secret redaction on the application namespaces.

    Args:
        level: Level name such as `INFO` or `DEBUG`. Unknown names fall back to `INFO`.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    handler.addFilter(SecretRedactionFilter())

    for namespace in LOGGED_NAMESPACES:
        logger = logging.getLogger(namespace)
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(_resolve_level(level))
        logger.propagate = False
