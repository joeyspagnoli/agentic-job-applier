"""Behavior tests for the .env file read/write helpers.

Purpose:
    Pin the contract for `_read_env_pairs`, `_write_env_key`, `_delete_env_key`,
    and `_read_env_key_statuses` so the OpenAI BYOK onboarding flow has a
    reliable foundation. These helpers are also intended to support future BYOK
    keys (issue #35), so the placeholder-sentinel handling and key-name
    allowlist are exercised explicitly.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from api import config as api_config
from api.services import env_keys


@pytest.fixture()
def env_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Redirect helper writes to a per-test temporary .env file.

    Purpose:
        Ensure unit tests cannot mutate the real project .env file.
    Args:
        monkeypatch: Pytest monkeypatch helper.
        tmp_path: Per-test temporary directory.
    Output:
        Returns the temporary .env path used by the helpers under test.
    """

    target = tmp_path / ".env"
    monkeypatch.setattr(env_keys, "SETTINGS_ENV_PATH", target)
    monkeypatch.setattr(api_config, "SETTINGS_ENV_PATH", target)
    for name in api_config.ALLOWED_API_KEY_NAMES:
        monkeypatch.delenv(name, raising=False)
    return target


def test_write_env_key_creates_file_when_absent(env_path: Path) -> None:
    # Arrange.
    assert not env_path.exists()

    # Act.
    env_keys._write_env_key("OPENAI_API_KEY", "sk-new")

    # Assert.
    assert env_path.read_text(encoding="utf-8") == "OPENAI_API_KEY=sk-new\n"
    assert os.environ["OPENAI_API_KEY"] == "sk-new"


def test_write_env_key_replaces_existing_entry(env_path: Path) -> None:
    # Arrange.
    env_path.write_text(
        "# header comment\nOPENAI_API_KEY=sk-old\nOTHER=keep\n",
        encoding="utf-8",
    )

    # Act.
    env_keys._write_env_key("OPENAI_API_KEY", "sk-fresh")

    # Assert.
    contents = env_path.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sk-fresh" in contents
    assert "OPENAI_API_KEY=sk-old" not in contents
    assert "OTHER=keep" in contents
    assert contents.startswith("# header comment\n")


def test_write_env_key_appends_when_key_missing(env_path: Path) -> None:
    # Arrange.
    env_path.write_text("EXISTING=1\n", encoding="utf-8")

    # Act.
    env_keys._write_env_key("OPENAI_API_KEY", "sk-add")

    # Assert.
    lines = env_path.read_text(encoding="utf-8").splitlines()
    assert "EXISTING=1" in lines
    assert "OPENAI_API_KEY=sk-add" in lines


def test_delete_env_key_removes_entry_and_unsets_env(env_path: Path) -> None:
    # Arrange.
    env_keys._write_env_key("OPENAI_API_KEY", "sk-temp")
    assert os.environ.get("OPENAI_API_KEY") == "sk-temp"

    # Act.
    env_keys._delete_env_key("OPENAI_API_KEY")

    # Assert.
    contents = env_path.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY" not in contents
    assert "OPENAI_API_KEY" not in os.environ


def test_read_env_key_statuses_treats_placeholders_as_unset(
    env_path: Path,
) -> None:
    # Arrange.
    env_path.write_text(
        "OPENAI_API_KEY=your_openai_api_key_here\n"
        "ANTHROPIC_API_KEY=your_anthropic_key_here\n"
        "GOOGLE_API_KEY=your_google_api_key_here\n",
        encoding="utf-8",
    )

    # Act.
    statuses = env_keys._read_env_key_statuses()

    # Assert.
    assert statuses["OPENAI_API_KEY"] is False
    assert statuses["ANTHROPIC_API_KEY"] is False
    assert statuses["GOOGLE_API_KEY"] is False


def test_read_env_key_statuses_marks_real_values_configured(
    env_path: Path,
) -> None:
    # Arrange.
    env_path.write_text("OPENAI_API_KEY=sk-real\n", encoding="utf-8")

    # Act.
    statuses = env_keys._read_env_key_statuses()

    # Assert.
    assert statuses["OPENAI_API_KEY"] is True
    assert statuses["ANTHROPIC_API_KEY"] is False
    assert statuses["GOOGLE_API_KEY"] is False
    assert statuses["OPENROUTER_BASE_URL"] is False


def test_read_env_key_statuses_returns_all_allowed_when_file_missing(
    env_path: Path,
) -> None:
    # Arrange.
    assert not env_path.exists()

    # Act.
    statuses = env_keys._read_env_key_statuses()

    # Assert.
    assert set(statuses.keys()) == set(api_config.ALLOWED_API_KEY_NAMES)
    assert all(value is False for value in statuses.values())


def test_build_api_keys_response_has_stable_shape(env_path: Path) -> None:
    # Arrange.
    env_keys._write_env_key("OPENAI_API_KEY", "sk-real")

    # Act.
    response = env_keys._build_api_keys_response()

    # Assert.
    assert response["ok"] is True
    keys = response["keys"]
    assert isinstance(keys, list)
    names = [entry["name"] for entry in keys]
    assert names == sorted(api_config.ALLOWED_API_KEY_NAMES)
    openai_entry = next(e for e in keys if e["name"] == "OPENAI_API_KEY")
    assert openai_entry["configured"] is True


def test_allowed_api_key_names_includes_future_byok_targets() -> None:
    # Arrange.
    expected = {
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "OPENROUTER_BASE_URL",
    }

    # Act.
    actual = set(api_config.ALLOWED_API_KEY_NAMES)

    # Assert.
    assert expected <= actual


def test_no_codex_specific_helpers_remain() -> None:
    # Arrange.
    forbidden = ("_write_codex_home", "_codex_home_path", "_clear_codex_session")

    # Act.
    present = [name for name in forbidden if hasattr(env_keys, name)]

    # Assert.
    assert present == []
