"""Glue layer between the apply worker and the apply-finisher agent.

Owns three responsibilities:

1. Build a ``FinisherContext`` from worker inputs (job row + repo
   paths) and load the per-run finisher dependencies (defer rules,
   answer cache, serialized profile, gate threshold).
2. Decide whether the run is eligible for auto-submit
   (``evaluate_submit_gate``).
3. Click submit and classify the result into one of three outcomes
   (SUBMITTED / NEEDS_REVIEW / FAILED) by inspecting the URL change
   plus any visible error toasts (``try_submit_and_classify``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from loguru import logger

from src.agents.apply_finisher.answer_cache import AnswerCache, load_answer_cache
from src.agents.apply_finisher.defer_rules import DeferRules, load_defer_rules
from src.agents.apply_finisher.schemas import (
    FinisherResult,
    SupportedAts,
)
from src.agents.apply_worker.schemas import (
    ApplyOutcome,
    ATSPlatform,
    FinisherDiagnostics,
)

if TYPE_CHECKING:  # pragma: no cover - type-only
    from playwright.async_api import Page

# Default soft tier-2 confidence threshold. The candidate profile's
# ``application_defaults.tier2_confidence_threshold`` overrides this.
_DEFAULT_TIER2_THRESHOLD: float = 1.0

# Maximum text length pulled from the job description into the agent's
# user-prompt. Sub-agent D budgets ~1500 tokens (≈ 6_000 chars).
_JOB_DESCRIPTION_EXCERPT_MAX_CHARS: int = 6_000

# Selectors checked for error toasts after a submit click.
_SUBMIT_ERROR_SELECTORS: tuple[str, ...] = (
    "[role='alert']",
    ".error",
    ".invalid-feedback",
    ".field-error",
)

# Wait budget after submit click for URL navigation OR success element.
_SUBMIT_URL_WAIT_TIMEOUT_MS: int = 5_000

# ATS-specific submit button selectors used by ``try_submit_and_classify``.
# Greenhouse renders a single ``button[type=submit]`` under
# ``#application_form``. Ashby uses ``button[type=submit]`` with the
# accessible name "Submit application".
_SUBMIT_BUTTON_SELECTORS: dict[ATSPlatform, str] = {
    ATSPlatform.GREENHOUSE: "#application_form button[type='submit']",
    ATSPlatform.ASHBY: "form button[type='submit']",
}

# Map ATS detector enum → SupportedAts literal expected by the finisher.
_SUPPORTED_FINISHER_ATS: dict[ATSPlatform, SupportedAts] = {
    ATSPlatform.GREENHOUSE: "greenhouse",
    ATSPlatform.ASHBY: "ashby",
}


@dataclass(frozen=True)
class FinisherContext:
    """Per-run inputs for the apply-finisher loop.

    Attributes:
        target_company: Company name from the job posting.
        target_role: Role title from the job posting.
        job_description: Full JD body; the worker excerpts it when
            building the user prompt.
        candidate_profile_path: Repo-resolved path to
            ``candidate_profile.yaml``.
        defer_rules_path: Repo-resolved path to ``defer_rules.yaml``.
        answer_cache_path: Repo-resolved path to ``answer_cache.yaml``.
        safe_mode: When True, disables auto-submit regardless of the
            gate decision (env-driven kill switch).
    """

    target_company: str
    target_role: str
    job_description: str
    candidate_profile_path: Path
    defer_rules_path: Path
    answer_cache_path: Path
    safe_mode: bool


@dataclass(frozen=True)
class FinisherDependencies:
    """Loaded finisher resources for one run.

    Attributes:
        defer_rules: Compiled defer-rule classifier.
        answer_cache: Loaded answer cache.
        profile_yaml: Pre-serialized candidate profile YAML.
        tier2_confidence_threshold: Threshold from the profile's
            ``application_defaults.tier2_confidence_threshold``.
    """

    defer_rules: DeferRules
    answer_cache: AnswerCache
    profile_yaml: str
    tier2_confidence_threshold: float


def load_finisher_dependencies(context: FinisherContext) -> FinisherDependencies:
    """Read the YAML inputs the finisher needs to run.

    Purpose:
        Centralize the file I/O so the worker stays focused on browser
        orchestration. Each load is a single read with no caching —
        the apply loop is rate-limited by Chrome, not by YAML parsing.
    Args:
        context: Per-run context with absolute paths.
    Returns:
        Populated :class:`FinisherDependencies`.
    """

    defer_rules = load_defer_rules(context.defer_rules_path)
    answer_cache = load_answer_cache(context.answer_cache_path)

    raw_profile_text = context.candidate_profile_path.read_text(encoding="utf-8")
    profile_obj = yaml.safe_load(raw_profile_text) or {}

    threshold = _DEFAULT_TIER2_THRESHOLD
    apply_prefs = (
        profile_obj.get("apply_prefs", {}) if isinstance(profile_obj, dict) else {}
    )
    if isinstance(apply_prefs, dict):
        application_defaults = apply_prefs.get("application_defaults") or {}
        if isinstance(application_defaults, dict):
            raw_threshold = application_defaults.get(
                "tier2_confidence_threshold", _DEFAULT_TIER2_THRESHOLD
            )
            try:
                threshold = float(raw_threshold)
            except (TypeError, ValueError):
                logger.warning(
                    "Invalid tier2_confidence_threshold={!r}; using default {}",
                    raw_threshold,
                    _DEFAULT_TIER2_THRESHOLD,
                )
                threshold = _DEFAULT_TIER2_THRESHOLD

    return FinisherDependencies(
        defer_rules=defer_rules,
        answer_cache=answer_cache,
        profile_yaml=raw_profile_text,
        tier2_confidence_threshold=threshold,
    )


def excerpt_job_description(description: str) -> str:
    """Trim a job description to fit the agent's context budget.

    Args:
        description: Full JD text from the job posting.
    Returns:
        The first ``_JOB_DESCRIPTION_EXCERPT_MAX_CHARS`` characters,
        with an ellipsis marker when truncation happened.
    """

    cleaned = (description or "").strip()
    if len(cleaned) <= _JOB_DESCRIPTION_EXCERPT_MAX_CHARS:
        return cleaned
    return cleaned[:_JOB_DESCRIPTION_EXCERPT_MAX_CHARS] + "\n...(excerpted)"


def supported_finisher_ats(ats: ATSPlatform) -> SupportedAts | None:
    """Return the finisher literal for an ATS, or ``None`` when unsupported.

    Purpose:
        Lever / Workday / iCIMS stay out-of-scope in v1 per the plan.
        Callers use this to short-circuit before allocating finisher
        dependencies.
    Args:
        ats: Detected ATS platform.
    Returns:
        The finisher dialect or ``None`` when out-of-scope.
    """

    return _SUPPORTED_FINISHER_ATS.get(ats)


def evaluate_submit_gate(
    *,
    finisher_result: FinisherResult,
    tier2_confidence_threshold: float,
    dry_run: bool,
    safe_mode: bool,
) -> tuple[bool, str]:
    """Decide whether the worker should fire the submit click.

    Purpose:
        Implement the binary v1 gate from the locked plan:
        ``all_required_filled AND no_tier3_deferred AND (no_tier2_pending
        OR all_tier2_drafts >= threshold)``.
        ``dry_run`` (caller-passed) and ``SAFE_MODE`` (env-driven) are
        defensive ceilings the gate cannot override.
    Args:
        finisher_result: Output of the finisher loop.
        tier2_confidence_threshold: Threshold from the candidate
            profile's ``application_defaults``.
        dry_run: Caller-passed dry-run flag.
        safe_mode: ``SAFE_MODE`` env kill switch.
    Returns:
        ``(can_auto_submit, gate_decision_label)``. The label is one of
        ``"auto_submit"``, ``"dry_run"``, ``"safe_mode"``,
        ``"finisher_incomplete"``, ``"tier2_pending"``, or
        ``"tier3_deferred"`` so diagnostics can record why the gate
        chose its branch.
    """

    if safe_mode:
        return False, "safe_mode"
    if dry_run:
        return False, "dry_run"

    if finisher_result.outcome != "COMPLETE":
        return False, "finisher_incomplete"
    if not finisher_result.all_required_filled:
        return False, "finisher_incomplete"
    if finisher_result.has_tier3_deferred:
        return False, "tier3_deferred"

    if finisher_result.has_tier2_pending:
        drafts = finisher_result.drafted_fields_flagged_for_verify
        all_pass = all(
            draft.confidence >= tier2_confidence_threshold for draft in drafts
        )
        if not all_pass:
            return False, "tier2_pending"

    return True, "auto_submit"


def _is_safe_mode() -> bool:
    """Read the ``SAFE_MODE`` env var as a boolean.

    Returns:
        True when ``SAFE_MODE`` is set to ``true`` / ``1`` / ``yes`` /
        ``on`` (case-insensitive). Anything else, including unset,
        returns False so the gate may fire.
    """

    raw = os.environ.get("SAFE_MODE", "").strip().lower()
    return raw in {"true", "1", "yes", "on"}


def safe_mode_from_env() -> bool:
    """Public re-export of the env-driven safe-mode check.

    Lets callers (apply_to_job, process_apply_jobs) avoid duplicating
    the env parsing rules.
    """

    return _is_safe_mode()


async def try_submit_and_classify(
    *,
    page: "Page",
    ats_platform: ATSPlatform,
) -> tuple[ApplyOutcome, list[str]]:
    """Click the submit button and classify the result.

    Purpose:
        Single helper the worker calls once the gate authorizes
        auto-submit. Waits up to 5s for a URL change (the canonical
        success signal). If the URL doesn't change, scrapes visible
        error toasts: presence of a toast → ``NEEDS_REVIEW`` (validation
        failure the human can fix); absence → ``FAILED_OTHER`` (network
        / captcha / silent rejection, handled by the existing retry
        path).
    Args:
        page: Playwright async page sitting on the filled form.
        ats_platform: Detected ATS platform; selects the submit selector.
    Returns:
        ``(outcome, submit_errors)``. ``submit_errors`` is the scraped
        toast text (empty when the submit succeeded or no toast).
    """

    selector = _SUBMIT_BUTTON_SELECTORS.get(ats_platform)
    if selector is None:
        logger.warning(
            "No submit selector configured for {}; leaving as NEEDS_REVIEW",
            ats_platform,
        )
        return ApplyOutcome.NEEDS_REVIEW, []

    pre_submit_url = page.url

    try:
        await page.locator(selector).first.click()
    except Exception as exc:
        logger.warning("Submit click failed via {}: {}", selector, exc)
        return ApplyOutcome.FAILED_OTHER, [f"submit_click_failed: {exc}"]

    # Wait up to 5s for the URL to change (the canonical success signal).
    try:
        await page.wait_for_url(
            lambda url: url != pre_submit_url,
            timeout=_SUBMIT_URL_WAIT_TIMEOUT_MS,
        )
        logger.info("Submit succeeded — URL changed to {}", page.url)
        return ApplyOutcome.SUBMITTED, []
    except Exception:
        logger.info(
            "Submit waited {}ms without URL change; scraping toasts",
            _SUBMIT_URL_WAIT_TIMEOUT_MS,
        )

    # URL didn't change — scrape toasts to classify validation vs network.
    toast_texts: list[str] = []
    for toast_selector in _SUBMIT_ERROR_SELECTORS:
        try:
            locator = page.locator(toast_selector)
            count = await locator.count()
            for index in range(count):
                text = (await locator.nth(index).text_content()) or ""
                cleaned = text.strip()
                if cleaned:
                    toast_texts.append(cleaned)
        except Exception as exc:  # pragma: no cover - best-effort scrape
            logger.debug("Toast scrape {} failed: {}", toast_selector, exc)

    if toast_texts:
        logger.info("Submit blocked by validation: {}", toast_texts[:3])
        return ApplyOutcome.NEEDS_REVIEW, toast_texts

    # No toast + no URL change → treat as a recoverable infra failure so
    # the existing exponential-backoff retry path kicks in.
    logger.warning("Submit had no URL change and no visible toast — FAILED")
    return ApplyOutcome.FAILED_OTHER, []


def synthesize_diagnostics(
    *,
    finisher_result: FinisherResult | None,
    simplify_no_op: bool,
    submit_errors: list[str],
    gate_decision: str,
) -> FinisherDiagnostics:
    """Build the persistence-ready ``FinisherDiagnostics`` payload.

    Args:
        finisher_result: Output of the finisher loop, or ``None`` when
            the finisher was not invoked (unsupported ATS).
        simplify_no_op: Result of ``verify_after_fill``.
        submit_errors: Error toasts scraped after a submit attempt.
        gate_decision: Label from :func:`evaluate_submit_gate`.
    Returns:
        Populated :class:`FinisherDiagnostics`.
    """

    if finisher_result is None:
        return FinisherDiagnostics(
            finisher_outcome="SKIPPED",
            simplify_no_op=simplify_no_op,
            submit_errors=submit_errors,
            gate_decision=gate_decision,
        )

    drafts = [
        {
            "field_id": d.field_id,
            "label": d.label,
            "drafted_value": d.drafted_value,
            "confidence": d.confidence,
            "reasoning": d.reasoning,
        }
        for d in finisher_result.drafted_fields_flagged_for_verify
    ]

    return FinisherDiagnostics(
        finisher_outcome=finisher_result.outcome,
        turns_used=finisher_result.turns_used,
        cost_usd=finisher_result.cost_usd,
        fields_filled=finisher_result.fields_filled,
        fields_deferred=finisher_result.fields_deferred,
        all_required_filled=finisher_result.all_required_filled,
        has_tier3_deferred=finisher_result.has_tier3_deferred,
        has_tier2_pending=finisher_result.has_tier2_pending,
        drafted_fields=drafts,
        simplify_no_op=simplify_no_op,
        submit_errors=submit_errors,
        gate_decision=gate_decision,
    )


__all__ = [
    "FinisherContext",
    "FinisherDependencies",
    "evaluate_submit_gate",
    "excerpt_job_description",
    "load_finisher_dependencies",
    "safe_mode_from_env",
    "supported_finisher_ats",
    "synthesize_diagnostics",
    "try_submit_and_classify",
]
