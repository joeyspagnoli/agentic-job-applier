"""HTTP contract tests for `/api/system-settings/automation`.

Purpose:
    Lock the request/response contract for the GET/PATCH automation-mode
    endpoints, including 422 rejection of unknown modes and the partial-
    update semantics on PATCH.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import main as api_main


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Return a TestClient with an isolated DB path.

    Purpose:
        Redirect every router that reads `_main.resolve_database_path()` to
        a per-test SQLite file so requests cannot collide with real data.
    """

    db_path = tmp_path / "settings.db"
    monkeypatch.setattr(api_main, "resolve_database_path", lambda: db_path)
    monkeypatch.delenv("TAILOR_MODE", raising=False)
    return TestClient(api_main.app)


def test_get_returns_defaults_on_fresh_db(client: TestClient) -> None:
    """First GET creates the table; tailor mode defaults to `opt_in`."""

    response = client.get("/api/system-settings/automation")

    assert response.status_code == 200
    body = response.json()
    assert body == {"ok": True, "tailor_mode": "opt_in"}


def test_patch_updates_tailor_mode(client: TestClient) -> None:
    """PATCH with `tailor_mode` updates the persisted value."""

    response = client.patch(
        "/api/system-settings/automation",
        json={"tailor_mode": "autonomous"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["tailor_mode"] == "autonomous"


def test_patch_empty_body_is_noop_and_returns_current_state(
    client: TestClient,
) -> None:
    """An empty body returns the post-write state (which equals the pre-state)."""

    response = client.patch("/api/system-settings/automation", json={})

    assert response.status_code == 200
    body = response.json()
    assert body == {"ok": True, "tailor_mode": "opt_in"}


def test_patch_rejects_invalid_mode_with_422(client: TestClient) -> None:
    """Unknown mode strings produce a 422 with `INVALID_AUTOMATION_MODE`."""

    response = client.patch(
        "/api/system-settings/automation",
        json={"tailor_mode": "definitely_not_a_mode"},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "INVALID_AUTOMATION_MODE"
    assert body["details"]["field"] == "tailor_mode"


def test_patch_then_get_round_trips(client: TestClient) -> None:
    """A value written via PATCH is visible to a subsequent GET."""

    client.patch("/api/system-settings/automation", json={"tailor_mode": "both"})

    response = client.get("/api/system-settings/automation")

    assert response.status_code == 200
    assert response.json()["tailor_mode"] == "both"


def test_patch_silently_ignores_unknown_field(client: TestClient) -> None:
    """Stale clients sending a removed field receive 200 with no effect."""

    response = client.patch(
        "/api/system-settings/automation",
        json={"review_mode": "both"},
    )

    assert response.status_code == 200
    body = response.json()
    assert "review_mode" not in body
    assert body["tailor_mode"] == "opt_in"
