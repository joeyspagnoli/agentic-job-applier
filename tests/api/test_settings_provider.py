"""Contract tests for the OpenAI-only provider settings router.

Purpose:
    Lock in the narrow OSS-launch contract for `/api/settings/provider`:
    accept OpenAI BYOK keys, reject all other provider types with a stable
    error body, and confirm the legacy Codex device-auth endpoints have been
    removed from the router entirely.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import config as api_config
from api import main as api_main
from api.routers import settings_provider as settings_provider_router


@pytest.fixture()
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Redirect .env writes and OPENAI_API_KEY to a temp location.

    Purpose:
        Keep the real project .env untouched while the route writes a key.
    Args:
        monkeypatch: Pytest monkeypatch helper.
        tmp_path: Per-test temporary directory.
    Output:
        Returns the temporary .env path used by the route under test.
    """

    env_path = tmp_path / ".env"
    monkeypatch.setattr(api_config, "SETTINGS_ENV_PATH", env_path)
    # Patch the binding actually used by the env_keys helpers.
    monkeypatch.setattr(
        "api.services.env_keys.SETTINGS_ENV_PATH",
        env_path,
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return env_path


def _client() -> TestClient:
    """Construct a TestClient bound to the FastAPI app under test.

    Purpose:
        Centralize TestClient construction so every test follows the same AAA
        wiring without repeating boilerplate.
    Args:
        None.
    Output:
        Returns a TestClient instance.
    """

    return TestClient(api_main.app)


def test_post_provider_with_openai_writes_key(isolated_env: Path) -> None:
    # Arrange.
    client = _client()
    payload = {"provider_type": "openai", "api_key": "sk-test-abc123"}

    # Act.
    response = client.post("/api/settings/provider", json=payload)

    # Assert.
    assert response.status_code == 200
    body = response.json()
    assert body == {"ok": True, "mode": "byok", "provider": "openai"}
    written = isolated_env.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sk-test-abc123" in written


def test_post_provider_strips_whitespace_in_api_key(isolated_env: Path) -> None:
    # Arrange.
    client = _client()
    payload = {"provider_type": "openai", "api_key": "  sk-padded  "}

    # Act.
    response = client.post("/api/settings/provider", json=payload)

    # Assert.
    assert response.status_code == 200
    written = isolated_env.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sk-padded" in written


@pytest.mark.parametrize(
    "blocked_provider",
    ["anthropic", "gemini", "openrouter", "codex"],
)
def test_post_provider_rejects_non_openai(
    isolated_env: Path,
    blocked_provider: str,
) -> None:
    # Arrange.
    client = _client()
    payload = {"provider_type": blocked_provider, "api_key": "sk-blocked"}

    # Act.
    response = client.post("/api/settings/provider", json=payload)

    # Assert.
    assert response.status_code == 400
    body = response.json()
    assert body["ok"] is False
    assert body["code"] == "UNSUPPORTED_PROVIDER"
    assert "Only OpenAI is supported" in body["message"]
    assert "issue #35" in body["message"]
    assert body["details"] == {"provider_type": blocked_provider}
    assert not isolated_env.exists()


def test_post_provider_missing_api_key_is_rejected(isolated_env: Path) -> None:
    # Arrange.
    client = _client()
    payload = {"provider_type": "openai", "api_key": ""}

    # Act.
    response = client.post("/api/settings/provider", json=payload)

    # Assert.
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "MISSING_API_KEY"
    assert not isolated_env.exists()


def test_post_provider_omitted_api_key_is_rejected(isolated_env: Path) -> None:
    # Arrange.
    client = _client()
    payload = {"provider_type": "openai"}

    # Act.
    response = client.post("/api/settings/provider", json=payload)

    # Assert.
    assert response.status_code == 400
    assert response.json()["code"] == "MISSING_API_KEY"


def test_get_ai_provider_reports_no_key_when_unset(
    isolated_env: Path,  # noqa: ARG001 — fixture clears OPENAI_API_KEY
) -> None:
    # Arrange.
    client = _client()

    # Act.
    response = client.get("/api/settings/ai-provider")

    # Assert.
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["config"] == {
        "mode": "byok",
        "providerType": "none",
        "hasOpenaiKey": False,
    }


def test_get_ai_provider_reports_key_when_set(
    isolated_env: Path,  # noqa: ARG001 — fixture clears OPENAI_API_KEY initially
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-live-1")
    client = _client()

    # Act.
    response = client.get("/api/settings/ai-provider")

    # Assert.
    body = response.json()
    assert body["config"]["providerType"] == "openai"
    assert body["config"]["hasOpenaiKey"] is True


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/settings/codex-auth/start"),
        ("GET", "/api/settings/codex-auth/status"),
        ("POST", "/api/settings/codex-auth/disconnect"),
        ("POST", "/api/settings/codex-auth/complete"),
    ],
)
def test_codex_auth_endpoints_are_removed(method: str, path: str) -> None:
    # Arrange.
    client = _client()

    # Act.
    response = client.request(method, path)

    # Assert. 404 means no handler; 405 means SPA-fallback owns GET so
    # non-GET methods are method-not-allowed. Either confirms the legacy
    # Codex routes are gone from the API router.
    assert response.status_code in (404, 405)


def test_router_does_not_export_codex_handlers() -> None:
    # Arrange.
    forbidden_attrs = (
        "start_codex_auth",
        "get_codex_auth_status",
        "disconnect_codex_auth",
        "complete_codex_auth",
    )

    # Act.
    present = [
        name
        for name in forbidden_attrs
        if hasattr(settings_provider_router, name)
    ]

    # Assert.
    assert present == []


def test_onboarding_status_reports_missing_steps(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Arrange.
    profile_path = tmp_path / "candidate_profile.yaml"
    resume_path = tmp_path / "resume_content.yaml"
    monkeypatch.setattr(
        "api.routers.settings_provider.SETTINGS_PROFILE_PATH",
        profile_path,
    )
    monkeypatch.setattr(
        "api.routers.settings_provider.SETTINGS_RESUME_PATH",
        resume_path,
    )
    client = _client()

    # Act.
    response = client.get("/api/settings/onboarding-status")

    # Assert.
    body = response.json()
    assert body["is_complete"] is False
    assert sorted(body["missing_steps"]) == ["profile", "resume"]
    assert body["completed_steps"] == []


def test_onboarding_status_reports_complete_when_both_present(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Arrange.
    profile_path = tmp_path / "candidate_profile.yaml"
    resume_path = tmp_path / "resume_content.yaml"
    profile_path.write_text("a" * 80, encoding="utf-8")
    resume_path.write_text("resume", encoding="utf-8")
    monkeypatch.setattr(
        "api.routers.settings_provider.SETTINGS_PROFILE_PATH",
        profile_path,
    )
    monkeypatch.setattr(
        "api.routers.settings_provider.SETTINGS_RESUME_PATH",
        resume_path,
    )
    client = _client()

    # Act.
    response = client.get("/api/settings/onboarding-status")

    # Assert.
    body = response.json()
    assert body["is_complete"] is True
    assert sorted(body["completed_steps"]) == ["profile", "resume"]
    assert body["missing_steps"] == []
