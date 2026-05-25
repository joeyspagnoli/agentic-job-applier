"""Integration tests for ``_run_application_flow`` with the finisher gate.

Drives the production flow with the existing ``FakeBrowserPage`` fixture
plus monkeypatched seams for ``run_finisher``, ``try_submit_and_classify``,
and the field/upload helpers so the finisher invocation, gate evaluation,
and submit classification can all be exercised deterministically.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.agents.apply_worker import browser as browser_module
from src.agents.apply_worker.finisher_integration import (
    FinisherContext,
    FinisherDependencies,
)
from src.agents.apply_finisher.answer_cache import AnswerCache
from src.agents.apply_finisher.defer_rules import DeferRules
from src.agents.apply_finisher.schemas import FinisherResult
from src.agents.apply_worker.schemas import (
    ApplyOutcome,
    ATSPlatform,
    ConfidenceReport,
)


# ---------------------------------------------------------------------------
# Fake page surface
# ---------------------------------------------------------------------------


class FakeFlowPage:
    """Page double that satisfies every surface ``_run_application_flow`` calls."""

    def __init__(self, *, html: str = "<html><body><form></form></body></html>") -> None:
        """Capture URL state and the deterministic body content."""

        self.url = "https://example.com/apply"
        self._html = html

    async def goto(
        self,
        source_url: str,
        timeout: int = 0,
        wait_until: str | None = None,
    ) -> None:
        """Record the navigation target."""

        _ = (timeout, wait_until)
        self.url = source_url

    async def wait_for_load_state(self, state: str, timeout: int = 0) -> None:
        """Accept the load-state wait without side effects."""

        _ = (state, timeout)

    async def content(self) -> str:
        """Return the configured HTML."""

        return self._html

    async def evaluate(self, script: str, arg: Any | None = None) -> bool:
        """Return ``True`` for the Simplify-detect script, ``False`` otherwise."""

        _ = arg
        if script == browser_module._JS_DETECT_SIMPLIFY:
            return False
        return False


# ---------------------------------------------------------------------------
# Common monkeypatch helpers
# ---------------------------------------------------------------------------


def _patch_shared_seams(
    monkeypatch: pytest.MonkeyPatch,
    *,
    ats: ATSPlatform,
    simplify_no_op: bool = False,
) -> None:
    """Patch the helpers that aren't being exercised in a given test."""

    async def fake_upload(*_: object, **__: object) -> bool:
        return True

    async def fake_scan(*_: object, **__: object) -> list[object]:
        return []

    async def fake_confidence(*_: object, **__: object) -> ConfidenceReport:
        return ConfidenceReport(
            score=0.9,
            checks=[],
            has_hard_blockers=False,
            resume_uploaded=True,
            simplify_autofill_detected=False,
            unresolved_required_count=0,
            unresolved_optional_count=0,
            ats_platform=ats,
        )

    async def fake_trigger(*_: object, **__: object) -> str:
        return "CLICKED:Autofill"

    async def fake_screenshot(*_: object, **__: object) -> None:
        return None

    async def fake_dom(*_: object, **__: object) -> None:
        return None

    async def fake_verify(*_: object, **__: object) -> dict[str, object]:
        return {
            "simplify_no_op": simplify_no_op,
            "values_seen": {},
            "selectors_checked": [],
        }

    async def fake_session_bootstrap(
        _cdp_url: str, apply_url: str | None = None
    ) -> tuple[bool, str]:
        """Bypass the real agent-browser CDP bootstrap subprocess."""

        _ = apply_url
        return True, ""

    monkeypatch.setattr(browser_module, "detect_ats_platform", lambda *_: ats)
    monkeypatch.setattr(browser_module, "_trigger_simplify_autofill", fake_trigger)
    monkeypatch.setattr(browser_module, "upload_resume", fake_upload)
    monkeypatch.setattr(browser_module, "scan_unresolved_fields", fake_scan)
    monkeypatch.setattr(browser_module, "compute_confidence", fake_confidence)
    monkeypatch.setattr(browser_module, "_save_screenshot_safe", fake_screenshot)
    monkeypatch.setattr(browser_module, "_save_dom_safe", fake_dom)
    monkeypatch.setattr(browser_module, "verify_after_fill", fake_verify)
    monkeypatch.setattr(
        browser_module, "_ensure_agent_browser_session", fake_session_bootstrap
    )


