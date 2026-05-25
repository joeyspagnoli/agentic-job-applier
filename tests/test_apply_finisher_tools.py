"""Behavioral tests for the apply-finisher Pydantic AI tools.

The browser surface is one shell-tool (``agent_browser``) that
delegates to the shared subprocess helper exercised in
``test_apply_finisher_browser_cli.py``; here we cover the wrapper
behavior (ModelRetry on missing binary, dict pass-through on success)
and the three state tools (``defer``, ``flag_for_verify``,
``lookup_cached_answer``) plus the ``_normalize_ab_ref`` helper that
canonicalises the agent-browser ``@eN`` ref format used by the model.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic_ai import ModelRetry

from src.agents.apply_finisher import tools as tools_module
from src.agents.apply_finisher.answer_cache import AnswerCache, load_answer_cache
from src.agents.apply_finisher.defer_rules import DeferRules
from src.agents.apply_finisher.schemas import FinisherDeps
from src.agents.apply_finisher.tools import (
    _normalize_ab_ref,
    agent_browser,
    defer,
    flag_for_verify,
    lookup_cached_answer,
)


class _Ctx:
    """RunContext stub carrying ``FinisherDeps`` for the state tools."""

    def __init__(self, deps: FinisherDeps) -> None:
        """Bind the deps the tool body reads."""

        self.deps = deps


def _build_deps(cache: AnswerCache | None = None) -> FinisherDeps:
    """Build a minimal ``FinisherDeps`` for state-tool assertions.

    Args:
        cache: Optional cache to inject; defaults to an empty one
            backed by a tmp path that is never written to in these
            tests.
    Returns:
        Configured ``FinisherDeps``.
    """

    return FinisherDeps(
        ats="greenhouse",
        target_company="Acme",
        defer_rules=DeferRules(
            _always_defer_patterns=(),
            _draft_and_flag_patterns=(),
            bypass_field_types=frozenset(),
            never_defer_overrides=(),
        ),
        cache=cache
        or AnswerCache(_path=Path("/tmp/_tools_cache.yaml")),
        profile_yaml="profile: {}\n",
    )


# ---------------------------------------------------------------------------
# _normalize_ab_ref
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("@e5", "e5"),
        ("e5", "e5"),
        ("5", "e5"),
        ("  @e12  ", "e12"),
        ("e0", "e0"),
    ],
)
def test_normalize_ab_ref_accepts_canonical_shapes(
    raw: str, expected: str
) -> None:
    """``@eN``, ``eN``, and bare digits all canonicalise to ``eN``."""

    assert _normalize_ab_ref(raw) == expected


@pytest.mark.parametrize("raw", ["", "  ", "@", "garbage", "e", "exx"])
def test_normalize_ab_ref_rejects_invalid_shapes(raw: str) -> None:
    """Empty, partial, or non-numeric refs raise ``ModelRetry``."""

    with pytest.raises(ModelRetry):
        _normalize_ab_ref(raw)


# ---------------------------------------------------------------------------
# agent_browser wrapper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_browser_returns_helper_result_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful CLI call passes the structured dict through unchanged."""

    captured: dict[str, Any] = {}

    async def fake_invoke(
        args: list[str],
        *,
        expect_json: bool = False,
        timeout_seconds: float = 20.0,
    ) -> dict[str, Any]:
        """Capture invocation args and return a canned ok payload."""

        captured["args"] = list(args)
        captured["expect_json"] = expect_json
        captured["timeout_seconds"] = timeout_seconds
        return {
            "ok": True,
            "command": "agent-browser snapshot -i",
            "stdout": "tree",
            "stderr": "",
            "exit_code": 0,
        }

    monkeypatch.setattr(tools_module, "invoke_agent_browser_cli", fake_invoke)

    result = await agent_browser(["snapshot", "-i"], timeout_seconds=8.0)

    assert result["ok"] is True
    assert result["stdout"] == "tree"
    assert captured == {
        "args": ["snapshot", "-i"],
        "expect_json": False,
        "timeout_seconds": 8.0,
    }


