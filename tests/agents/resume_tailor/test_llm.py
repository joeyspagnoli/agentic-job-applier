"""Direct unit tests for `src/agents/resume_tailor/llm.py`.

Purpose:
    Lock the five surfaces called out in issue #41 item #7 —
    `_split_provider_and_model`, `_build_client`, `_extract_usage`,
    `get_tailor_model_name`, and `get_reviewer_model_name` — at the
    unit level. Integration coverage already exercises the public
    `call_tailor` / `call_reviewer` functions via monkeypatch; this
    file targets the internals at the `instructor.from_openai`
    boundary so no real API calls are made.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import instructor
import pytest

from src.agents.resume_tailor import llm


def test_split_provider_and_model_returns_two_parts_for_valid_id() -> None:
    """A `provider/model` string splits into two non-empty parts."""

    provider, model = llm._split_provider_and_model("openai/gpt-5-mini")

    assert provider == "openai"
    assert model == "gpt-5-mini"


def test_split_provider_and_model_raises_when_no_slash() -> None:
    """A bare model name without `/` raises `ValueError`."""

    with pytest.raises(ValueError, match="provider/model"):
        llm._split_provider_and_model("gpt-5-mini")


def test_split_provider_and_model_raises_when_left_side_empty() -> None:
    """`/model` with no provider raises `ValueError`."""

    with pytest.raises(ValueError, match="provider/model"):
        llm._split_provider_and_model("/foo")


def test_split_provider_and_model_raises_when_right_side_empty() -> None:
    """`provider/` with no model raises `ValueError`."""

    with pytest.raises(ValueError, match="provider/model"):
        llm._split_provider_and_model("openai/")


def test_build_client_raises_runtime_error_when_openai_key_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_build_client` must refuse to construct a client without `OPENAI_API_KEY`."""

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        llm._build_client("openai/gpt-5-mini")


def test_build_client_returns_instructor_client_and_bare_model_for_openai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Happy-path returns `(client, bare_model)` and calls `instructor.from_openai` once.

    Purpose:
        Stub the network boundary at `instructor.from_openai` so the
        test stays offline. Verifies the function returns the bare
        model name (no provider prefix) and constructs the client.
    """

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    call_count = {"value": 0}
    captured_mode: dict[str, Any] = {}
    sentinel_client = object()

    def fake_from_openai(_inner: object, *, mode: Any = None) -> object:
        call_count["value"] += 1
        captured_mode["mode"] = mode
        return sentinel_client

    monkeypatch.setattr(instructor, "from_openai", fake_from_openai)

    client, bare_model = llm._build_client("openai/gpt-5-mini")

    assert client is sentinel_client
    assert bare_model == "gpt-5-mini"
    assert call_count["value"] == 1
    # Pin the Responses-API mode so a future regression that drops it
    # (and silently breaks the gpt-5 family) fails loudly here.
    assert captured_mode["mode"] is instructor.Mode.RESPONSES_TOOLS


def test_build_client_raises_value_error_for_unsupported_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-OpenAI providers are rejected with `ValueError`.

    Purpose:
        Per the issue #41 item #4 decision, only OpenAI is wired today;
        attempting another provider must fail loudly rather than fall
        through to a misleading branch.
    """

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    with pytest.raises(ValueError, match="Unsupported provider"):
        llm._build_client("anthropic/gpt-5-mini")


def test_extract_usage_returns_zeros_when_completion_has_no_usage() -> None:
    """A completion without a `usage` attribute returns a zero `TokenUsage`."""

    completion = SimpleNamespace()

    result = llm._extract_usage(completion)

    assert result.prompt_tokens == 0
    assert result.completion_tokens == 0


def test_extract_usage_infers_total_when_only_prompt_and_completion_present() -> None:
    """When only `prompt_tokens` and `completion_tokens` are present they are read correctly."""

    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5)
    completion = SimpleNamespace(usage=usage)

    result = llm._extract_usage(completion)

    assert result.prompt_tokens == 10
    assert result.completion_tokens == 5


def test_extract_usage_respects_explicit_total_tokens() -> None:
    """An explicit `total_tokens` field is ignored; the TokenUsage prompt+completion fields are set."""

    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=20)
    completion = SimpleNamespace(usage=usage)

    result = llm._extract_usage(completion)

    assert result.prompt_tokens == 10
    assert result.completion_tokens == 5


def test_extract_usage_coerces_none_attributes_to_zero() -> None:
    """`None`-valued usage fields are coerced to `0` rather than raising."""

    usage = SimpleNamespace(prompt_tokens=None, completion_tokens=None, total_tokens=None)
    completion = SimpleNamespace(usage=usage)

    result = llm._extract_usage(completion)

    assert result.prompt_tokens == 0
    assert result.completion_tokens == 0


def test_extract_usage_returns_zeros_when_usage_is_none() -> None:
    """A completion whose `usage` field is `None` returns a zero `TokenUsage`."""

    completion: Any = SimpleNamespace(usage=None)

    result = llm._extract_usage(completion)

    assert result.prompt_tokens == 0
    assert result.completion_tokens == 0


def test_get_tailor_model_name_returns_default_when_env_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No env override → returns `DEFAULT_TAILOR_MODEL`."""

    monkeypatch.delenv(llm.TAILOR_MODEL_ENV_VAR, raising=False)

    result = llm.get_tailor_model_name()

    assert result == llm.DEFAULT_TAILOR_MODEL


def test_get_tailor_model_name_default_is_pinned_to_gpt_5_4(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pin the literal default tailor model to `openai/gpt-5.4`.

    Purpose:
        Commit `9be242d` bumped the tailor default from `gpt-5-mini`
        to `gpt-5.4` after the tightened prompt landed; this test
        fails loudly if a future bump silently changes the default
        (in either direction) without an accompanying review.
    """

    monkeypatch.delenv(llm.TAILOR_MODEL_ENV_VAR, raising=False)

    result = llm.get_tailor_model_name()

    assert result == "openai/gpt-5.4"


def test_get_reviewer_model_name_default_is_pinned_to_gpt_5_mini(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pin the literal default reviewer model to `openai/gpt-5-mini`.

    Purpose:
        The reviewer was also swapped off the coding-tuned default in
        #53 so the tailor and reviewer share the same prose-tuned model.
    """

    monkeypatch.delenv(llm.REVIEWER_MODEL_ENV_VAR, raising=False)

    result = llm.get_reviewer_model_name()

    assert result == "openai/gpt-5-mini"


def test_get_tailor_model_name_honors_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`RESUME_TAILOR_MODEL` overrides the default when set to a non-blank value."""

    monkeypatch.setenv(llm.TAILOR_MODEL_ENV_VAR, "openai/gpt-5")

    result = llm.get_tailor_model_name()

    assert result == "openai/gpt-5"


def test_get_reviewer_model_name_honors_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`RESUME_REVIEWER_MODEL` overrides the default when set to a non-blank value."""

    monkeypatch.setenv(llm.REVIEWER_MODEL_ENV_VAR, "openai/gpt-5")

    result = llm.get_reviewer_model_name()

    assert result == "openai/gpt-5"
