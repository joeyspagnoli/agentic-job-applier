"""Validate system lifecycle endpoint dispatch behavior.

Purpose:
    Ensure `/api/system/stop` and `/api/system/restart` return accepted payloads
    on successful dispatch and preserve the standard error envelope on failures.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from api import main as api_main


@pytest.fixture
def lifecycle_client() -> TestClient:
    """Build a FastAPI test client for lifecycle endpoint contract tests.

    Purpose:
        Provide one reusable API client for lifecycle endpoint tests.
    Args:
        None.
    Output:
        Returns a `TestClient` bound to `api_main.app`.
    """

    return TestClient(api_main.app)


def test_stop_system_endpoint_returns_accepted_payload(
    lifecycle_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify stop endpoint returns accepted payload on successful dispatch.

    Purpose:
        Protect frontend contract expectations for stop action responses.
    Args:
        lifecycle_client: Test client fixture for API requests.
        monkeypatch: Fixture used to patch lifecycle dispatch helper.
    Output:
        Returns `None`; test passes when response payload matches contract.
    """

    monkeypatch.setattr(
        api_main,
        "_dispatch_system_lifecycle_action",
        lambda action: f"request-{action}",
    )

    response = lifecycle_client.post("/api/system/stop")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "action": "stop",
        "status": "accepted",
        "request_id": "request-stop",
    }


def test_restart_system_endpoint_returns_accepted_payload(
    lifecycle_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify restart endpoint returns accepted payload on successful dispatch.

    Purpose:
        Protect frontend contract expectations for restart action responses.
    Args:
        lifecycle_client: Test client fixture for API requests.
        monkeypatch: Fixture used to patch lifecycle dispatch helper.
    Output:
        Returns `None`; test passes when response payload matches contract.
    """

    monkeypatch.setattr(
        api_main,
        "_dispatch_system_lifecycle_action",
        lambda action: f"request-{action}",
    )

    response = lifecycle_client.post("/api/system/restart")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "action": "restart",
        "status": "accepted",
        "request_id": "request-restart",
    }


def test_system_lifecycle_endpoint_returns_standard_error_envelope_on_dispatch_failure(
    lifecycle_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify dispatch failures use standard API error payload shape.

    Purpose:
        Keep error handling deterministic when lifecycle scripts cannot be
        dispatched.
    Args:
        lifecycle_client: Test client fixture for API requests.
        monkeypatch: Fixture used to patch lifecycle dispatch helper.
    Output:
        Returns `None`; test passes when endpoint returns standard error envelope.
    """

    def _raise_dispatch_error(_: str) -> str:
        """Raise deterministic dispatch failure for endpoint error-path testing.

        Purpose:
            Simulate script-dispatch failure without touching host scripts.
        Args:
            _: Ignored lifecycle action string.
        Output:
            Raises `OSError`.
        """

        raise OSError("synthetic dispatch failure")

    monkeypatch.setattr(
        api_main,
        "_dispatch_system_lifecycle_action",
        _raise_dispatch_error,
    )

    response = lifecycle_client.post("/api/system/stop")

    assert response.status_code == 500
    assert response.json()["ok"] is False
    assert response.json()["code"] == "SYSTEM_ACTION_DISPATCH_FAILED"
    assert response.json()["message"] == "Failed to dispatch system stop action."
    assert response.json()["details"]["action"] == "stop"
