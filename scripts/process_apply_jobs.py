#!/usr/bin/env python3
"""Process reviewed jobs by applying via browser automation.

Purpose:
    Provide an autonomous apply worker that claims reviewed jobs, opens
    them in Chrome via CDP, triggers Simplify autofill, uploads the
    tailored resume, and captures diagnostics.  Auto-submit is hard-
    disabled for this release: the worker always runs in dry-run mode,
    so every successful flow stops before submit and lands as
    NEEDS_REVIEW with an `apply_handoffs` row for the user to review
    and submit manually.  See SECURITY.md for the policy.

Run once (default):
  uv run python -m scripts.process_apply_jobs

Run continuously:
  APPLY_POLL_INTERVAL_SECONDS=60 uv run python -m scripts.process_apply_jobs --loop
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from collections.abc import Mapping
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

from src.agents.apply_worker.browser import apply_to_job
from src.agents.apply_worker.browser import check_chrome_reachable
from src.agents.apply_worker.finisher_integration import (
    FinisherContext,
    safe_mode_from_env,
)
from src.agents.apply_worker.schemas import ApplyOutcome
from src.agents.apply_worker.schemas import DEFAULT_CDP_URL
from src.database._mixins.system_settings import APPLY_MODE_KEY
from src.database.db_manager import ClaimOwnershipError
from src.database.db_manager import DEFAULT_APPLY_CLAIM_LEASE_SECONDS
from src.database.db_manager import DatabaseManager
from src.utils.cost_tracking import PIPELINE_STAGE_APPLY
from src.utils.cost_tracking import check_budget_before_claim
from src.utils.cost_tracking import record_apply_browser_stub
from src.utils.notifications import send_ntfy_notification
from src.utils.paths import resolve_database_path
from src.utils.paths import resolve_repo_root

# Repo-relative paths for finisher resources. Resolved against
# ``resolve_repo_root()`` per call so a different deploy layout works.
CANDIDATE_PROFILE_REL_PATH = "config/candidate_profile.yaml"
DEFER_RULES_REL_PATH = "config/defer_rules.yaml"
ANSWER_CACHE_REL_PATH = "data/answer_cache.yaml"

DEFAULT_APPLY_POLL_INTERVAL_SECONDS = 60
DEFAULT_APPLY_MAX_RETRIES = 2
DEFAULT_APPLY_RETRY_BACKOFF_SECONDS = 1800  # 30 min between retries
DEFAULT_APPLY_RETRY_BACKOFF_MULTIPLIER = 2
DEFAULT_APPLY_OUTPUT_DIR = "data/apply_runs"
SQLITE_UTC_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
HUMAN_REVIEW_HANDOFF_OUTCOME = ApplyOutcome.NEEDS_REVIEW.value
AUTO_SUBMIT_DISABLED_MESSAGE = (
    "Auto-submit is disabled in this release. "
    "Forms will be filled but not submitted."
)

# When the autonomous toggle is OFF, the apply row is set to `opt_in` and the
# loop must skip claiming entirely so a stopped Chrome cannot drive jobs into
# FAILED rows.
APPLY_OPT_IN_MODE = "opt_in"
APPLY_AUTONOMOUS_MODES: frozenset[str] = frozenset({"autonomous", "both"})

_JOB_HASH_RE = re.compile(r"^[a-f0-9]{32,64}$")


class ApplyPreflightError(RuntimeError):
    """Represent a fatal preflight check failure for the apply worker."""


def _validate_job_hash(job_hash: str) -> None:
    """Validate that job_hash is a safe hexadecimal hash string.

    Purpose:
        Prevent path traversal and malformed-run directory writes by rejecting
        unexpected job hash values before filesystem operations.
    Args:
        job_hash: Hash string returned by apply claim query.
    Output:
        Returns `None` when hash is valid.
    Raises:
        ValueError: When job_hash is not a 32-64 lowercase hex string.
    """

    if not _JOB_HASH_RE.match(job_hash):
        raise ValueError(
            f"Invalid job_hash format - expected 32-64 hex chars, got {job_hash!r}"
        )


def _build_finisher_context(claimed_row: Mapping[str, object]) -> FinisherContext:
    """Build a per-run :class:`FinisherContext` from the claimed job row.

    Purpose:
        Centralize the conversion of DB row fields + repo paths into
        the typed context the apply-finisher needs so the call site
        stays a one-liner.
    Args:
        claimed_row: Row returned by ``claim_next_apply_job`` (carries
            ``title``, ``company``, ``description`` from
            ``job_postings``).
    Returns:
        A frozen :class:`FinisherContext`.
    """

    repo_root = resolve_repo_root()
    target_company_raw = claimed_row.get("company")
    target_role_raw = claimed_row.get("title")
    description_raw = claimed_row.get("description")

    target_company = (
        str(target_company_raw) if isinstance(target_company_raw, str) else "the company"
    )
    target_role = (
        str(target_role_raw) if isinstance(target_role_raw, str) else "this role"
    )
    description = str(description_raw) if isinstance(description_raw, str) else ""

    return FinisherContext(
        target_company=target_company,
        target_role=target_role,
        job_description=description,
        candidate_profile_path=repo_root / CANDIDATE_PROFILE_REL_PATH,
        defer_rules_path=repo_root / DEFER_RULES_REL_PATH,
        answer_cache_path=repo_root / ANSWER_CACHE_REL_PATH,
        safe_mode=safe_mode_from_env(),
    )


def _load_int_env(name: str, default_value: int) -> int:
    """Read a positive integer from environment and fall back safely.

    Purpose:
        Keep worker tuning knobs resilient to missing or invalid env values.
    Args:
        name: Environment variable name to read.
        default_value: Fallback integer when parsing fails.
    Output:
        Returns positive integer value.
    """

    raw_value = os.getenv(name)
    if raw_value is None:
        return default_value

    try:
        parsed_value = int(raw_value)
    except ValueError:
        logger.warning(
            "Invalid integer for {}='{}'; using default {}",
            name,
            raw_value,
            default_value,
        )
        return default_value

    if parsed_value <= 0:
        logger.warning(
            "Non-positive value for {}={}; using default {}",
            name,
            parsed_value,
            default_value,
        )
        return default_value

    return parsed_value


def _calculate_retry_delay_seconds(
    *,
    retry_count: int,
    backoff_seconds: int,
    backoff_multiplier: int,
) -> int:
    """Calculate backoff delay seconds for the next retry attempt.

    Purpose:
        Centralize retry-backoff formula used by the apply worker.
    Args:
        retry_count: Retry count being scheduled (1-based).
        backoff_seconds: Base delay in seconds for first retry.
        backoff_multiplier: Multiplicative factor for each additional retry.
    Output:
        Returns computed delay in seconds.
    """

    exponent = max(retry_count - 1, 0)
    return int(backoff_seconds * (backoff_multiplier**exponent))


def _calculate_next_retry_at(
    *,
    retry_count: int,
    backoff_seconds: int,
    backoff_multiplier: int,
) -> str:
    """Calculate the UTC timestamp for the next retry attempt.

    Purpose:
        Produce a SQLite-compatible UTC timestamp for apply retry scheduling.
    Args:
        retry_count: Retry count being scheduled (1-based).
        backoff_seconds: Base delay in seconds for first retry.
        backoff_multiplier: Multiplicative factor for each additional retry.
    Output:
        Returns `%Y-%m-%d %H:%M:%S` UTC timestamp string.
    """

    delay = _calculate_retry_delay_seconds(
        retry_count=retry_count,
        backoff_seconds=backoff_seconds,
        backoff_multiplier=backoff_multiplier,
    )
    next_retry_at_utc = datetime.now(tz=timezone.utc) + timedelta(seconds=delay)
    return next_retry_at_utc.strftime(SQLITE_UTC_TIMESTAMP_FORMAT)


def _resolve_resume_path(claimed_row: Mapping[str, object]) -> tuple[Path, str]:
    """Determine the correct resume PDF path from the review verdict.

    Selects the tailored resume for PASS/TAILORED verdicts and the
    base resume for BASE verdicts.

    Args:
        claimed_row: Merged row dict from claim_next_apply_job containing
            review_verdict, selected_pdf_path, and fallback_base_pdf_path.

    Returns:
        A tuple of (pdf_path, resume_source) where resume_source is
        either "TAILORED" or "BASE".

    Raises:
        FileNotFoundError: When no resume PDF can be found on disk.
    """

    verdict = str(claimed_row.get("review_verdict", ""))

    if verdict in ("PASS", "TAILORED"):
        selected = claimed_row.get("selected_pdf_path")
        if selected and Path(str(selected)).exists():
            return Path(str(selected)), "TAILORED"

    # BASE verdict or missing selected path -> use fallback
    fallback = claimed_row.get("fallback_base_pdf_path")
    if fallback and Path(str(fallback)).exists():
        return Path(str(fallback)), "BASE"

    raise FileNotFoundError(
        f"No resume PDF found for review_run {claimed_row.get('review_run_id')}"
    )


def _check_preflight(cdp_url: str) -> None:
    """Run synchronous preflight checks before starting the worker.

    Purpose:
        Fail fast on missing dependencies, unreachable Chrome, or
        missing display configuration.
    Args:
        cdp_url: Chrome CDP endpoint to verify.
    Output:
        Returns `None` when all checks pass.
    Raises:
        ApplyPreflightError: When any preflight check fails.
    """

    # Check playwright is importable
    try:
        import playwright  # noqa: F401
    except ImportError as exc:
        raise ApplyPreflightError(
            "playwright not installed. Run: uv pip install playwright"
        ) from exc

    # Check DISPLAY is set on Linux (needed for Xvfb + extensions)
    if sys.platform == "linux" and not os.getenv("DISPLAY"):
        raise ApplyPreflightError(
            "DISPLAY not set. Chrome with extensions requires a display. "
            "Start Xvfb first: Xvfb :99 -screen 0 1920x1080x24 & "
            "export DISPLAY=:99"
        )


async def _check_chrome_preflight(cdp_url: str) -> None:
    """Verify Chrome is reachable over CDP.

    Args:
        cdp_url: Chrome CDP endpoint to verify.

    Raises:
        ApplyPreflightError: When Chrome is not reachable.
    """

    reachable = await check_chrome_reachable(cdp_url)
    if not reachable:
        raise ApplyPreflightError(
            f"Chrome not reachable at {cdp_url}. "
            f"Start Chrome with: google-chrome --remote-debugging-port=9222"
        )


async def _handle_apply_failure(
    *,
    db: DatabaseManager,
    run_id: int,
    claim_token: str,
    review_run_id: int,
    job_hash: str | None,
    error: str,
    outcome: str | None,
    max_retries: int,
    backoff_seconds: int,
    backoff_multiplier: int,
    screenshot_path: str | None = None,
    dom_snapshot_path: str | None = None,
    ats_platform: str | None = None,
    page_url: str | None = None,
    work_executed: bool = True,
) -> None:
    """Record an apply failure with retry scheduling.

    Purpose:
        Persist failure details and compute the next retry timestamp
        based on the current failure count and backoff parameters.
    Args:
        db: Database manager instance.
        run_id: Apply run primary key.
        claim_token: Claim token that owns the pending apply run.
        review_run_id: Review run this apply attempt belongs to.
        job_hash: Optional stable job hash for this apply run.
        error: Human-readable error description.
        outcome: Optional failure classification.
        max_retries: Maximum retries allowed.
        backoff_seconds: Base backoff delay.
        backoff_multiplier: Exponential backoff factor.
        screenshot_path: Path to any captured screenshot.
        dom_snapshot_path: Path to any captured DOM snapshot.
        ats_platform: Detected ATS platform.
        page_url: Final page URL.
        work_executed: Whether stage work executed and should incur cost.
    Output:
        Returns `None` after recording the failure.
    """

    failure_count = await db.get_apply_failure_count(review_run_id)
    # The current run is already PENDING, so the failure count
    # represents previous failures.  The next retry is based on
    # failure_count + 1.
    current_attempt = failure_count + 1

    next_retry_at: str | None = None
    if current_attempt < max_retries:
        next_retry_at = _calculate_next_retry_at(
            retry_count=current_attempt,
            backoff_seconds=backoff_seconds,
            backoff_multiplier=backoff_multiplier,
        )

    try:
        await db.record_apply_failure(
            run_id=run_id,
            claim_token=claim_token,
            error=error,
            next_retry_at=next_retry_at,
            outcome=outcome,
            screenshot_path=screenshot_path,
            dom_snapshot_path=dom_snapshot_path,
            ats_platform=ats_platform,
            page_url=page_url,
        )
    except ClaimOwnershipError as exc:
        logger.warning(
            "Skipping stale apply failure write for run_id={}: {}",
            run_id,
            exc,
        )
        return
    if work_executed:
        await _record_apply_cost_best_effort(
            db=db,
            job_hash=job_hash,
            run_id=run_id,
            metadata={
                "status": "FAILED",
                "review_run_id": review_run_id,
                "outcome": outcome,
                "attempt": current_attempt,
                "max_retries": max_retries,
            },
        )

    if current_attempt >= max_retries:
        logger.warning(
            "Apply run {} reached max retries ({}) for review_run_id={}",
            run_id,
            max_retries,
            review_run_id,
        )
        await _notify_terminal_failure(run_id, review_run_id, error)


async def _record_apply_cost_best_effort(
    *,
    db: DatabaseManager,
    job_hash: str | None,
    run_id: int,
    metadata: Mapping[str, object],
) -> None:
    """Persist apply-stage cost telemetry without breaking core flow.

    Purpose:
        Keep handoff and run-state persistence authoritative by treating
        telemetry write failures as non-fatal operational diagnostics.
    Args:
        db: Database manager used for cost persistence.
        job_hash: Optional stable job hash associated with the run.
        run_id: Apply run identifier used in telemetry row.
        metadata: Structured telemetry metadata for the event.
    Output:
        Returns `None` after best-effort telemetry recording.
    """

    try:
        await record_apply_browser_stub(
            db=db,
            job_hash=job_hash,
            run_id=str(run_id),
            metadata=metadata,
        )
    except Exception as exc:
        logger.warning(
            "Apply cost telemetry write failed for run_id={}: {}",
            run_id,
            exc,
        )


async def _notify_terminal_failure(
    run_id: int,
    review_run_id: int,
    error: str,
) -> None:
    """Send a notification when an apply run reaches terminal failure.

    Args:
        run_id: Apply run primary key.
        review_run_id: Review run identifier.
        error: Failure description.
    """

    try:
        await send_ntfy_notification(
            title="Apply Worker: Terminal Failure",
            message=(
                f"Apply run {run_id} (review_run={review_run_id}) "
                f"reached terminal failure: {error}"
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to send terminal-failure notification: {}", exc)


async def _apply_once(
    *,
    db: DatabaseManager,
    output_base_dir: Path,
    cdp_url: str,
    max_retries: int,
    lease_seconds: int,
    backoff_seconds: int,
    backoff_multiplier: int,
    dry_run: bool,
) -> int:
    """Claim and process one eligible apply job.

    Purpose:
        Execute one apply cycle: claim a reviewed job, run the browser
        automation, and persist the result.
    Args:
        db: Database manager instance.
        output_base_dir: Base directory for apply run artifacts.
        cdp_url: Chrome CDP endpoint URL.
        max_retries: Maximum failed attempts per review run.
        lease_seconds: Claim lease duration in seconds.
        backoff_seconds: Base retry backoff delay.
        backoff_multiplier: Exponential backoff factor.
        dry_run: Whether to skip the submit step.
    Output:
        Returns 1 if a job was processed, 0 if no eligible jobs found.
    """

    if not await check_budget_before_claim(db=db, stage=PIPELINE_STAGE_APPLY):
        return 0

    claimed_row = await db.claim_next_apply_job(
        max_retries=max_retries,
        lease_seconds=lease_seconds,
    )
    if claimed_row is None:
        return 0

    apply_run_id_raw = claimed_row["_apply_run_id"]
    if not isinstance(apply_run_id_raw, int):
        logger.error("Invalid _apply_run_id type: {}", type(apply_run_id_raw))
        return 0
    run_id: int = apply_run_id_raw

    apply_claim_token_raw = claimed_row.get("_apply_claim_token")
    if not isinstance(apply_claim_token_raw, str) or not apply_claim_token_raw:
        logger.error(
            "Invalid _apply_claim_token type/value for run_id={}: {}",
            run_id,
            type(apply_claim_token_raw),
        )
        return 0
    apply_claim_token = apply_claim_token_raw

    job_hash: str = str(claimed_row["job_hash"])

    review_run_id_raw = claimed_row["review_run_id"]
    if not isinstance(review_run_id_raw, int):
        logger.error("Invalid review_run_id type: {}", type(review_run_id_raw))
        return 0
    review_run_id: int = review_run_id_raw
    source_url: str = str(claimed_row["source_url"])

    logger.info(
        "Processing apply run: run_id={} job_hash={} review_run_id={} url={}",
        run_id,
        job_hash,
        review_run_id,
        source_url,
    )

    # Validate job_hash before using it in filesystem paths
    try:
        _validate_job_hash(job_hash)
    except ValueError as exc:
        await _handle_apply_failure(
            db=db,
            run_id=run_id,
            claim_token=apply_claim_token,
            review_run_id=review_run_id,
            job_hash=job_hash,
            error=str(exc),
            outcome=ApplyOutcome.FAILED_OTHER.value,
            max_retries=0,  # Terminal, no retry
            backoff_seconds=backoff_seconds,
            backoff_multiplier=backoff_multiplier,
            work_executed=False,
        )
        return 1

    # Resolve the resume PDF path from the review verdict
    try:
        resume_pdf_path, resume_source = _resolve_resume_path(claimed_row)
    except FileNotFoundError as exc:
        await _handle_apply_failure(
            db=db,
            run_id=run_id,
            claim_token=apply_claim_token,
            review_run_id=review_run_id,
            job_hash=job_hash,
            error=str(exc),
            outcome=ApplyOutcome.FAILED_UPLOAD.value,
            max_retries=0,  # Terminal, no retry
            backoff_seconds=backoff_seconds,
            backoff_multiplier=backoff_multiplier,
            work_executed=False,
        )
        return 1

    artifact_dir = output_base_dir / job_hash
    logger.info(
        "Using {} resume: {} for job_hash={}",
        resume_source,
        resume_pdf_path,
        job_hash,
    )

    finisher_context = _build_finisher_context(claimed_row)

    # Run the browser automation
    try:
        result = await apply_to_job(
            cdp_url=cdp_url,
            source_url=source_url,
            resume_pdf_path=resume_pdf_path,
            job_hash=job_hash,
            artifact_dir=artifact_dir,
            dry_run=dry_run,
            finisher_context=finisher_context,
        )
    except Exception as exc:
        logger.exception(
            "Browser automation failed for job_hash={}: {}",
            job_hash,
            exc,
        )
        await _handle_apply_failure(
            db=db,
            run_id=run_id,
            claim_token=apply_claim_token,
            review_run_id=review_run_id,
            job_hash=job_hash,
            error=f"Browser automation error: {exc}",
            outcome=ApplyOutcome.FAILED_OTHER.value,
            max_retries=max_retries,
            backoff_seconds=backoff_seconds,
            backoff_multiplier=backoff_multiplier,
        )
        return 1

    # Persist the result
    if result.success:
        resolved_outcome = (
            result.outcome.value if result.outcome else HUMAN_REVIEW_HANDOFF_OUTCOME
        )
        confidence_json = (
            result.confidence_report.model_dump_json()
            if result.confidence_report
            else None
        )
        unresolved_json = (
            json.dumps(
                [f.model_dump() for f in result.unresolved_fields],
                ensure_ascii=False,
            )
            if result.unresolved_fields
            else None
        )

        try:
            await db.record_apply_success(
                run_id=run_id,
                claim_token=apply_claim_token,
                outcome=resolved_outcome,
                resume_pdf_path=str(resume_pdf_path),
                resume_source=resume_source,
                confidence_score=result.confidence_score,
                confidence_report_json=confidence_json,
                screenshot_path=result.screenshot_path,
                dom_snapshot_path=result.dom_snapshot_path,
                unresolved_fields_json=unresolved_json,
                simplify_autofill_detected=(
                    result.confidence_report.simplify_autofill_detected
                    if result.confidence_report
                    else None
                ),
                ats_platform=(result.ats_platform.value if result.ats_platform else None),
                page_url=result.page_url,
            )
        except ClaimOwnershipError as exc:
            logger.warning(
                "Skipping stale apply success write for run_id={}: {}",
                run_id,
                exc,
            )
            return 1

        if resolved_outcome == HUMAN_REVIEW_HANDOFF_OUTCOME:
            deferred_questions_json = (
                json.dumps(result.deferred_questions, ensure_ascii=False)
                if result.deferred_questions
                else None
            )
            finisher_diagnostics_json = (
                result.finisher_diagnostics.model_dump_json()
                if result.finisher_diagnostics
                else None
            )
            await db.record_apply_handoff(
                apply_run_id=run_id,
                job_hash=job_hash,
                review_run_id=review_run_id,
                apply_outcome=resolved_outcome,
                resume_source=resume_source,
                resume_pdf_path=str(resume_pdf_path),
                confidence_score=result.confidence_score,
                confidence_report_json=confidence_json,
                unresolved_fields_json=unresolved_json,
                screenshot_path=result.screenshot_path,
                dom_snapshot_path=result.dom_snapshot_path,
                deferred_questions_json=deferred_questions_json,
                finisher_diagnostics_json=finisher_diagnostics_json,
                ats_platform=(
                    result.ats_platform.value if result.ats_platform else None
                ),
                page_url=result.page_url,
            )

        await _record_apply_cost_best_effort(
            db=db,
            job_hash=job_hash,
            run_id=run_id,
            metadata={
                "status": "SUCCESS",
                "review_run_id": review_run_id,
                "outcome": resolved_outcome,
                "resume_source": resume_source,
            },
        )

        logger.info(
            "Apply run {} completed: outcome={} score={:.4f} for job_hash={}",
            run_id,
            result.outcome,
            result.confidence_score or 0.0,
            job_hash,
        )
    else:
        await _handle_apply_failure(
            db=db,
            run_id=run_id,
            claim_token=apply_claim_token,
            review_run_id=review_run_id,
            job_hash=job_hash,
            error=result.failure_reason or "Unknown failure",
            outcome=(result.outcome.value if result.outcome else None),
            max_retries=max_retries,
            backoff_seconds=backoff_seconds,
            backoff_multiplier=backoff_multiplier,
            screenshot_path=result.screenshot_path,
            dom_snapshot_path=result.dom_snapshot_path,
            ats_platform=(result.ats_platform.value if result.ats_platform else None),
            page_url=result.page_url,
        )

    return 1


async def _is_apply_mode_active(db: DatabaseManager) -> bool:
    """Return True when the stored apply mode permits claiming this cycle.

    Purpose:
        Hard-gate the apply loop on per-stage automation mode so a
        non-autonomous user never has the apply worker claim a job from
        underneath them.
    Args:
        db: Connected database manager.
    Output:
        Returns `True` for `autonomous` and `both`; `False` otherwise.
    """

    mode = await db.get_automation_mode(APPLY_MODE_KEY)
    if mode in APPLY_AUTONOMOUS_MODES:
        return True
    if mode == APPLY_OPT_IN_MODE:
        logger.debug("Apply mode is opt_in; skipping claim this cycle")
        return False
    logger.warning("Unknown apply mode {!r}; treating as opt_in", mode)
    return False


async def run_apply_loop(
    *,
    db: DatabaseManager,
    output_base_dir: Path,
    cdp_url: str,
    max_retries: int = DEFAULT_APPLY_MAX_RETRIES,
    lease_seconds: int = DEFAULT_APPLY_CLAIM_LEASE_SECONDS,
    backoff_seconds: int = DEFAULT_APPLY_RETRY_BACKOFF_SECONDS,
    backoff_multiplier: int = DEFAULT_APPLY_RETRY_BACKOFF_MULTIPLIER,
    poll_interval_seconds: int = DEFAULT_APPLY_POLL_INTERVAL_SECONDS,
    dry_run: bool = True,
) -> None:
    """Run the apply worker poll loop using a shared database manager.

    Purpose:
        Provide an importable entry point so the API supervisor can run
        the apply loop as an in-process asyncio task. The loop reads the
        per-stage automation mode every cycle and additionally sleeps
        without claiming whenever host Chrome is not reachable over CDP,
        so a closed browser never produces FAILED rows.
    Args:
        db: Connected database manager shared with other in-process loops.
        output_base_dir: Per-run artifact root.
        cdp_url: Chrome CDP endpoint URL.
        max_retries: Maximum FAILED attempts per review run.
        lease_seconds: Claim lease length.
        backoff_seconds: Base retry backoff delay.
        backoff_multiplier: Exponential backoff factor per retry.
        poll_interval_seconds: Sleep duration between cycles.
        dry_run: Whether to skip the submit step (always True today).
    Output:
        Returns `None` only on `asyncio.CancelledError` (re-raised).
    """

    logger.info(
        "Apply loop entering poll: poll={}s lease={}s max_retries={} "
        "dry_run={} cdp_url={}",
        poll_interval_seconds,
        lease_seconds,
        max_retries,
        dry_run,
        cdp_url,
    )

    while True:
        try:
            if not await _is_apply_mode_active(db):
                await asyncio.sleep(poll_interval_seconds)
                continue
            chrome_reachable = await check_chrome_reachable(cdp_url)
            if not chrome_reachable:
                logger.debug(
                    "Apply loop: Chrome unreachable at {}; sleeping without claim",
                    cdp_url,
                )
                await asyncio.sleep(poll_interval_seconds)
                continue
            processed = await _apply_once(
                db=db,
                output_base_dir=output_base_dir,
                cdp_url=cdp_url,
                max_retries=max_retries,
                lease_seconds=lease_seconds,
                backoff_seconds=backoff_seconds,
                backoff_multiplier=backoff_multiplier,
                dry_run=dry_run,
            )
            if processed == 0:
                await asyncio.sleep(poll_interval_seconds)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Apply polling cycle failed: {}", exc)
            await asyncio.sleep(poll_interval_seconds)


async def main() -> None:
    """Entry point for the apply worker."""

    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Apply to reviewed jobs via browser automation",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        default=False,
        help="Run continuously, polling for new jobs",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        default=False,
        help="Process one job and exit (default behavior)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=DEFAULT_APPLY_OUTPUT_DIR,
        help=f"Base directory for apply run artifacts (default: {DEFAULT_APPLY_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--database-path",
        type=str,
        default=None,
        help="Override database path (falls back to DATABASE_PATH env or default)",
    )
    parser.add_argument(
        "--cdp-url",
        type=str,
        default=None,
        help=(
            "Chrome CDP endpoint URL. "
            f"Falls back to CHROME_CDP_URL env or {DEFAULT_CDP_URL}"
        ),
    )
    args = parser.parse_args()

    should_loop = args.loop and not args.once
    poll_interval_seconds = _load_int_env(
        "APPLY_POLL_INTERVAL_SECONDS",
        DEFAULT_APPLY_POLL_INTERVAL_SECONDS,
    )
    max_retries = _load_int_env("APPLY_MAX_RETRIES", DEFAULT_APPLY_MAX_RETRIES)
    backoff_seconds = _load_int_env(
        "APPLY_RETRY_BACKOFF_SECONDS",
        DEFAULT_APPLY_RETRY_BACKOFF_SECONDS,
    )
    backoff_multiplier = _load_int_env(
        "APPLY_RETRY_BACKOFF_MULTIPLIER",
        DEFAULT_APPLY_RETRY_BACKOFF_MULTIPLIER,
    )
    lease_seconds = _load_int_env(
        "APPLY_CLAIM_LEASE_SECONDS",
        DEFAULT_APPLY_CLAIM_LEASE_SECONDS,
    )
    cdp_url = args.cdp_url or os.getenv("CHROME_CDP_URL", DEFAULT_CDP_URL)

    # Auto-submit is gated by the apply-finisher result; ``SAFE_MODE=true``
    # is the env-driven kill switch documented in `.env.example` and
    # SECURITY.md. ``dry_run`` here is the worker-wide ceiling — the per-job
    # gate inside ``_run_application_flow`` is the policy decision point.
    dry_run = safe_mode_from_env()
    if dry_run:
        logger.info(AUTO_SUBMIT_DISABLED_MESSAGE)
    else:
        logger.info(
            "Apply worker: auto-submit gate ENABLED. "
            "Set SAFE_MODE=true to disable globally.",
        )

    # Synchronous preflight checks
    try:
        _check_preflight(cdp_url)
    except ApplyPreflightError as exc:
        logger.error("Apply preflight failed: {}", exc)
        return

    # Async preflight: check Chrome is reachable
    try:
        await _check_chrome_preflight(cdp_url)
    except ApplyPreflightError as exc:
        logger.error("Apply preflight failed: {}", exc)
        return

    repo_root = resolve_repo_root()

    output_base_dir = Path(args.output_dir)
    if not output_base_dir.is_absolute():
        output_base_dir = repo_root / output_base_dir
    output_base_dir = output_base_dir.resolve()

    if args.database_path:
        database_path = Path(args.database_path).resolve()
    else:
        database_path = resolve_database_path()

    async with DatabaseManager(str(database_path)) as db:
        await db.create_tables()
        await db.migrate_review_schema()
        await db.migrate_apply_schema()
        await db.migrate_cost_schema()

        stale_count = await db.mark_stale_apply_runs_failed(
            lease_seconds=lease_seconds,
        )
        if stale_count > 0:
            logger.warning(
                "Marked {} stale PENDING apply runs as FAILED on startup",
                stale_count,
            )

        if not should_loop:
            await _apply_once(
                db=db,
                output_base_dir=output_base_dir,
                cdp_url=cdp_url,
                max_retries=max_retries,
                lease_seconds=lease_seconds,
                backoff_seconds=backoff_seconds,
                backoff_multiplier=backoff_multiplier,
                dry_run=dry_run,
            )
            return

        logger.info(
            "Apply worker entering loop: poll={}s lease={}s max_retries={} "
            "dry_run={} cdp_url={}",
            poll_interval_seconds,
            lease_seconds,
            max_retries,
            dry_run,
            cdp_url,
        )

        while True:
            processed = 0
            try:
                processed = await _apply_once(
                    db=db,
                    output_base_dir=output_base_dir,
                    cdp_url=cdp_url,
                    max_retries=max_retries,
                    lease_seconds=lease_seconds,
                    backoff_seconds=backoff_seconds,
                    backoff_multiplier=backoff_multiplier,
                    dry_run=dry_run,
                )
                logger.info("Apply cycle complete: processed={}", processed)
            except Exception as exc:
                logger.exception("Apply polling cycle failed: {}", exc)

            if processed == 0:
                await asyncio.sleep(poll_interval_seconds)


if __name__ == "__main__":
    asyncio.run(main())
