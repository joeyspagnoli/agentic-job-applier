"""Schema definitions for the browser-based apply worker.

Purpose:
    Define strict outcome, confidence, field-scan, and run-result contracts
    used by the apply worker to persist diagnostics and drive future agent
    repair passes.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel
from pydantic import Field


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SIMPLIFY_POLL_INTERVAL_MS = 500
"""Milliseconds between DOM polls when waiting for Simplify activation."""

SIMPLIFY_POLL_TIMEOUT_MS = 45_000
"""Maximum wait time for Simplify extension to inject its UI markers.

Verified on 2026-05-07: Simplify v2.4.6 takes ~15s on Greenhouse to render
its full UI with the Autofill button. 45s leaves headroom for slower pages.
"""

FORM_STABILITY_WAIT_MS = 2_000
"""Milliseconds of DOM inactivity before considering the form stable."""

DEFAULT_PAGE_LOAD_TIMEOUT_MS = 30_000
"""Maximum wait time for initial page navigation and network idle."""

DEFAULT_CDP_URL = "http://localhost:9222"
"""Default Chrome DevTools Protocol endpoint for CDP connections."""


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ApplyOutcome(str, Enum):
    """Represent the application-level result of a browser apply run.

    Purpose:
        Separate the run lifecycle status (PENDING/SUCCESS/FAILED) from the
        application outcome so workers can distinguish between a run that
        completed successfully but needs human review versus one that was
        auto-submitted.
    """

    NEEDS_REVIEW = "NEEDS_REVIEW"
    SUBMITTED = "SUBMITTED"
    FAILED_PREFILL = "FAILED_PREFILL"
    FAILED_UPLOAD = "FAILED_UPLOAD"
    FAILED_NAVIGATION = "FAILED_NAVIGATION"
    FAILED_OTHER = "FAILED_OTHER"


def apply_outcome_check_sql(column: str = "apply_outcome") -> str:
    """Build the `<column> IN (...)` clause used in DB CHECK constraints.

    Purpose:
        Generate the `IN (...)` value list from `ApplyOutcome` so the
        Python enum is the single source of truth. Adding a new outcome
        only requires editing the enum; every CHECK that imports this
        helper picks up the new value automatically.
    Args:
        column: Column name to constrain. Defaults to `apply_outcome`
            which matches the names used by `apply_runs` and
            `apply_handoffs`.
    Output:
        Returns a SQL fragment of the form ``apply_outcome IN ('A', 'B')``.
    """

    values = ", ".join(repr(item.value) for item in ApplyOutcome)
    return f"{column} IN ({values})"


class ATSPlatform(str, Enum):
    """Identify the applicant tracking system hosting a job application.

    Purpose:
        Provide diagnostic classification for logging and future
        platform-specific heuristics without driving form interaction.
    """

    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    WORKDAY = "workday"
    ICIMS = "icims"
    ASHBY = "ashby"
    SMARTRECRUITERS = "smartrecruiters"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Field scanning models
# ---------------------------------------------------------------------------


class UnresolvedField(BaseModel):
    """Capture rich metadata for a single form field left unresolved.

    Purpose:
        Store enough context about each unfilled field that a future agent
        repair pass can propose values without re-opening the browser.

    Attributes:
        field_id: CSS id or unique identifier for the field element.
        label: Human-readable label text extracted from the form.
        field_type: HTML input type (text, select, radio, checkbox, etc.).
        is_required: Whether the field is marked as required.
        current_value: Current value in the field (empty string if blank).
        validation_error: Any visible validation error text near the field.
        options: Available options for select/radio/checkbox fields.
        selector: CSS selector that uniquely identifies this field.
        parent_form_selector: CSS selector for the enclosing form element.
        placeholder: Placeholder text from the field, if present.
    """

    field_id: str | None = None
    label: str | None = None
    field_type: str
    is_required: bool
    current_value: str = ""
    validation_error: str | None = None
    options: list[str] | None = None
    selector: str
    parent_form_selector: str | None = None
    placeholder: str | None = None


# ---------------------------------------------------------------------------
# Confidence scoring models
# ---------------------------------------------------------------------------


class ConfidenceCheck(BaseModel):
    """Record the result of a single deterministic confidence check.

    Purpose:
        Provide an auditable breakdown of each weighted factor that
        contributed to the overall confidence score.

    Attributes:
        name: Short identifier for the check (e.g. "resume_uploaded").
        passed: Whether the check passed.
        weight: Contribution to the overall score when passed.
        detail: Optional human-readable context about the result.
    """

    name: str
    passed: bool
    weight: float
    detail: str | None = None


class ConfidenceReport(BaseModel):
    """Aggregate deterministic confidence signals for an apply attempt.

    Purpose:
        Provide a single auditable payload that captures the weighted
        confidence score and every individual check so submission
        decisions are transparent and reproducible.

    Attributes:
        score: Overall confidence score in the range [0.0, 1.0].
        checks: Ordered list of individual check results.
        has_hard_blockers: True if any hard-blocker condition was detected.
        resume_uploaded: Whether the tailored resume was successfully uploaded.
        simplify_autofill_detected: Whether Simplify extension activated.
        unresolved_required_count: Number of required fields left empty.
        unresolved_optional_count: Number of optional fields left empty.
        ats_platform: Detected ATS platform for this application.
    """

    score: float = Field(ge=0.0, le=1.0)
    checks: list[ConfidenceCheck] = Field(default_factory=list)
    has_hard_blockers: bool = False
    resume_uploaded: bool = False
    simplify_autofill_detected: bool = False
    unresolved_required_count: int = 0
    unresolved_optional_count: int = 0
    ats_platform: ATSPlatform = ATSPlatform.UNKNOWN


# ---------------------------------------------------------------------------
# Finisher diagnostics
# ---------------------------------------------------------------------------


class FinisherDiagnostics(BaseModel):
    """Telemetry payload persisted to ``apply_handoffs.finisher_diagnostics_json``.

    Purpose:
        Bundle every signal the human reviewer needs to debug a
        NEEDS_REVIEW or FAILED outcome — the finisher's terminal state,
        cost / turn counters, the Tier-2 drafts, the verify-after-fill
        result, and any submit-time error toasts. Stored as JSON in the
        ``apply_handoffs`` row added in issue #59.

    Attributes:
        finisher_outcome: ``COMPLETE`` / ``AGENT_GAVE_UP`` /
            ``USAGE_LIMIT_HIT`` / ``RUNTIME_ERROR`` / ``SKIPPED`` (the
            last when the finisher was not invoked, e.g. Lever).
        turns_used: Number of agent iterations consumed.
        cost_usd: USD cost computed via ``litellm.cost_per_token``.
        fields_filled: Tier-1 fills the agent reported.
        fields_deferred: Tier-3 fields the agent skipped.
        all_required_filled: True when every required field is
            either filled or drafted.
        has_tier3_deferred: Convenience mirror of
            ``len(deferred_questions) > 0``.
        has_tier2_pending: True when any draft is awaiting human review.
        drafted_fields: Tier-2 drafts with per-field confidence scores.
        simplify_no_op: True when post-Simplify verify saw all known
            fields empty (telemetry only).
        submit_errors: Error-toast text scraped after a submit attempt.
            Empty when the gate did not fire submit.
        gate_decision: ``"auto_submit"`` / ``"dry_run"`` / ``"skipped"``
            describing which gate branch fired.
    """

    finisher_outcome: str = "SKIPPED"
    turns_used: int = 0
    cost_usd: float = 0.0
    fields_filled: int = 0
    fields_deferred: int = 0
    all_required_filled: bool = False
    has_tier3_deferred: bool = False
    has_tier2_pending: bool = False
    drafted_fields: list[dict[str, Any]] = Field(default_factory=list)
    simplify_no_op: bool = False
    submit_errors: list[str] = Field(default_factory=list)
    gate_decision: str = "skipped"


# ---------------------------------------------------------------------------
# Run result model
# ---------------------------------------------------------------------------


class ApplyRunResult(BaseModel):
    """Represent the final output payload from one browser apply attempt.

    Purpose:
        Return deterministic success/failure state with full diagnostics
        so the polling script can persist outcomes and the user can review
        captured artifacts.

    Attributes:
        success: Whether the browser run completed without fatal errors.
        outcome: The application-level result (NEEDS_REVIEW, SUBMITTED, etc.).
        failure_reason: Human-readable explanation when success is False.
        resume_pdf_path: Absolute path to the resume PDF that was uploaded.
        resume_source: Whether the TAILORED or BASE resume was used.
        confidence_score: Overall confidence score from deterministic checks.
        confidence_report: Full breakdown of confidence checks.
        screenshot_path: Path to the captured pre-submit screenshot.
        dom_snapshot_path: Path to the saved page HTML.
        unresolved_fields: Rich metadata for every unresolved form field.
        ats_platform: Detected ATS platform.
        page_url: Final page URL after any redirects.
        finisher_diagnostics: Issue #59 finisher telemetry (None when
            the finisher was not invoked, e.g. unsupported ATS).
        deferred_questions: Tier-3 questions the finisher logged; the
            worker persists these to
            ``apply_handoffs.deferred_questions_json``.
    """

    success: bool
    outcome: ApplyOutcome | None = None
    failure_reason: str | None = None
    resume_pdf_path: str | None = None
    resume_source: str | None = None
    confidence_score: float | None = None
    confidence_report: ConfidenceReport | None = None
    screenshot_path: str | None = None
    dom_snapshot_path: str | None = None
    unresolved_fields: list[UnresolvedField] = Field(default_factory=list)
    ats_platform: ATSPlatform | None = None
    page_url: str | None = None
    finisher_diagnostics: FinisherDiagnostics | None = None
    deferred_questions: list[dict[str, Any]] = Field(default_factory=list)


__all__ = [
    "DEFAULT_CDP_URL",
    "DEFAULT_PAGE_LOAD_TIMEOUT_MS",
    "FORM_STABILITY_WAIT_MS",
    "SIMPLIFY_POLL_INTERVAL_MS",
    "SIMPLIFY_POLL_TIMEOUT_MS",
    "ATSPlatform",
    "ApplyOutcome",
    "ApplyRunResult",
    "ConfidenceCheck",
    "ConfidenceReport",
    "FinisherDiagnostics",
    "UnresolvedField",
]
