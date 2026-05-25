"""Behavioral tests for ``src.agents.apply_worker.finisher_integration``.

Covers the worker-side glue: ``try_submit_and_classify`` (URL-change /
toast / silent branches), ``load_finisher_dependencies`` (YAML reads +
threshold override), and ``excerpt_job_description`` boundary behavior.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
import yaml

from src.agents.apply_finisher.schemas import FinisherResult
from src.agents.apply_worker.finisher_integration import (
    FinisherContext,
    evaluate_submit_gate,
    excerpt_job_description,
    load_finisher_dependencies,
    supported_finisher_ats,
    synthesize_diagnostics,
    try_submit_and_classify,
)
from src.agents.apply_worker.schemas import ApplyOutcome, ATSPlatform
from tests.helpers.fake_finisher_page import FakeFinisherPage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_DEFER_RULES_TEXT = """
always_defer_labels:
  - regex: '(?i)sponsor'
draft_and_flag_labels: []
bypass_field_types:
  - file
never_defer_overrides: []
"""

_ANSWER_CACHE_TEXT = "schema_version: 1\nentries: []\n"


def _write_finisher_yamls(tmp_path: Path, threshold: float | None = None) -> FinisherContext:
    """Lay out the three YAML files the loader needs and return a context."""

    profile_path = tmp_path / "candidate_profile.yaml"
    defer_path = tmp_path / "defer_rules.yaml"
    cache_path = tmp_path / "answer_cache.yaml"

    apply_prefs: dict[str, object] = {"work_authorized_us": "yes"}
    if threshold is not None:
        apply_prefs["application_defaults"] = {"tier2_confidence_threshold": threshold}

    profile_path.write_text(
        yaml.safe_dump({"profile": {"contact": {"full_name": "Test"}}, "apply_prefs": apply_prefs}),
        encoding="utf-8",
    )
    defer_path.write_text(_DEFER_RULES_TEXT, encoding="utf-8")
    cache_path.write_text(_ANSWER_CACHE_TEXT, encoding="utf-8")

    return FinisherContext(
        target_company="Acme",
        target_role="SWE",
        job_description="A short JD.",
        candidate_profile_path=profile_path,
        defer_rules_path=defer_path,
        answer_cache_path=cache_path,
        safe_mode=False,
    )


# ---------------------------------------------------------------------------
# load_finisher_dependencies
# ---------------------------------------------------------------------------


def test_load_finisher_dependencies_defaults_threshold_to_1_when_absent(tmp_path: Path) -> None:
    """A profile without an explicit threshold falls back to the safe default."""

    ctx = _write_finisher_yamls(tmp_path)

    deps = load_finisher_dependencies(ctx)

    assert deps.tier2_confidence_threshold == pytest.approx(1.0)
    assert "profile:" in deps.profile_yaml


def test_load_finisher_dependencies_reads_threshold_override(tmp_path: Path) -> None:
    """A profile-set threshold overrides the default."""

    ctx = _write_finisher_yamls(tmp_path, threshold=0.87)

    deps = load_finisher_dependencies(ctx)

    assert deps.tier2_confidence_threshold == pytest.approx(0.87)


def test_load_finisher_dependencies_falls_back_on_garbage_threshold(tmp_path: Path) -> None:
    """A non-numeric threshold logs a warning and uses the default."""

    profile_path = tmp_path / "profile.yaml"
    defer_path = tmp_path / "defer.yaml"
    cache_path = tmp_path / "cache.yaml"

    profile_path.write_text(
        yaml.safe_dump(
            {
                "apply_prefs": {
                    "application_defaults": {"tier2_confidence_threshold": "not-a-number"}
                }
            }
        ),
        encoding="utf-8",
    )
    defer_path.write_text(_DEFER_RULES_TEXT, encoding="utf-8")
    cache_path.write_text(_ANSWER_CACHE_TEXT, encoding="utf-8")

    ctx = FinisherContext(
        target_company="Acme",
        target_role="SWE",
        job_description="",
        candidate_profile_path=profile_path,
        defer_rules_path=defer_path,
        answer_cache_path=cache_path,
        safe_mode=False,
    )

    deps = load_finisher_dependencies(ctx)

    assert deps.tier2_confidence_threshold == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# excerpt_job_description
# ---------------------------------------------------------------------------


def test_excerpt_job_description_returns_short_text_unchanged() -> None:
    """Texts shorter than the cap return without an ellipsis marker."""

    text = "A very short JD body."
    assert excerpt_job_description(text) == text


def test_excerpt_job_description_handles_empty_input() -> None:
    """Empty input returns empty string (after strip)."""

    assert excerpt_job_description("") == ""
    assert excerpt_job_description("   ") == ""


def test_excerpt_job_description_truncates_with_sentinel() -> None:
    """Long text is truncated and carries the ``(excerpted)`` sentinel."""

    text = "x" * 20_000
    excerpted = excerpt_job_description(text)
    assert excerpted.endswith("\n...(excerpted)")
    assert len(excerpted) <= 6_000 + len("\n...(excerpted)")


# ---------------------------------------------------------------------------
# supported_finisher_ats
# ---------------------------------------------------------------------------


def test_supported_finisher_ats_unsupported_returns_none() -> None:
    """Every non-Greenhouse / non-Ashby ATS resolves to None."""

    for ats in (
        ATSPlatform.LEVER,
        ATSPlatform.WORKDAY,
        ATSPlatform.ICIMS,
        ATSPlatform.SMARTRECRUITERS,
        ATSPlatform.UNKNOWN,
    ):
        assert supported_finisher_ats(ats) is None


# ---------------------------------------------------------------------------
# try_submit_and_classify
# ---------------------------------------------------------------------------


def _submitted_page(initial_url: str, after_click_url: str) -> FakeFinisherPage:
    """Build a page whose submit-button click mutates the URL after firing."""

    page = FakeFinisherPage(url=initial_url)
    submit_selector = "#application_form button[type='submit']"
    real_locator = page.locator

    def new_locator(selector: str) -> Any:
        loc = real_locator(selector)
        if selector == submit_selector:
            real_click = loc.click

            async def patched_click() -> None:
                await real_click()
                page.url = after_click_url

            loc.click = patched_click  # type: ignore[method-assign]
        return loc

    page.locator = new_locator  # type: ignore[method-assign]
    return page


def test_try_submit_classifies_url_change_as_submitted() -> None:
    """A URL change inside the wait window lands SUBMITTED with no errors."""

    page = _submitted_page(
        initial_url="https://boards.greenhouse.io/foo/jobs/123/apply",
        after_click_url="https://boards.greenhouse.io/foo/jobs/123/confirmation",
    )

    outcome, errors = asyncio.run(
        try_submit_and_classify(page=page, ats_platform=ATSPlatform.GREENHOUSE)  # type: ignore[arg-type]
    )

    assert outcome == ApplyOutcome.SUBMITTED
    assert errors == []


def test_try_submit_classifies_unchanged_url_with_toast_as_needs_review() -> None:
    """No URL change + a visible toast → NEEDS_REVIEW with scraped errors."""

    class _ToastPage(FakeFinisherPage):
        """Page whose error-selector locators return one alert string."""

        def __init__(self) -> None:
            super().__init__(url="https://example.com/apply")
            self.wait_for_url_should_raise = True

        def locator(self, selector: str) -> object:  # type: ignore[override]
            if selector in {
                "[role='alert']",
                ".error",
                ".invalid-feedback",
                ".field-error",
            }:
                return _ToastLocator(selector)
            return super().locator(selector)

    class _ToastLocator:
        """Tiny locator that exposes one toast string per selector."""

        def __init__(self, selector: str) -> None:
            self._selector = selector

        async def count(self) -> int:
            return 1 if self._selector == "[role='alert']" else 0

        def nth(self, index: int) -> "_ToastLocator":
            _ = index
            return self

        async def text_content(self) -> str:
            return "Required field missing: email"

        @property
        def first(self) -> "_ToastLocator":
            return self

        async def click(self) -> None:  # pragma: no cover - submit selector path
            return None

    page = _ToastPage()
    outcome, errors = asyncio.run(
        try_submit_and_classify(page=page, ats_platform=ATSPlatform.GREENHOUSE)  # type: ignore[arg-type]
    )

    assert outcome == ApplyOutcome.NEEDS_REVIEW
    assert "Required field missing: email" in errors


def test_try_submit_classifies_silent_failure_as_failed_other() -> None:
    """No URL change and no toast → FAILED_OTHER for the retry path."""

    page = FakeFinisherPage(url="https://example.com/apply", wait_for_url_should_raise=True)

    outcome, errors = asyncio.run(
        try_submit_and_classify(page=page, ats_platform=ATSPlatform.GREENHOUSE)  # type: ignore[arg-type]
    )

    assert outcome == ApplyOutcome.FAILED_OTHER
    assert errors == []


def test_try_submit_handles_click_failure_with_failed_other() -> None:
    """A submit click that itself raises lands FAILED_OTHER with the message."""

    page = FakeFinisherPage(url="https://example.com/apply")
    real_locator = page.locator

    def raising_locator(selector: str) -> Any:
        loc = real_locator(selector)
        if "button[type='submit']" in selector:
            async def raise_click() -> None:
                raise RuntimeError("click intercepted")
            loc.click = raise_click  # type: ignore[method-assign]
        return loc

    page.locator = raising_locator  # type: ignore[method-assign]

    outcome, errors = asyncio.run(
        try_submit_and_classify(page=page, ats_platform=ATSPlatform.GREENHOUSE)  # type: ignore[arg-type]
    )

    assert outcome == ApplyOutcome.FAILED_OTHER
    assert errors and "submit_click_failed" in errors[0]


def test_try_submit_falls_back_to_needs_review_for_unknown_ats() -> None:
    """An ATS without a configured selector returns NEEDS_REVIEW immediately."""

    outcome, errors = asyncio.run(
        try_submit_and_classify(page=FakeFinisherPage(), ats_platform=ATSPlatform.WORKDAY)  # type: ignore[arg-type]
    )

    assert outcome == ApplyOutcome.NEEDS_REVIEW
    assert errors == []


# ---------------------------------------------------------------------------
# evaluate_submit_gate — extra branches not covered in smoke
# ---------------------------------------------------------------------------


def test_evaluate_submit_gate_returns_finisher_incomplete_when_all_required_unfilled() -> None:
    """An ``all_required_filled=False`` COMPLETE result fails the gate."""

    result = FinisherResult(outcome="COMPLETE", all_required_filled=False)

    can, label = evaluate_submit_gate(
        finisher_result=result,
        tier2_confidence_threshold=1.0,
        dry_run=False,
        safe_mode=False,
    )

    assert (can, label) == (False, "finisher_incomplete")


# ---------------------------------------------------------------------------
# synthesize_diagnostics — populated case
# ---------------------------------------------------------------------------


def test_synthesize_diagnostics_forwards_submit_errors_and_gate_label() -> None:
    """Submit errors and the gate label flow into diagnostics verbatim."""

    result = FinisherResult(outcome="COMPLETE", all_required_filled=True)

    diag = synthesize_diagnostics(
        finisher_result=result,
        simplify_no_op=False,
        submit_errors=["email required"],
        gate_decision="auto_submit",
    )

    assert diag.submit_errors == ["email required"]
    assert diag.gate_decision == "auto_submit"
    assert diag.finisher_outcome == "COMPLETE"
