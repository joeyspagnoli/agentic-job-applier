"""Smoke tests for the apply-finisher tool surface and gate logic.

Covers the contract orchestrator-side: each tool resolves a Playwright
locator, the gate's six branches each reach the expected verdict, and
the prompt assembly produces a non-empty payload. The full
behavior-driven test pass (DOM fixtures, mocked agent runs, tier
classification corner cases) belongs to the testing-standards agent.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from src.agents.apply_finisher.prompts import (
    BASE,
    build_system_prompt,
    fragment_for,
)
from src.agents.apply_finisher.schemas import (
    DeferredQuestion,
    DraftedField,
    FinisherDeps,
    FinisherResult,
)
from src.agents.apply_finisher.tools import (
    _is_forbidden_name,
    _normalize_aria_ref,
    click,
    defer,
    fill,
    flag_for_verify,
    get_snapshot,
    lookup_cached_answer,
)
from src.agents.apply_worker.finisher_integration import (
    evaluate_submit_gate,
    excerpt_job_description,
    safe_mode_from_env,
    supported_finisher_ats,
    synthesize_diagnostics,
)
from src.agents.apply_worker.schemas import ATSPlatform


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _FakeLocator:
    """Minimal Playwright-like Locator for tool-surface smoke tests."""

    def __init__(
        self,
        *,
        count: int = 1,
        accessible_name: str = "Some Field",
        text_content_value: str | None = "Some Field",
    ) -> None:
        """Capture invocation arguments for assertion in tests.

        Args:
            count: What ``count()`` returns.
            accessible_name: What ``get_attribute('aria-label')`` returns.
            text_content_value: What ``text_content()`` returns.
        """

        self._count = count
        self._accessible_name = accessible_name
        self._text_content_value = text_content_value
        self.click_calls: int = 0
        self.fill_calls: list[str] = []
        self.first = self

    async def count(self) -> int:
        """Return the configured count."""

        return self._count

    async def get_attribute(self, _name: str) -> str | None:
        """Return the configured aria-label."""

        return self._accessible_name

    async def text_content(self) -> str | None:
        """Return the configured text content."""

        return self._text_content_value

    async def click(self) -> None:
        """Increment the click counter."""

        self.click_calls += 1

    async def fill(self, value: str) -> None:
        """Record the fill value."""

        self.fill_calls.append(value)

    async def aria_snapshot(self, *, mode: str = "ai") -> str:
        """Return a stub snapshot string."""

        return f"snapshot mode={mode}"


class _FakePage:
    """Page double that returns the same _FakeLocator for any selector."""

    def __init__(self, *, locator: _FakeLocator) -> None:
        """Hold the locator that will be returned for every call."""

        self._locator = locator
        self.url: str = "https://example.com/apply"

    def locator(self, _selector: str) -> _FakeLocator:
        """Return the held locator regardless of selector."""

        return self._locator

    async def screenshot(self, *, full_page: bool = False) -> bytes:
        """Return a constant byte payload."""

        return b"\x89PNG\r\n\x1a\nfake"


class _FakeRunContext:
    """RunContext stub carrying the supplied FinisherDeps."""

    def __init__(self, deps: FinisherDeps) -> None:
        """Store the deps reference."""

        self.deps = deps


def _build_deps(page: _FakePage) -> FinisherDeps:
    """Construct a FinisherDeps wired to the supplied fake page."""

    from src.agents.apply_finisher.answer_cache import AnswerCache
    from src.agents.apply_finisher.defer_rules import DeferRules

    cache = AnswerCache(_path=Path("/tmp/_smoke_cache.yaml"))
    defer_rules = DeferRules(
        _always_defer_patterns=(),
        _draft_and_flag_patterns=(),
        bypass_field_types=frozenset(),
        never_defer_overrides=(),
    )
    return FinisherDeps(
        page=page,  # type: ignore[arg-type]
        ats="greenhouse",
        target_company="Stripe",
        defer_rules=defer_rules,
        cache=cache,
        profile_yaml="profile: {}\n",
        form_root_selector="#application_form",
    )


# ---------------------------------------------------------------------------
# Ref normalization
# ---------------------------------------------------------------------------


def test_normalize_aria_ref_accepts_bare_int() -> None:
    """``"5"`` normalizes to ``"e5"``."""

    assert _normalize_aria_ref("5") == "e5"


def test_normalize_aria_ref_accepts_eN() -> None:
    """``"e12"`` passes through unchanged."""

    assert _normalize_aria_ref("e12") == "e12"


# ---------------------------------------------------------------------------
# Forbidden-name guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["Submit", "submit application", "Apply Now", "send"],
)
def test_forbidden_name_blocks_submit_words(name: str) -> None:
    """Submit-style accessible names are flagged for refusal."""

    assert _is_forbidden_name(name) is True


@pytest.mark.parametrize("name", ["Next", "Continue", "Save", "Upload Resume"])
def test_forbidden_name_allows_non_submit_words(name: str) -> None:
    """Non-submit accessible names are not flagged."""

    assert _is_forbidden_name(name) is False


# ---------------------------------------------------------------------------
# Tool smoke
# ---------------------------------------------------------------------------


def test_defer_records_into_deps() -> None:
    """``defer`` appends a DeferredQuestion without touching the page."""

    page = _FakePage(locator=_FakeLocator())
    deps = _build_deps(page)
    ctx = _FakeRunContext(deps)

    result = asyncio.run(
        defer(
            ctx,  # type: ignore[arg-type]
            ref="e3",
            label="Sponsorship?",
            field_type="select",
            category="sponsorship",
            reason="Tier-3 by policy.",
        )
    )

    assert "deferred ref e3" in result
    assert len(deps.recorded_deferrals) == 1
    assert isinstance(deps.recorded_deferrals[0], DeferredQuestion)
    assert deps.recorded_deferrals[0].category == "sponsorship"


def test_flag_for_verify_records_drafted_field() -> None:
    """``flag_for_verify`` appends a DraftedField with the confidence."""

    page = _FakePage(locator=_FakeLocator())
    deps = _build_deps(page)
    ctx = _FakeRunContext(deps)

    result = asyncio.run(
        flag_for_verify(
            ctx,  # type: ignore[arg-type]
            ref="e7",
            label="Why this role?",
            drafted_value="I admire $COMPANY's mission.",
            confidence=0.6,
            reasoning="Drafted from JD; needs review.",
        )
    )

    assert "flagged ref e7" in result
    assert len(deps.drafted_fields) == 1
    assert isinstance(deps.drafted_fields[0], DraftedField)
    assert deps.drafted_fields[0].confidence == pytest.approx(0.6)


def test_fill_increments_counter_and_writes() -> None:
    """``fill`` writes the value AND bumps ``fields_filled_count``."""

    locator = _FakeLocator()
    page = _FakePage(locator=locator)
    deps = _build_deps(page)
    ctx = _FakeRunContext(deps)

    result = asyncio.run(
        fill(
            ctx,  # type: ignore[arg-type]
            ref="e2",
            value="Joseph",
        )
    )

    assert "filled ref e2" in result
    assert locator.fill_calls == ["Joseph"]
    assert deps.fields_filled_count == 1


def test_click_refuses_submit_buttons() -> None:
    """``click`` raises ModelRetry when the element name is submit-style."""

    from pydantic_ai import ModelRetry

    locator = _FakeLocator(accessible_name="Submit application")
    page = _FakePage(locator=locator)
    deps = _build_deps(page)
    ctx = _FakeRunContext(deps)

    with pytest.raises(ModelRetry):
        asyncio.run(click(ctx, ref="e9"))  # type: ignore[arg-type]
    # And the underlying click was not invoked.
    assert locator.click_calls == 0


def test_get_snapshot_returns_tool_return_with_text() -> None:
    """``get_snapshot`` wraps the AX tree in a ToolReturn."""

    locator = _FakeLocator()
    page = _FakePage(locator=locator)
    deps = _build_deps(page)
    ctx = _FakeRunContext(deps)

    result = asyncio.run(get_snapshot(ctx))  # type: ignore[arg-type]
    assert "snapshot mode=ai" in str(result.return_value)


def test_lookup_cached_answer_returns_sentinel_on_miss() -> None:
    """``lookup_cached_answer`` returns the no-hit sentinel when empty."""

    page = _FakePage(locator=_FakeLocator())
    deps = _build_deps(page)
    ctx = _FakeRunContext(deps)

    result = asyncio.run(
        lookup_cached_answer(ctx, question_text="anything")  # type: ignore[arg-type]
    )
    assert result == "<no cache hit>"


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


def test_build_system_prompt_includes_base_and_fragment() -> None:
    """Composed prompt carries both the base and the per-ATS fragment."""

    prompt = build_system_prompt("greenhouse")
    assert BASE in prompt
    assert "Greenhouse-specific quirks" in prompt
    assert fragment_for("greenhouse") in prompt


def test_fragment_for_rejects_unknown_ats() -> None:
    """``fragment_for`` raises ValueError on an unsupported ATS."""

    with pytest.raises(ValueError):
        fragment_for("workday")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Gate evaluator
# ---------------------------------------------------------------------------


def _make_complete_result(**overrides: Any) -> FinisherResult:
    """Build a happy-path ``FinisherResult`` with optional field overrides."""

    base = FinisherResult(
        outcome="COMPLETE",
        all_required_filled=True,
        has_tier3_deferred=False,
        has_tier2_pending=False,
        drafted_fields_flagged_for_verify=[],
    )
    return base.model_copy(update=overrides)


def test_gate_authorizes_when_all_conditions_pass() -> None:
    """All three gate clauses met → auto_submit branch fires."""

    result = _make_complete_result()
    can, label = evaluate_submit_gate(
        finisher_result=result,
        tier2_confidence_threshold=1.0,
        dry_run=False,
        safe_mode=False,
    )
    assert (can, label) == (True, "auto_submit")


def test_gate_refuses_on_dry_run() -> None:
    """``dry_run=True`` always wins over a passing finisher result."""

    can, label = evaluate_submit_gate(
        finisher_result=_make_complete_result(),
        tier2_confidence_threshold=1.0,
        dry_run=True,
        safe_mode=False,
    )
    assert (can, label) == (False, "dry_run")


def test_gate_refuses_on_safe_mode() -> None:
    """``safe_mode=True`` always wins, even over ``dry_run=False``."""

    can, label = evaluate_submit_gate(
        finisher_result=_make_complete_result(),
        tier2_confidence_threshold=1.0,
        dry_run=False,
        safe_mode=True,
    )
    assert (can, label) == (False, "safe_mode")


def test_gate_refuses_on_tier3_deferred() -> None:
    """A Tier-3 deferral blocks the auto_submit branch."""

    result = _make_complete_result(
        has_tier3_deferred=True,
        deferred_questions=[
            DeferredQuestion(
                field_id="e1",
                label="Sponsorship?",
                field_type="select",
                category="sponsorship",
                reason="Tier-3.",
            )
        ],
    )
    can, label = evaluate_submit_gate(
        finisher_result=result,
        tier2_confidence_threshold=1.0,
        dry_run=False,
        safe_mode=False,
    )
    assert (can, label) == (False, "tier3_deferred")


def test_gate_refuses_on_tier2_below_threshold() -> None:
    """Tier-2 drafts below threshold block auto_submit."""

    draft = DraftedField(
        field_id="e2",
        label="Why?",
        drafted_value="...",
        confidence=0.85,
        reasoning="Drafted.",
    )
    result = _make_complete_result(
        has_tier2_pending=True,
        drafted_fields_flagged_for_verify=[draft],
    )
    can, label = evaluate_submit_gate(
        finisher_result=result,
        tier2_confidence_threshold=0.92,
        dry_run=False,
        safe_mode=False,
    )
    assert (can, label) == (False, "tier2_pending")


def test_gate_allows_tier2_at_threshold() -> None:
    """Tier-2 drafts at or above threshold let auto_submit through."""

    draft = DraftedField(
        field_id="e2",
        label="Why?",
        drafted_value="...",
        confidence=0.95,
        reasoning="High confidence draft.",
    )
    result = _make_complete_result(
        has_tier2_pending=True,
        drafted_fields_flagged_for_verify=[draft],
    )
    can, label = evaluate_submit_gate(
        finisher_result=result,
        tier2_confidence_threshold=0.92,
        dry_run=False,
        safe_mode=False,
    )
    assert (can, label) == (True, "auto_submit")


def test_gate_refuses_when_finisher_incomplete() -> None:
    """Any non-COMPLETE outcome blocks the auto_submit branch."""

    for bad_outcome in ("AGENT_GAVE_UP", "USAGE_LIMIT_HIT", "RUNTIME_ERROR"):
        result = _make_complete_result(outcome=bad_outcome)
        can, label = evaluate_submit_gate(
            finisher_result=result,
            tier2_confidence_threshold=1.0,
            dry_run=False,
            safe_mode=False,
        )
        assert (can, label) == (False, "finisher_incomplete")


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------


def test_supported_finisher_ats_maps_known_atses() -> None:
    """Greenhouse and Ashby are supported; Lever / Workday are not."""

    assert supported_finisher_ats(ATSPlatform.GREENHOUSE) == "greenhouse"
    assert supported_finisher_ats(ATSPlatform.ASHBY) == "ashby"
    assert supported_finisher_ats(ATSPlatform.LEVER) is None
    assert supported_finisher_ats(ATSPlatform.WORKDAY) is None


def test_excerpt_job_description_truncates_long_text() -> None:
    """Excerpt caps at the configured length and adds a sentinel."""

    long_text = "x" * 20_000
    excerpted = excerpt_job_description(long_text)
    assert excerpted.endswith("(excerpted)")
    assert len(excerpted) < len(long_text)


def test_safe_mode_from_env_parses_true_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """``SAFE_MODE=true`` is parsed as enabled regardless of case."""

    monkeypatch.setenv("SAFE_MODE", "TRUE")
    assert safe_mode_from_env() is True


def test_safe_mode_from_env_defaults_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unset env defaults to False so the gate is allowed to fire."""

    monkeypatch.delenv("SAFE_MODE", raising=False)
    assert safe_mode_from_env() is False


def test_synthesize_diagnostics_handles_missing_finisher() -> None:
    """``None`` finisher result yields a SKIPPED diagnostics payload."""

    diag = synthesize_diagnostics(
        finisher_result=None,
        simplify_no_op=True,
        submit_errors=[],
        gate_decision="skipped",
    )
    assert diag.finisher_outcome == "SKIPPED"
    assert diag.simplify_no_op is True
    assert diag.gate_decision == "skipped"


def test_synthesize_diagnostics_pulls_drafted_fields() -> None:
    """A populated FinisherResult flows drafted fields into diagnostics."""

    result = _make_complete_result(
        drafted_fields_flagged_for_verify=[
            DraftedField(
                field_id="e2",
                label="Why?",
                drafted_value="...",
                confidence=0.91,
                reasoning="Why this role.",
            )
        ],
        has_tier2_pending=True,
    )
    diag = synthesize_diagnostics(
        finisher_result=result,
        simplify_no_op=False,
        submit_errors=[],
        gate_decision="tier2_pending",
    )
    assert diag.has_tier2_pending is True
    assert diag.drafted_fields[0]["confidence"] == pytest.approx(0.91)
