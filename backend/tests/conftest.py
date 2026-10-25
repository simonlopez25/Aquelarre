"""Test environment and shared fixtures.

The environment is prepared before any application module is imported, and every credential is
generated, so a developer's real keys can never reach a test run. A stub client is installed
before the lifespan runs, which keeps LiteLLM and its network stack out of the test process.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

TEST_API_KEY = f"aquelarre-{uuid4().hex}"
TEST_DATABASE_PATH = Path(tempfile.gettempdir()) / "aquelarre_test.db"
CANNED_CONTENT = "hello from the stub"

CANNED_COMPLETION: dict[str, Any] = {
    "id": "chatcmpl-test",
    "created": 1_700_000_000,
    "model": "stub-model",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": CANNED_CONTENT},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16},
}

TEST_DATABASE_PATH.unlink(missing_ok=True)
os.environ["AQUELARRE_API_KEY"] = TEST_API_KEY
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE_PATH.as_posix()}"
os.environ["GROQ_API_KEY"] = f"gsk_{uuid4().hex}"
os.environ["GEMINI_API_KEY"] = f"AIza{uuid4().hex}"
os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"
os.environ["OPENCODE_BASE_URL"] = "http://localhost:55890/v1"
os.environ["KILO_BASE_URL"] = "https://api.kilo.ai/api/gateway/v1"


@pytest.fixture
def mock_completion() -> Iterator[MagicMock]:
    """Install a stub completion client, which the lifespan then leaves untouched."""
    from app.main import app

    stub = MagicMock()
    stub.complete = AsyncMock(return_value=(True, CANNED_COMPLETION))
    app.state.litellm_client = stub
    yield stub
    app.state.litellm_client = None


@pytest.fixture
def client(mock_completion: MagicMock) -> Iterator[TestClient]:
    """Return a client whose startup lifespan has already run."""
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Return the header carrying a valid Aquelarre credential."""
    return {"Authorization": f"Bearer {os.environ['AQUELARRE_API_KEY']}"}