def _build_finisher_context(tmp_path: Path, safe_mode: bool = False) -> FinisherContext:
    """Build a context with placeholder paths the loader won't need."""

    return FinisherContext(
        target_company="Acme",
        target_role="SWE",
        job_description="A short JD.",
        candidate_profile_path=tmp_path / "candidate_profile.yaml",
        defer_rules_path=tmp_path / "defer_rules.yaml",
        answer_cache_path=tmp_path / "answer_cache.yaml",
        safe_mode=safe_mode,
    )


def _stub_deps(threshold: float = 1.0) -> FinisherDependencies:
    """Build a tiny FinisherDependencies object the worker can read."""

    return FinisherDependencies(
        defer_rules=DeferRules(
            _always_defer_patterns=(),
            _draft_and_flag_patterns=(),
            bypass_field_types=frozenset(),
            never_defer_overrides=(),
        ),
        answer_cache=AnswerCache(_path=Path("/tmp/_flow_cache.yaml")),
        profile_yaml="profile: {}\n",
        tier2_confidence_threshold=threshold,
    )


# ---------------------------------------------------------------------------
# Lever skip — finisher_dialect is None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lever_skips_finisher_and_lands_needs_review(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When the ATS is Lever the finisher is never invoked."""

    _patch_shared_seams(monkeypatch, ats=ATSPlatform.LEVER)

    finisher_calls: list[bool] = []

    async def fake_runner(*_: object, **__: object) -> FinisherResult:
        finisher_calls.append(True)
        return FinisherResult(outcome="COMPLETE", all_required_filled=True)

    monkeypatch.setattr(browser_module, "run_finisher", fake_runner)

    result = await browser_module._run_application_flow(
        page=FakeFlowPage(),
        source_url="https://jobs.lever.co/foo/abc/apply",
        resume_pdf_path=tmp_path / "resume.pdf",
        job_hash="abc",
        screenshot_path=tmp_path / "shot.png",
        dom_snapshot_path=tmp_path / "dom.html",
        unresolved_path=tmp_path / "u.json",
        dry_run=False,
        finisher_context=_build_finisher_context(tmp_path),
    )

    assert result.outcome == ApplyOutcome.NEEDS_REVIEW
    assert finisher_calls == []
    assert result.finisher_diagnostics is not None
    assert result.finisher_diagnostics.finisher_outcome == "SKIPPED"


