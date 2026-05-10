"""Contract tests for ``POST /api/settings/api-keys/validate-adzuna``.

Purpose:
    Lock in the wire contract used by the onboarding wizard's optional
    Adzuna section: a 200 success returns ``{"ok": True}``, Adzuna 401/403
    folds to a 401 ``ADZUNA_AUTH_FAILED``, network errors to 502
    ``ADZUNA_UNREACHABLE``, and 5xx to 502 ``ADZUNA_ERROR``.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from api import main as api_main
from api.routers import settings_api_keys as router


VALID_PAYLOAD = {"app_id": "id-test", "app_key": "key-test"}


def _client() -> TestClient:
    """Construct a TestClient bound to the FastAPI app under test.

    Purpose:
        Centralize TestClient construction so each test reads as straight
        Arrange / Act / Assert.
    Args:
        None.
    Output:
        Returns a ``TestClient`` instance.
    """

    return TestClient(api_main.app)


def _install_adzuna_handler(
    monkeypatch: pytest.MonkeyPatch,
    handler: Any,
) -> None:
    """Replace ``httpx.AsyncClient`` with a ``MockTransport``-backed factory.

    Purpose:
        The validate-adzuna route constructs ``httpx.AsyncClient`` directly,
        so each test installs a transport that returns the response shape it
        wants to exercise.
    Args:
        monkeypatch: Pytest monkeypatch helper.
        handler: ``httpx`` request handler used by ``MockTransport``.
    Output:
        Returns ``None``; mutation is via the supplied monkeypatch.
    """

    real_async_client = httpx.AsyncClient

    def factory(**_: Any) -> httpx.AsyncClient:
        return real_async_client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    # The router imports ``httpx`` and instantiates ``httpx.AsyncClient`` at
    # call time, so the monkeypatch above is the one it sees. ``router`` is
    # used here only to keep the import side-effect explicit.
    _ = router


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_validate_adzuna_returns_ok_on_200(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify a successful Adzuna probe returns ``{"ok": True}`` with HTTP 200.

    Purpose:
        The wizard treats the 200 response as the green light to persist
        the Adzuna keys; regressions on this contract would block onboarding.
    """

    captured: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(dict(request.url.params))
        return httpx.Response(200, json={"results": []})

    _install_adzuna_handler(monkeypatch, handler)
    client = _client()

    response = client.post(
        "/api/settings/api-keys/validate-adzuna",
        json=VALID_PAYLOAD,
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert captured[0]["app_id"] == "id-test"
    assert captured[0]["app_key"] == "key-test"


# ---------------------------------------------------------------------------
# Adzuna-side error mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("upstream_status", [401, 403])
def test_validate_adzuna_maps_auth_rejections_to_401(
    monkeypatch: pytest.MonkeyPatch,
    upstream_status: int,
) -> None:
    """Verify Adzuna 401/403 responses fold into ``ADZUNA_AUTH_FAILED`` 401.

    Purpose:
        Both unauthorized and forbidden responses indicate bad credentials
        from the wizard's perspective; the route normalizes them to one
        actionable error code.
    """

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(upstream_status, json={"error": "auth"})

    _install_adzuna_handler(monkeypatch, handler)
    client = _client()

    response = client.post(
        "/api/settings/api-keys/validate-adzuna",
        json=VALID_PAYLOAD,
    )

    assert response.status_code == 401
    body = response.json()
    assert body["ok"] is False
    assert body["code"] == "ADZUNA_AUTH_FAILED"


def test_validate_adzuna_maps_5xx_to_adzuna_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify upstream 5xx responses surface as 502 ``ADZUNA_ERROR``.

    Purpose:
        Server-side Adzuna failures are not the user's fault; the wizard
        should let them retry rather than blame the credentials.
    """

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "boom"})

    _install_adzuna_handler(monkeypatch, handler)
    client = _client()

    response = client.post(
        "/api/settings/api-keys/validate-adzuna",
        json=VALID_PAYLOAD,
    )

    assert response.status_code == 502
    body = response.json()
    assert body["code"] == "ADZUNA_ERROR"
    assert "503" in body["message"]


def test_validate_adzuna_maps_request_error_to_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify network-level errors surface as 502 ``ADZUNA_UNREACHABLE``.

    Purpose:
        DNS or socket failures are distinct from Adzuna saying "no" — the UI
        wants to differentiate so it can suggest "check your connection".
    """

    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated network failure")

    _install_adzuna_handler(monkeypatch, handler)
    client = _client()

    response = client.post(
        "/api/settings/api-keys/validate-adzuna",
        json=VALID_PAYLOAD,
    )

    assert response.status_code == 502
    body = response.json()
    assert body["code"] == "ADZUNA_UNREACHABLE"


# ---------------------------------------------------------------------------
# Pydantic validation
# ---------------------------------------------------------------------------


def test_validate_adzuna_rejects_empty_app_id() -> None:
    """Verify Pydantic rejects an empty ``app_id`` with 422 before any HTTP call.

    Purpose:
        Empty fields would always fail upstream; rejecting at the schema
        boundary keeps the error message specific and avoids a wasted call.
    """

    client = _client()

    response = client.post(
        "/api/settings/api-keys/validate-adzuna",
        json={"app_id": "", "app_key": "key-test"},
    )

    assert response.status_code == 422


def test_validate_adzuna_rejects_empty_app_key() -> None:
    """Verify Pydantic rejects an empty ``app_key`` with 422 before any HTTP call.

    Purpose:
        Mirror of the empty-app_id check — both fields are required, both
        must short-circuit at the schema layer.
    """

    client = _client()

    response = client.post(
        "/api/settings/api-keys/validate-adzuna",
        json={"app_id": "id-test", "app_key": ""},
    )

    assert response.status_code == 422


def test_validate_adzuna_rejects_extra_fields() -> None:
    """Verify the Pydantic model forbids extra fields on the request body.

    Purpose:
        ``extra="forbid"`` keeps the wire contract tight so frontend payload
        regressions show up as 422s instead of silently-ignored fields.
    """

    client = _client()

    response = client.post(
        "/api/settings/api-keys/validate-adzuna",
        json={"app_id": "id-test", "app_key": "key-test", "country": "us"},
    )

    assert response.status_code == 422
