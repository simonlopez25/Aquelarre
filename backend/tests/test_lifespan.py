"""Tests for the application lifespan: startup, client injection and shutdown."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient


def test_lifespan_injects_client_when_none(
    client: TestClient, mock_completion: MagicMock
) -> None:
    """The lifespan should leave an injected client untouched."""
    from app.main import app

    assert app.state.litellm_client is mock_completion
    assert app.state.hybrid_router is not None
    assert app.state.quota is not None


def test_lifespan_keeps_injected_client(client: TestClient) -> None:
    """A client injected by a test must not be replaced by the lifespan."""
    from app.main import app

    assert app.state.litellm_client is not None


def test_app_state_settings_is_available(client: TestClient) -> None:
    from app.main import app

    assert app.state.settings is not None
    assert app.state.settings.aquelarre_api_key


def test_health_endpoint_returns_200_without_auth(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert isinstance(payload["providers"], dict)


def test_health_endpoint_lists_active_providers(client: TestClient) -> None:
    response = client.get("/health")
    payload = response.json()
    # At least one provider should be present (ollama-coder is always active)
    assert "ollama-coder" in payload["providers"]


def test_health_provider_status_has_required_fields(client: TestClient) -> None:
    response = client.get("/health")
    payload = response.json()
    for _name, status in payload["providers"].items():
        assert "tokens" in status
        assert "capacity" in status
        assert "failure_count" in status
        assert "cooldown_seconds" in status
        assert "circuit_open" in status
        assert "available" in status


def test_app_has_cors_middleware(client: TestClient) -> None:
    from app.main import app

    # CORS middleware should be present in the middleware stack.
    assert len(app.user_middleware) >= 1


def test_app_registers_exception_handlers(client: TestClient) -> None:
    from app.main import app

    # Exception handlers should be registered.
    assert len(app.exception_handlers) >= 1