# ---------------------------------------------------------------------------
# Greenhouse: gate passes → submit fires → SUBMITTED
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_greenhouse_gate_pass_fires_submit_and_lands_submitted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A clean COMPLETE result + URL change → SUBMITTED, no errors."""

    _patch_shared_seams(monkeypatch, ats=ATSPlatform.GREENHOUSE)

    async def fake_runner(*_: object, **__: object) -> FinisherResult:
        return FinisherResult(outcome="COMPLETE", all_required_filled=True)

    submit_calls: list[ATSPlatform] = []

    async def fake_submit(*, page: Any, ats_platform: ATSPlatform) -> tuple[ApplyOutcome, list[str]]:
        _ = page
        submit_calls.append(ats_platform)
        return ApplyOutcome.SUBMITTED, []

    monkeypatch.setattr(browser_module, "run_finisher", fake_runner)
    monkeypatch.setattr(browser_module, "try_submit_and_classify", fake_submit)
    monkeypatch.setattr(browser_module, "load_finisher_dependencies", lambda ctx: _stub_deps())

    result = await browser_module._run_application_flow(
        page=FakeFlowPage(),
        source_url="https://example.com/apply",
        resume_pdf_path=tmp_path / "resume.pdf",
        job_hash="gh123",
        screenshot_path=tmp_path / "shot.png",
        dom_snapshot_path=tmp_path / "dom.html",
        unresolved_path=tmp_path / "u.json",
        dry_run=False,
        finisher_context=_build_finisher_context(tmp_path),
    )

    assert result.outcome == ApplyOutcome.SUBMITTED
    assert submit_calls == [ATSPlatform.GREENHOUSE]
    assert result.finisher_diagnostics is not None
    assert result.finisher_diagnostics.gate_decision == "auto_submit"


# ---------------------------------------------------------------------------
# Greenhouse: tier-3 deferral → submit NOT fired
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_greenhouse_tier3_deferred_holds_back_submit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When the finisher reports Tier-3 deferrals the submit never fires."""

    _patch_shared_seams(monkeypatch, ats=ATSPlatform.GREENHOUSE)

    async def fake_runner(*_: object, **__: object) -> FinisherResult:
        return FinisherResult(
            outcome="COMPLETE",
            all_required_filled=True,
            has_tier3_deferred=True,
        )

    submit_attempts: list[bool] = []

    async def fake_submit(**_: object) -> tuple[ApplyOutcome, list[str]]:
        submit_attempts.append(True)
        return ApplyOutcome.SUBMITTED, []

    monkeypatch.setattr(browser_module, "run_finisher", fake_runner)
    monkeypatch.setattr(browser_module, "try_submit_and_classify", fake_submit)
    monkeypatch.setattr(browser_module, "load_finisher_dependencies", lambda ctx: _stub_deps())

    result = await browser_module._run_application_flow(
        page=FakeFlowPage(),
        source_url="https://example.com/apply",
        resume_pdf_path=tmp_path / "resume.pdf",
        job_hash="gh_t3",
        screenshot_path=tmp_path / "shot.png",
        dom_snapshot_path=tmp_path / "dom.html",
        unresolved_path=tmp_path / "u.json",
        dry_run=False,
        finisher_context=_build_finisher_context(tmp_path),
    )

    assert result.outcome == ApplyOutcome.NEEDS_REVIEW
    assert submit_attempts == []
    assert result.finisher_diagnostics is not None
    assert result.finisher_diagnostics.gate_decision == "tier3_deferred"


# ---------------------------------------------------------------------------
# SAFE_MODE env beats a passing gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_safe_mode_env_wins_over_passing_gate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``SAFE_MODE=true`` blocks submit even with a clean COMPLETE result."""

    _patch_shared_seams(monkeypatch, ats=ATSPlatform.GREENHOUSE)
    monkeypatch.setenv("SAFE_MODE", "true")

    async def fake_runner(*_: object, **__: object) -> FinisherResult:
        return FinisherResult(outcome="COMPLETE", all_required_filled=True)

    submit_attempts: list[bool] = []

    async def fake_submit(**_: object) -> tuple[ApplyOutcome, list[str]]:
        submit_attempts.append(True)
        return ApplyOutcome.SUBMITTED, []

    monkeypatch.setattr(browser_module, "run_finisher", fake_runner)
    monkeypatch.setattr(browser_module, "try_submit_and_classify", fake_submit)
    monkeypatch.setattr(browser_module, "load_finisher_dependencies", lambda ctx: _stub_deps())

    result = await browser_module._run_application_flow(
        page=FakeFlowPage(),
        source_url="https://example.com/apply",
        resume_pdf_path=tmp_path / "resume.pdf",
        job_hash="gh_safe",
        screenshot_path=tmp_path / "shot.png",
        dom_snapshot_path=tmp_path / "dom.html",
        unresolved_path=tmp_path / "u.json",
        dry_run=False,
        finisher_context=_build_finisher_context(tmp_path),
    )

    assert result.outcome == ApplyOutcome.NEEDS_REVIEW
    assert submit_attempts == []
    assert result.finisher_diagnostics is not None
    assert result.finisher_diagnostics.gate_decision == "safe_mode"


