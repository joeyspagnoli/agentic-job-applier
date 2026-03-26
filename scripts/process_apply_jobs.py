#!/usr/bin/env python3
"""Process reviewed jobs by applying via browser automation.

Purpose:
    Provide an autonomous apply worker that claims reviewed jobs, opens
    them in Chrome via CDP, triggers Simplify autofill, uploads the
    tailored resume, and captures diagnostics.  In v1 dry-run mode, all
    runs stop before submit and land as NEEDS_REVIEW.

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
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

from src.agents.apply_worker.browser import apply_to_job
from src.agents.apply_worker.browser import check_chrome_reachable
from src.agents.apply_worker.schemas import ApplyOutcome
from src.agents.apply_worker.schemas import DEFAULT_CDP_URL
from src.database.db_manager import DEFAULT_APPLY_CLAIM_LEASE_SECONDS
from src.database.db_manager import DatabaseManager
from src.utils.notifications import send_ntfy_notification
from src.utils.paths import resolve_database_path
from src.utils.paths import resolve_repo_root

DEFAULT_APPLY_POLL_INTERVAL_SECONDS = 60
DEFAULT_APPLY_MAX_RETRIES = 2
DEFAULT_APPLY_RETRY_BACKOFF_SECONDS = 1800  # 30 min between retries
DEFAULT_APPLY_RETRY_BACKOFF_MULTIPLIER = 2
DEFAULT_APPLY_OUTPUT_DIR = "data/apply_runs"
DEFAULT_APPLY_DRY_RUN = True
SQLITE_UTC_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

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


def _load_bool_env(name: str, default_value: bool) -> bool:
    """Read a boolean from environment and fall back safely.

    Purpose:
        Parse common boolean representations from environment variables.
    Args:
        name: Environment variable name to read.
        default_value: Fallback boolean when parsing fails.
    Output:
        Returns parsed boolean value.
    """

    raw_value = os.getenv(name)
    if raw_value is None:
        return default_value

    return raw_value.lower() in ("true", "1", "yes")


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
    return backoff_seconds * (backoff_multiplier**exponent)


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


def _resolve_resume_path(claimed_row: dict[str, object]) -> tuple[Path, str]:
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
        f"No resume PDF found for review_run "
        f"{claimed_row.get('review_run_id')}"
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
    review_run_id: int,
    error: str,
    outcome: str | None,
    max_retries: int,
    backoff_seconds: int,
    backoff_multiplier: int,
    screenshot_path: str | None = None,
    dom_snapshot_path: str | None = None,
    ats_platform: str | None = None,
    page_url: str | None = None,
) -> None:
    """Record an apply failure with retry scheduling.

    Purpose:
        Persist failure details and compute the next retry timestamp
        based on the current failure count and backoff parameters.
    Args:
        db: Database manager instance.
        run_id: Apply run primary key.
        review_run_id: Review run this apply attempt belongs to.
        error: Human-readable error description.
        outcome: Optional failure classification.
        max_retries: Maximum retries allowed.
        backoff_seconds: Base backoff delay.
        backoff_multiplier: Exponential backoff factor.
        screenshot_path: Path to any captured screenshot.
        dom_snapshot_path: Path to any captured DOM snapshot.
        ats_platform: Detected ATS platform.
        page_url: Final page URL.
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

    await db.record_apply_failure(
        run_id=run_id,
        error=error,
        next_retry_at=next_retry_at,
        outcome=outcome,
        screenshot_path=screenshot_path,
        dom_snapshot_path=dom_snapshot_path,
        ats_platform=ats_platform,
        page_url=page_url,
    )

    if current_attempt >= max_retries:
        logger.warning(
            "Apply run {} reached max retries ({}) for review_run_id={}",
            run_id,
            max_retries,
            review_run_id,
        )
        await _notify_terminal_failure(run_id, review_run_id, error)


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

    claimed_row = await db.claim_next_apply_job(
        max_retries=max_retries,
        lease_seconds=lease_seconds,
    )
    if claimed_row is None:
        return 0

    run_id: int = claimed_row["_apply_run_id"]
    job_hash: str = str(claimed_row["job_hash"])
    review_run_id: int = claimed_row["review_run_id"]
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
            review_run_id=review_run_id,
            error=str(exc),
            outcome=ApplyOutcome.FAILED_OTHER.value,
            max_retries=0,  # Terminal, no retry
            backoff_seconds=backoff_seconds,
            backoff_multiplier=backoff_multiplier,
        )
        return 1

    # Resolve the resume PDF path from the review verdict
    try:
        resume_pdf_path, resume_source = _resolve_resume_path(claimed_row)
    except FileNotFoundError as exc:
        await _handle_apply_failure(
            db=db,
            run_id=run_id,
            review_run_id=review_run_id,
            error=str(exc),
            outcome=ApplyOutcome.FAILED_UPLOAD.value,
            max_retries=0,  # Terminal, no retry
            backoff_seconds=backoff_seconds,
            backoff_multiplier=backoff_multiplier,
        )
        return 1

    artifact_dir = output_base_dir / job_hash
    logger.info(
        "Using {} resume: {} for job_hash={}",
        resume_source,
        resume_pdf_path,
        job_hash,
    )

    # Run the browser automation
    try:
        result = await apply_to_job(
            cdp_url=cdp_url,
            source_url=source_url,
            resume_pdf_path=resume_pdf_path,
            job_hash=job_hash,
            artifact_dir=artifact_dir,
            dry_run=dry_run,
        )
    except Exception as exc:
        logger.exception(
            "Browser automation failed for job_hash={}: {}", job_hash, exc,
        )
        await _handle_apply_failure(
            db=db,
            run_id=run_id,
            review_run_id=review_run_id,
            error=f"Browser automation error: {exc}",
            outcome=ApplyOutcome.FAILED_OTHER.value,
            max_retries=max_retries,
            backoff_seconds=backoff_seconds,
            backoff_multiplier=backoff_multiplier,
        )
        return 1

    # Persist the result
    if result.success:
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

        await db.record_apply_success(
            run_id=run_id,
            outcome=result.outcome.value if result.outcome else "NEEDS_REVIEW",
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
            ats_platform=(
                result.ats_platform.value if result.ats_platform else None
            ),
            page_url=result.page_url,
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
            review_run_id=review_run_id,
            error=result.failure_reason or "Unknown failure",
            outcome=(
                result.outcome.value if result.outcome else None
            ),
            max_retries=max_retries,
            backoff_seconds=backoff_seconds,
            backoff_multiplier=backoff_multiplier,
            screenshot_path=result.screenshot_path,
            dom_snapshot_path=result.dom_snapshot_path,
            ats_platform=(
                result.ats_platform.value if result.ats_platform else None
            ),
            page_url=result.page_url,
        )

    return 1


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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=None,
        help="Skip the submit step (default for v1)",
    )
    parser.add_argument(
        "--no-dry-run",
        action="store_true",
        default=False,
        help="Enable auto-submit when confidence is high",
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

    # Resolve dry_run: CLI flags > env var > default
    if args.no_dry_run:
        dry_run = False
    elif args.dry_run is not None:
        dry_run = True
    else:
        dry_run = _load_bool_env("APPLY_DRY_RUN", DEFAULT_APPLY_DRY_RUN)

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