@pytest.mark.asyncio
async def test_agent_browser_raises_model_retry_when_binary_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A ``-2`` launch failure surfaces as ``ModelRetry`` for the agent."""

    async def fake_invoke(*_: Any, **__: Any) -> dict[str, Any]:
        """Return the canonical missing-binary payload."""

        return {
            "ok": False,
            "command": "agent-browser snapshot",
            "stdout": "",
            "stderr": "",
            "exit_code": -2,
            "error": "agent-browser CLI not on PATH — image is missing",
        }

    monkeypatch.setattr(tools_module, "invoke_agent_browser_cli", fake_invoke)

    with pytest.raises(ModelRetry) as exc_info:
        await agent_browser(["snapshot"])

    assert "not on PATH" in str(exc_info.value)


@pytest.mark.asyncio
async def test_agent_browser_passes_through_nonbinary_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-launch failures (e.g. nonzero exit) return the dict for the agent."""

    async def fake_invoke(*_: Any, **__: Any) -> dict[str, Any]:
        """Return a click-failed payload."""

        return {
            "ok": False,
            "command": "agent-browser click @e5",
            "stdout": "",
            "stderr": "element not found",
            "exit_code": 1,
        }

    monkeypatch.setattr(tools_module, "invoke_agent_browser_cli", fake_invoke)

    result = await agent_browser(["click", "@e5"])

    assert result["ok"] is False
    assert result["exit_code"] == 1
    assert "element not found" in result["stderr"]


# ---------------------------------------------------------------------------
# defer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_defer_records_question_with_normalized_ref() -> None:
    """``defer`` appends a ``DeferredQuestion`` keyed by the canonical ref."""

    deps = _build_deps()
    ctx = _Ctx(deps)

    result = await defer(
        ctx,  # type: ignore[arg-type]
        ref="@e7",
        label="Salary expectation",
        field_type="textbox",
        category="salary",
        reason="user must answer",
    )

    assert "deferred ref e7" in result
    assert len(deps.recorded_deferrals) == 1
    recorded = deps.recorded_deferrals[0]
    assert recorded.field_id == "e7"
    assert recorded.category == "salary"
    assert recorded.label == "Salary expectation"


# ---------------------------------------------------------------------------
# flag_for_verify
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flag_for_verify_records_draft() -> None:
    """``flag_for_verify`` appends a ``DraftedField`` with the supplied confidence."""

    deps = _build_deps()
    ctx = _Ctx(deps)

    await flag_for_verify(
        ctx,  # type: ignore[arg-type]
        ref="3",
        label="Why this role?",
        drafted_value="I love it.",
        confidence=0.5,
        reasoning="profile-light",
    )

    assert len(deps.drafted_fields) == 1
    draft = deps.drafted_fields[0]
    assert draft.field_id == "e3"
    assert draft.confidence == 0.5
    assert draft.drafted_value == "I love it."


@pytest.mark.asyncio
async def test_flag_for_verify_rejects_confidence_out_of_range() -> None:
    """Confidence outside [0.0, 1.0] raises ``ModelRetry``."""

    deps = _build_deps()
    ctx = _Ctx(deps)

    with pytest.raises(ModelRetry):
        await flag_for_verify(
            ctx,  # type: ignore[arg-type]
            ref="e3",
            label="Why this role?",
            drafted_value="anything",
            confidence=1.5,
            reasoning="too confident",
        )


# ---------------------------------------------------------------------------
# lookup_cached_answer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lookup_cached_answer_returns_sentinel_on_miss() -> None:
    """An empty cache produces the ``<no cache hit>`` sentinel."""

    deps = _build_deps()
    ctx = _Ctx(deps)

    result = await lookup_cached_answer(
        ctx,  # type: ignore[arg-type]
        question_text="Why this role?",
    )

    assert result == "<no cache hit>"


@pytest.mark.asyncio
async def test_lookup_cached_answer_returns_hit_payload(tmp_path: Path) -> None:
    """A matching cache entry is rendered with the score + answer."""

    cache = load_answer_cache(tmp_path / "answer_cache.yaml")
    cache.append_entry(
        question_text="Why are you interested in this role?",
        answer="Because I am.",
        category="motivation",
        company_specific=False,
    )
    deps = _build_deps(cache=cache)
    ctx = _Ctx(deps)

    result = await lookup_cached_answer(
        ctx,  # type: ignore[arg-type]
        question_text="Why are you interested in this role?",
    )

    assert "<cache_hit" in result
    assert "Because I am." in result
