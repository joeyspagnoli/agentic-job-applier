"""Smoke tests for the apply-finisher prompts + worker-side gate logic.

Tool-surface behavior (``agent_browser``, ``defer``,
``flag_for_verify``, ``lookup_cached_answer``) lives in
``test_apply_finisher_tools.py``; subprocess plumbing in
``test_apply_finisher_browser_cli.py``. This file covers the
non-tool surfaces: prompt assembly, the binary submit gate's six
branches, and the misc helpers used by the worker integration
(ATS mapping, JD excerpt, safe-mode env parse, diagnostics
synthesis).
"""

from __future__ import annotations

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
    FinisherResult,
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


def test_base_prompt_teaches_agent_browser_shell_tool() -> None:
    """Base prompt names the single ``agent_browser`` shell-tool."""

    assert "agent_browser(args" in BASE


def test_base_prompt_keeps_eeo_as_tier_1() -> None:
    """The EEO=Tier-1 correction from the smoke-test edits survives."""

    assert "EEO is **NOT** Tier 3" in BASE


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

    can, label = evaluate_submit_gate(
        finisher_result=_make_complete_result(),
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
