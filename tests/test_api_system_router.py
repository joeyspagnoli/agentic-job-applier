"""Validate `/api/system/health` reports the OpenAI key configuration state.

Purpose:
    Guarantee the dashboard always receives a deterministic payload with an
    `openai_key_configured` flag so it can render the missing-key banner
    consistently regardless of how `OPENAI_API_KEY` is set, unset, or blank.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from api import main as api_main


@pytest.fixture
def health_client() -> TestClient:
    """Build a FastAPI test client for `/api/system/health` contract tests.

    Purpose:
        Provide one reusable API client bound to the live application so the
        endpoint is exercised through the same router stack production uses.
    Args:
        None.
    Output:
        Returns a `TestClient` wrapping `api_main.app`.
    """

    return TestClient(api_main.app)


def test_system_health_reports_openai_key_configured_true_when_env_set(
    health_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify health flags the key as configured when the env var is set.

    Purpose:
        Lock in the dashboard contract that `openai_key_configured` becomes
        True the moment a non-empty value is present in the environment.
    Args:
        health_client: Test client fixture for the FastAPI app.
        monkeypatch: Fixture used to set the env var deterministically.
    Output:
        Returns `None`; assertion failure surfaces a contract regression.
    """

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-value")

    response = health_client.get("/api/system/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload == {"ok": True, "openai_key_configured": True}


def test_system_health_reports_openai_key_configured_false_when_unset(
    health_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify health flags the key as missing when the env var is unset.

    Purpose:
        Ensure the missing-key banner trigger fires whenever `OPENAI_API_KEY`
        is not part of the runtime environment at all.
    Args:
        health_client: Test client fixture for the FastAPI app.
        monkeypatch: Fixture used to delete the env var deterministically.
    Output:
        Returns `None`; assertion failure surfaces a contract regression.
    """

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    response = health_client.get("/api/system/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload == {"ok": True, "openai_key_configured": False}


def test_system_health_treats_blank_openai_key_as_unset(
    health_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify whitespace-only key values are treated as missing.

    Purpose:
        Defend against `.env` files that leave `OPENAI_API_KEY=` or contain
        only whitespace; the dashboard must still surface the warning banner.
    Args:
        health_client: Test client fixture for the FastAPI app.
        monkeypatch: Fixture used to set the env var to blank values.
    Output:
        Returns `None`; assertion failure surfaces a contract regression.
    """

    monkeypatch.setenv("OPENAI_API_KEY", "   ")

    response = health_client.get("/api/system/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["openai_key_configured"] is False