# ---------------------------------------------------------------------------
# Greenhouse: validation toast → NEEDS_REVIEW with errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validation_toast_lands_needs_review_with_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A failed submit that scrapes toast text reports NEEDS_REVIEW + errors."""

    _patch_shared_seams(monkeypatch, ats=ATSPlatform.GREENHOUSE)

    async def fake_runner(*_: object, **__: object) -> FinisherResult:
        return FinisherResult(outcome="COMPLETE", all_required_filled=True)

    async def fake_submit(**_: object) -> tuple[ApplyOutcome, list[str]]:
        return ApplyOutcome.NEEDS_REVIEW, ["email is required"]

    monkeypatch.setattr(browser_module, "run_finisher", fake_runner)
    monkeypatch.setattr(browser_module, "try_submit_and_classify", fake_submit)
    monkeypatch.setattr(browser_module, "load_finisher_dependencies", lambda ctx: _stub_deps())

    result = await browser_module._run_application_flow(
        page=FakeFlowPage(),
        source_url="https://example.com/apply",
        resume_pdf_path=tmp_path / "resume.pdf",
        job_hash="gh_validate",
        screenshot_path=tmp_path / "shot.png",
        dom_snapshot_path=tmp_path / "dom.html",
        unresolved_path=tmp_path / "u.json",
        dry_run=False,
        finisher_context=_build_finisher_context(tmp_path),
    )

    assert result.outcome == ApplyOutcome.NEEDS_REVIEW
    assert result.finisher_diagnostics is not None
    assert result.finisher_diagnostics.submit_errors == ["email is required"]


# ---------------------------------------------------------------------------
# Captcha intercept: submit fires, URL doesn't change, no toast → FAILED_OTHER
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_captcha_intercept_classifies_failed_other(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No URL change + no toast (captcha) → FAILED_OTHER + success=False."""

    _patch_shared_seams(monkeypatch, ats=ATSPlatform.GREENHOUSE)

    async def fake_runner(*_: object, **__: object) -> FinisherResult:
        return FinisherResult(outcome="COMPLETE", all_required_filled=True)

    async def fake_submit(**_: object) -> tuple[ApplyOutcome, list[str]]:
        return ApplyOutcome.FAILED_OTHER, []

    monkeypatch.setattr(browser_module, "run_finisher", fake_runner)
    monkeypatch.setattr(browser_module, "try_submit_and_classify", fake_submit)
    monkeypatch.setattr(browser_module, "load_finisher_dependencies", lambda ctx: _stub_deps())

    result = await browser_module._run_application_flow(
        page=FakeFlowPage(),
        source_url="https://example.com/apply",
        resume_pdf_path=tmp_path / "resume.pdf",
        job_hash="gh_captcha",
        screenshot_path=tmp_path / "shot.png",
        dom_snapshot_path=tmp_path / "dom.html",
        unresolved_path=tmp_path / "u.json",
        dry_run=False,
        finisher_context=_build_finisher_context(tmp_path),
    )

    assert result.success is False
    assert result.outcome == ApplyOutcome.FAILED_OTHER
    assert result.failure_reason == "submit_no_url_change_no_toast"


# ---------------------------------------------------------------------------
# Ashby gate-pass also fires submit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ashby_gate_pass_fires_submit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The Ashby branch also evaluates the gate and fires submit on PASS."""

    _patch_shared_seams(monkeypatch, ats=ATSPlatform.ASHBY)

    async def fake_runner(*_: object, **__: object) -> FinisherResult:
        return FinisherResult(outcome="COMPLETE", all_required_filled=True)

    submit_atses: list[ATSPlatform] = []

    async def fake_submit(*, page: Any, ats_platform: ATSPlatform) -> tuple[ApplyOutcome, list[str]]:
        _ = page
        submit_atses.append(ats_platform)
        return ApplyOutcome.SUBMITTED, []

    monkeypatch.setattr(browser_module, "run_finisher", fake_runner)
    monkeypatch.setattr(browser_module, "try_submit_and_classify", fake_submit)
    monkeypatch.setattr(browser_module, "load_finisher_dependencies", lambda ctx: _stub_deps())

    result = await browser_module._run_application_flow(
        page=FakeFlowPage(),
        source_url="https://jobs.ashbyhq.com/notion/abc/application",
        resume_pdf_path=tmp_path / "resume.pdf",
        job_hash="ashby1",
        screenshot_path=tmp_path / "shot.png",
        dom_snapshot_path=tmp_path / "dom.html",
        unresolved_path=tmp_path / "u.json",
        dry_run=False,
        finisher_context=_build_finisher_context(tmp_path),
    )

    assert result.outcome == ApplyOutcome.SUBMITTED
    assert submit_atses == [ATSPlatform.ASHBY]


# ---------------------------------------------------------------------------
# Tier-2 confidence at/above/below threshold (gate logic via the worker)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tier2_below_threshold_blocks_submit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Drafts below the profile-configured threshold block auto-submit."""

    _patch_shared_seams(monkeypatch, ats=ATSPlatform.GREENHOUSE)

    from src.agents.apply_finisher.schemas import DraftedField

    async def fake_runner(*_: object, **__: object) -> FinisherResult:
        return FinisherResult(
            outcome="COMPLETE",
            all_required_filled=True,
            has_tier2_pending=True,
            drafted_fields_flagged_for_verify=[
                DraftedField(
                    field_id="e9", label="Why?", drafted_value="...",
                    confidence=0.80, reasoning="meh",
                )
            ],
        )

    submit_attempts: list[bool] = []

    async def fake_submit(**_: object) -> tuple[ApplyOutcome, list[str]]:
        submit_attempts.append(True)
        return ApplyOutcome.SUBMITTED, []

    monkeypatch.setattr(browser_module, "run_finisher", fake_runner)
    monkeypatch.setattr(browser_module, "try_submit_and_classify", fake_submit)
    monkeypatch.setattr(
        browser_module, "load_finisher_dependencies",
        lambda ctx: _stub_deps(threshold=0.92),
    )

    result = await browser_module._run_application_flow(
        page=FakeFlowPage(),
        source_url="https://example.com/apply",
        resume_pdf_path=tmp_path / "resume.pdf",
        job_hash="t2_below",
        screenshot_path=tmp_path / "shot.png",
        dom_snapshot_path=tmp_path / "dom.html",
        unresolved_path=tmp_path / "u.json",
        dry_run=False,
        finisher_context=_build_finisher_context(tmp_path),
    )

    assert result.outcome == ApplyOutcome.NEEDS_REVIEW
    assert submit_attempts == []
    assert result.finisher_diagnostics is not None
    assert result.finisher_diagnostics.gate_decision == "tier2_pending"


@pytest.mark.asyncio
async def test_tier2_above_threshold_fires_submit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Drafts ≥ profile-configured threshold let the submit fire."""

    _patch_shared_seams(monkeypatch, ats=ATSPlatform.GREENHOUSE)

    from src.agents.apply_finisher.schemas import DraftedField

    async def fake_runner(*_: object, **__: object) -> FinisherResult:
        return FinisherResult(
            outcome="COMPLETE",
            all_required_filled=True,
            has_tier2_pending=True,
            drafted_fields_flagged_for_verify=[
                DraftedField(
                    field_id="e9", label="Why?", drafted_value="...",
                    confidence=0.95, reasoning="high",
                )
            ],
        )

    async def fake_submit(**_: object) -> tuple[ApplyOutcome, list[str]]:
        return ApplyOutcome.SUBMITTED, []

    monkeypatch.setattr(browser_module, "run_finisher", fake_runner)
    monkeypatch.setattr(browser_module, "try_submit_and_classify", fake_submit)
    monkeypatch.setattr(
        browser_module, "load_finisher_dependencies",
        lambda ctx: _stub_deps(threshold=0.92),
    )

    result = await browser_module._run_application_flow(
        page=FakeFlowPage(),
        source_url="https://example.com/apply",
        resume_pdf_path=tmp_path / "resume.pdf",
        job_hash="t2_above",
        screenshot_path=tmp_path / "shot.png",
        dom_snapshot_path=tmp_path / "dom.html",
        unresolved_path=tmp_path / "u.json",
        dry_run=False,
        finisher_context=_build_finisher_context(tmp_path),
    )

    assert result.outcome == ApplyOutcome.SUBMITTED
    assert result.finisher_diagnostics is not None
    assert result.finisher_diagnostics.gate_decision == "auto_submit"
