#!/usr/bin/env python3
"""Process tailored resumes with the pi-mono review pipeline.

Purpose:
    Provide an autonomous review worker that claims successful tailor runs,
    invokes the pi-mono review runtime, and persists verdicts/diagnostics.

Run once (default):
  uv run python -m scripts.process_reviewed_resumes

Run continuously:
  REVIEW_POLL_INTERVAL_SECONDS=30 uv run python -m scripts.process_reviewed_resumes --loop
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

from src.agents.resume_review_pi import ReviewInvocationContract
from src.agents.resume_review_pi import ReviewRunResult
from src.agents.resume_review_pi import run_resume_review_pipeline
from src.agents.resume_tailor_pi.compiler import compile_resume_tex
from src.agents.resume_tailor_pi.renderer import render_resume_yaml_to_tex
from src.database.db_manager import DEFAULT_REVIEW_CLAIM_LEASE_SECONDS
from src.database.db_manager import DatabaseManager
from src.utils.cost_tracking import PIPELINE_STAGE_REVIEW
from src.utils.cost_tracking import record_stage_cost_event
from src.utils.notifications import send_ntfy_notification
from src.utils.paths import resolve_database_path
from src.utils.paths import resolve_repo_root

DEFAULT_REVIEW_POLL_INTERVAL_SECONDS = 30
DEFAULT_REVIEW_MAX_RETRIES = 2
DEFAULT_REVIEW_RETRY_BACKOFF_SECONDS = 600
DEFAULT_REVIEW_RETRY_BACKOFF_MULTIPLIER = 2
DEFAULT_REVIEW_OUTPUT_DIR = "data/tailored_resumes"
DEFAULT_REVIEW_BASE_RESUME_YAML_PATH = "config/resume_content.yaml"
DEFAULT_REVIEW_BASE_ARTIFACT_DIR = "data/tailored_resumes/_base_reference"

_JOB_HASH_RE = re.compile(r"^[a-f0-9]{32,64}$")


class ReviewPreflightError(RuntimeError):
    """Represent a fatal preflight check failure for the review worker."""


def _validate_job_hash(job_hash: str) -> None:
    """Validate that job_hash is a safe hexadecimal hash string.

    Purpose:
        Prevent path traversal and malformed-run directory writes by rejecting
        unexpected job hash values before filesystem operations.
    Args:
        job_hash: Hash string returned by review claim query.
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


def _calculate_retry_delay_seconds(
    *,
    retry_count: int,
    backoff_seconds: int,
    backoff_multiplier: int,
) -> int:
    """Calculate backoff delay seconds for the next retry attempt.

    Purpose:
        Centralize retry-backoff formula used by the review worker.
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
    """Calculate UTC timestamp string for the next retry attempt.

    Purpose:
        Produce SQLite-compatible retry timestamps for transient failures.
    Args:
        retry_count: Retry count being scheduled (1-based).
        backoff_seconds: Base delay in seconds for first retry.
        backoff_multiplier: Multiplicative factor per retry step.
    Output:
        Returns `%Y-%m-%d %H:%M:%S` UTC timestamp string.
    """

    delay_seconds = _calculate_retry_delay_seconds(
        retry_count=retry_count,
        backoff_seconds=backoff_seconds,
        backoff_multiplier=backoff_multiplier,
    )
    scheduled_time = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
    return scheduled_time.strftime("%Y-%m-%d %H:%M:%S")


def _resolve_required_binary(binary_name: str) -> None:
    """Verify one required binary exists in PATH.

    Purpose:
        Keep preflight checks concise and actionable for missing dependencies.
    Args:
        binary_name: Command name that must resolve in PATH.
    Output:
        Returns `None` when binary exists.
    Raises:
        ReviewPreflightError: When binary is missing.
    """

    if shutil.which(binary_name) is None:
        raise ReviewPreflightError(f"{binary_name} not found in PATH")


def _check_preflight() -> None:
    """Validate review worker dependencies and runtime prerequisites.

    Purpose:
        Fail fast before entering polling loop when required tools or paths are
        unavailable.
    Args:
        None.
    Output:
        Returns `None` when checks pass.
    Raises:
        ReviewPreflightError: When required command or path is missing.
    """

    has_pi_env = bool(
        os.getenv("PI_CODING_AGENT_COMMAND", "").strip()
        or os.getenv("PI_CODING_AGENT_COMMAND_ARGV", "").strip()
    )
    has_pi_binary = shutil.which("pi") is not None
    if not has_pi_env and not has_pi_binary:
        raise ReviewPreflightError(
            "pi command not found. Set PI_CODING_AGENT_COMMAND or "
            "PI_CODING_AGENT_COMMAND_ARGV in .env, or ensure 'pi' is in PATH."
        )

    _resolve_required_binary("latexmk")
    _resolve_required_binary("pdfinfo")
    _resolve_required_binary("pdftotext")
    _resolve_required_binary("pdftoppm")

    try:
        database_path = resolve_database_path()
    except RuntimeError as exc:
        raise ReviewPreflightError(f"Database path resolution failed: {exc}") from exc

    if not database_path.parent.exists():
        raise ReviewPreflightError(
            f"Database parent directory does not exist: {database_path.parent}"
        )


async def _notify_terminal_failure(
    *,
    job_hash: str,
    tailor_run_id: int,
    error: str,
    retry_count: int,
) -> None:
    """Send ntfy alert for terminal review-stage failure.

    Purpose:
        Notify operators when a tailored resume exhausts review retries and
        manual intervention may be required.
    Args:
        job_hash: Job hash for the failed review candidate.
        tailor_run_id: Tailor run identifier for traceability.
        error: Terminal failure reason text.
        retry_count: Number of failed review attempts.
    Output:
        Returns `None` after best-effort notification.
    """

    await send_ntfy_notification(
        title="Resume review terminal failure",
        message=(
            "Resume review exhausted retries and needs intervention.\n"
            f"job_hash={job_hash}\n"
            f"tailor_run_id={tailor_run_id}\n"
            f"retry_count={retry_count}\n"
            f"error={error}"
        ),
        tags=("warning", "page_facing_up"),
        priority="high",
    )


async def _notify_preflight_failure(error: str) -> None:
    """Send one-time ntfy alert for review preflight failure.

    Purpose:
        Surface fatal startup misconfiguration to operators.
    Args:
        error: Preflight error text describing missing dependency or path.
    Output:
        Returns `None` after best-effort notification.
    """

    await send_ntfy_notification(
        title="Resume review worker preflight failure",
        message=(
            f"Review worker could not start due to preflight failure.\nerror={error}"
        ),
        tags=("warning", "gear"),
        priority="high",
    )


def _resolve_tailored_yaml_path(job_row: dict[str, object]) -> Path:
    """Resolve tailored YAML work-copy path from claimed review row fields.

    Purpose:
        Keep review-worker path resolution compatible with old tailor rows that
        may not yet store `artifact_yaml_path`.
    Args:
        job_row: Claimed review row containing tailor artifact fields.
    Output:
        Returns absolute path to tailored YAML work copy.
    """

    artifact_yaml_path = str(job_row.get("artifact_yaml_path") or "").strip()
    if artifact_yaml_path != "":
        return Path(artifact_yaml_path).resolve()

    artifact_tex_path = str(job_row.get("artifact_tex_path") or "").strip()
    if artifact_tex_path != "":
        return (
            Path(artifact_tex_path).resolve().parent / "resume_content_work.yaml"
        ).resolve()

    job_hash = str(job_row.get("job_hash") or "")
    return (
        Path(DEFAULT_REVIEW_OUTPUT_DIR).resolve()
        / job_hash
        / "resume_content_work.yaml"
    ).resolve()


def _ensure_base_reference_artifacts(
    *,
    base_yaml_path: Path,
    base_tex_path: Path,
    base_pdf_path: Path,
) -> None:
    """Ensure base resume TeX/PDF references exist and are up to date.

    Purpose:
        Keep every review run grounded to deterministic base references without
        requiring manual base-artifact preparation.
    Args:
        base_yaml_path: Canonical base resume YAML path.
        base_tex_path: Target base reference TeX path.
        base_pdf_path: Target base reference PDF path.
    Output:
        Returns `None` after ensuring both artifacts exist.
    Raises:
        RuntimeError: When base YAML does not exist or render/compile fails.
    """

    if not base_yaml_path.exists():
        raise RuntimeError(f"Base YAML path does not exist: {base_yaml_path}")

    base_tex_path.parent.mkdir(parents=True, exist_ok=True)
    base_pdf_path.parent.mkdir(parents=True, exist_ok=True)

    should_rebuild = False
    if not base_tex_path.exists() or not base_pdf_path.exists():
        should_rebuild = True
    else:
        yaml_mtime = base_yaml_path.stat().st_mtime
        tex_mtime = base_tex_path.stat().st_mtime
        pdf_mtime = base_pdf_path.stat().st_mtime
        should_rebuild = yaml_mtime > tex_mtime or yaml_mtime > pdf_mtime

    if not should_rebuild:
        return

    render_resume_yaml_to_tex(
        yaml_path=base_yaml_path,
        tex_output_path=base_tex_path,
    )
    compile_resume_tex(
        tex_path=base_tex_path,
        pdf_output_path=base_pdf_path,
    )


async def _handle_review_failure(
    *,
    db: DatabaseManager,
    run_id: int,
    job_hash: str,
    tailor_run_id: int,
    error: str,
    max_retries: int,
    backoff_seconds: int,
    backoff_multiplier: int,
    fallback_base_yaml_path: Path,
    fallback_base_tex_path: Path,
    fallback_base_pdf_path: Path,
    agent_stdout: str | None,
    agent_stderr: str | None,
) -> None:
    """Record review failure with retry scheduling and fallback references.

    Purpose:
        Persist runtime diagnostics and base-resume fallback metadata while
        handling retry and terminal-alert behavior in one place.
    Args:
        db: Connected database manager.
        run_id: Review run row identifier.
        job_hash: Stable job hash for logging and alerts.
        tailor_run_id: Tailor run identifier used for retry counting.
        error: Failure reason text.
        max_retries: Maximum failed review runs before terminal failure.
        backoff_seconds: Base retry backoff in seconds.
        backoff_multiplier: Multiplicative backoff factor.
        fallback_base_yaml_path: Base YAML fallback path.
        fallback_base_tex_path: Base TeX fallback path.
        fallback_base_pdf_path: Base PDF fallback path.
        agent_stdout: Raw agent stdout diagnostics text.
        agent_stderr: Raw agent stderr diagnostics text.
    Output:
        Returns `None` after recording failure and optional alerting.
    """

    try:
        failed_count = await db.get_review_failure_count(tailor_run_id) + 1
    except Exception as count_exc:
        logger.error(
            "Could not fetch review failure count for tailor_run_id={} during error recovery: {}; "
            "recording terminal failure",
            tailor_run_id,
            count_exc,
        )
        failed_count = max_retries

    if failed_count >= max_retries:
        next_retry_at = None
        await _notify_terminal_failure(
            job_hash=job_hash,
            tailor_run_id=tailor_run_id,
            error=error,
            retry_count=failed_count,
        )
    else:
        next_retry_at = _calculate_next_retry_at(
            retry_count=failed_count,
            backoff_seconds=backoff_seconds,
            backoff_multiplier=backoff_multiplier,
        )

    await db.record_review_failure(
        run_id=run_id,
        error=error,
        next_retry_at=next_retry_at,
        agent_stdout=agent_stdout,
        agent_stderr=agent_stderr,
        fallback_base_yaml_path=str(fallback_base_yaml_path),
        fallback_base_tex_path=str(fallback_base_tex_path),
        fallback_base_pdf_path=str(fallback_base_pdf_path),
    )
    await record_stage_cost_event(
        db=db,
        stage=PIPELINE_STAGE_REVIEW,
        job_hash=job_hash,
        run_id=str(run_id),
        metadata={
            "status": "FAILED",
            "tailor_run_id": tailor_run_id,
            "retry_count": failed_count,
            "max_retries": max_retries,
        },
    )


async def _review_once(
    *,
    db: DatabaseManager,
    output_base_dir: Path,
    base_yaml_path: Path,
    base_tex_path: Path,
    base_pdf_path: Path,
    max_retries: int,
    lease_seconds: int,
    backoff_seconds: int,
    backoff_multiplier: int,
    pi_model: str | None = None,
) -> int:
    """Claim and process one tailored resume through review runtime.

    Purpose:
        Drive one end-to-end review pass: claim eligible run, invoke review
        runtime, and persist success/failure outcomes in `review_runs`.
    Args:
        db: Connected database manager for claim and persistence.
        output_base_dir: Base directory containing tailored run artifacts.
        base_yaml_path: Base resume YAML reference path.
        base_tex_path: Base resume TeX reference path.
        base_pdf_path: Base resume PDF reference path.
        max_retries: Maximum FAILED review runs before exclusion.
        lease_seconds: Seconds a PENDING review claim stays valid.
        backoff_seconds: Base delay in seconds for retry scheduling.
        backoff_multiplier: Multiplicative retry backoff factor.
        pi_model: Optional model identifier forwarded to pi subprocess.
    Output:
        Returns `1` when a review run completes successfully, else `0`.
    """

    claimed_row = await db.claim_next_review_job(
        max_retries=max_retries,
        lease_seconds=lease_seconds,
    )
    if claimed_row is None:
        logger.info("No tailored resumes pending review processing")
        return 0

    run_id = int(claimed_row["_review_run_id"])
    job_hash = str(claimed_row["job_hash"])
    tailor_run_id = int(claimed_row["tailor_run_id"])

    try:
        _validate_job_hash(job_hash)
    except ValueError as exc:
        await _handle_review_failure(
            db=db,
            run_id=run_id,
            job_hash=job_hash,
            tailor_run_id=tailor_run_id,
            error=f"invalid_job_hash: {exc}",
            max_retries=max_retries,
            backoff_seconds=backoff_seconds,
            backoff_multiplier=backoff_multiplier,
            fallback_base_yaml_path=base_yaml_path,
            fallback_base_tex_path=base_tex_path,
            fallback_base_pdf_path=base_pdf_path,
            agent_stdout=None,
            agent_stderr=None,
        )
        return 0

    run_dir = output_base_dir / job_hash
    run_dir.mkdir(parents=True, exist_ok=True)

    tailored_yaml_path = _resolve_tailored_yaml_path(claimed_row)
    tailored_tex_path = Path(str(claimed_row.get("artifact_tex_path") or "")).resolve()
    tailored_pdf_path = Path(str(claimed_row.get("artifact_pdf_path") or "")).resolve()
    tailored_log_path = tailored_tex_path.with_suffix(".log")

    required_paths = [tailored_yaml_path, tailored_tex_path, tailored_pdf_path]
    missing_paths = [path for path in required_paths if not path.exists()]
    if missing_paths:
        await _handle_review_failure(
            db=db,
            run_id=run_id,
            job_hash=job_hash,
            tailor_run_id=tailor_run_id,
            error=(
                "missing_tailor_artifacts: "
                + ", ".join(str(path) for path in missing_paths)
            ),
            max_retries=max_retries,
            backoff_seconds=backoff_seconds,
            backoff_multiplier=backoff_multiplier,
            fallback_base_yaml_path=base_yaml_path,
            fallback_base_tex_path=base_tex_path,
            fallback_base_pdf_path=base_pdf_path,
            agent_stdout=None,
            agent_stderr=None,
        )
        return 0

    report_path = run_dir / "review_report.json"

    invocation_payload: dict[str, object] = {
        "job_ref": {"job_hash": job_hash},
        "tailor_run_id": tailor_run_id,
        "database_path": str(db.db_path),
        "tailored_yaml_path": str(tailored_yaml_path),
        "tailored_tex_path": str(tailored_tex_path),
        "tailored_pdf_path": str(tailored_pdf_path),
        "tailored_log_path": str(tailored_log_path),
        "base_yaml_path": str(base_yaml_path),
        "base_tex_path": str(base_tex_path),
        "base_pdf_path": str(base_pdf_path),
        "review_report_path": str(report_path),
        "max_review_iterations": 2,
    }
    if pi_model:
        invocation_payload["pi_model"] = pi_model

    invocation = ReviewInvocationContract.model_validate(invocation_payload)

    result: ReviewRunResult
    try:
        event_loop = asyncio.get_event_loop()
        result = await event_loop.run_in_executor(
            None,
            lambda: run_resume_review_pipeline(invocation=invocation),
        )
    except Exception as exc:
        await _handle_review_failure(
            db=db,
            run_id=run_id,
            job_hash=job_hash,
            tailor_run_id=tailor_run_id,
            error=f"review_runtime_exception: {exc}",
            max_retries=max_retries,
            backoff_seconds=backoff_seconds,
            backoff_multiplier=backoff_multiplier,
            fallback_base_yaml_path=base_yaml_path,
            fallback_base_tex_path=base_tex_path,
            fallback_base_pdf_path=base_pdf_path,
            agent_stdout=None,
            agent_stderr=None,
        )
        return 0

    if (
        result.success
        and result.review_report is not None
        and result.verdict is not None
    ):
        await db.record_review_success(
            run_id=run_id,
            verdict=result.verdict.value,
            selected_yaml_path=result.selected_yaml_path,
            selected_tex_path=result.selected_tex_path,
            selected_pdf_path=result.selected_pdf_path,
            review_report_json=result.review_report.model_dump_json(indent=2),
            agent_stdout=result.agent_stdout,
            agent_stderr=result.agent_stderr,
        )
        await record_stage_cost_event(
            db=db,
            stage=PIPELINE_STAGE_REVIEW,
            job_hash=job_hash,
            run_id=str(run_id),
            metadata={
                "status": "SUCCESS",
                "tailor_run_id": tailor_run_id,
                "verdict": result.verdict.value,
            },
        )
        logger.info(
            "Review SUCCESS: job_hash={} tailor_run_id={} verdict={} selected_pdf={}",
            job_hash,
            tailor_run_id,
            result.verdict.value,
            result.selected_pdf_path,
        )
        return 1

    await _handle_review_failure(
        db=db,
        run_id=run_id,
        job_hash=job_hash,
        tailor_run_id=tailor_run_id,
        error=(result.failure_reason or "unknown review runtime failure")[:500],
        max_retries=max_retries,
        backoff_seconds=backoff_seconds,
        backoff_multiplier=backoff_multiplier,
        fallback_base_yaml_path=base_yaml_path,
        fallback_base_tex_path=base_tex_path,
        fallback_base_pdf_path=base_pdf_path,
        agent_stdout=result.agent_stdout,
        agent_stderr=result.agent_stderr,
    )
    logger.warning(
        "Review FAILED: job_hash={} tailor_run_id={} error={}",
        job_hash,
        tailor_run_id,
        result.failure_reason,
    )
    return 0


async def main() -> None:
    """Parse CLI args and run one-shot or looping review processing.

    Purpose:
        Provide script entrypoint that performs preflight, base-artifact setup,
        DB preparation, and one-shot/loop execution.
    Args:
        None.
    Output:
        Returns `None` after processing requested mode.
    """

    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Process tailored resumes through the review pipeline",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--loop", action="store_true", help="Poll forever")
    mode_group.add_argument(
        "--once",
        action="store_true",
        help="Process once and exit (default behavior)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=os.getenv("REVIEW_OUTPUT_DIR", DEFAULT_REVIEW_OUTPUT_DIR),
        help="Base directory containing tailored artifacts",
    )
    parser.add_argument(
        "--base-resume-yaml-path",
        type=str,
        default=os.getenv(
            "REVIEW_BASE_RESUME_YAML_PATH",
            DEFAULT_REVIEW_BASE_RESUME_YAML_PATH,
        ),
        help="Path to base canonical resume YAML",
    )
    parser.add_argument(
        "--base-resume-tex-path",
        type=str,
        default=os.getenv(
            "REVIEW_BASE_RESUME_TEX_PATH",
            f"{DEFAULT_REVIEW_BASE_ARTIFACT_DIR}/resume_base.tex",
        ),
        help="Base reference TeX path used for review comparisons",
    )
    parser.add_argument(
        "--base-resume-pdf-path",
        type=str,
        default=os.getenv(
            "REVIEW_BASE_RESUME_PDF_PATH",
            f"{DEFAULT_REVIEW_BASE_ARTIFACT_DIR}/resume_base.pdf",
        ),
        help="Base reference PDF path used for review comparisons",
    )
    parser.add_argument(
        "--database-path",
        type=str,
        default=None,
        help="SQLite database path (default: from DATABASE_PATH env)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help=(
            "Model to pass to pi (e.g. openai/gpt-5.1-codex-mini). "
            "Falls back to RESUME_REVIEW_MODEL env var."
        ),
    )
    args = parser.parse_args()

    should_loop = args.loop and not args.once
    poll_interval_seconds = _load_int_env(
        "REVIEW_POLL_INTERVAL_SECONDS",
        DEFAULT_REVIEW_POLL_INTERVAL_SECONDS,
    )
    max_retries = _load_int_env("REVIEW_MAX_RETRIES", DEFAULT_REVIEW_MAX_RETRIES)
    backoff_seconds = _load_int_env(
        "REVIEW_RETRY_BACKOFF_SECONDS",
        DEFAULT_REVIEW_RETRY_BACKOFF_SECONDS,
    )
    backoff_multiplier = _load_int_env(
        "REVIEW_RETRY_BACKOFF_MULTIPLIER",
        DEFAULT_REVIEW_RETRY_BACKOFF_MULTIPLIER,
    )
    lease_seconds = _load_int_env(
        "REVIEW_CLAIM_LEASE_SECONDS",
        DEFAULT_REVIEW_CLAIM_LEASE_SECONDS,
    )

    pi_model: str | None = (
        args.model or os.getenv("RESUME_REVIEW_MODEL") or "openai/gpt-5.1-codex-mini"
    )

    try:
        _check_preflight()
    except ReviewPreflightError as exc:
        logger.error("Review preflight failed: {}", exc)
        await _notify_preflight_failure(str(exc))
        return

    repo_root = resolve_repo_root()

    output_base_dir = Path(args.output_dir)
    if not output_base_dir.is_absolute():
        output_base_dir = repo_root / output_base_dir
    output_base_dir = output_base_dir.resolve()

    base_yaml_path = Path(args.base_resume_yaml_path)
    if not base_yaml_path.is_absolute():
        base_yaml_path = repo_root / base_yaml_path
    base_yaml_path = base_yaml_path.resolve()

    base_tex_path = Path(args.base_resume_tex_path)
    if not base_tex_path.is_absolute():
        base_tex_path = repo_root / base_tex_path
    base_tex_path = base_tex_path.resolve()

    base_pdf_path = Path(args.base_resume_pdf_path)
    if not base_pdf_path.is_absolute():
        base_pdf_path = repo_root / base_pdf_path
    base_pdf_path = base_pdf_path.resolve()

    if args.database_path:
        database_path = Path(args.database_path).resolve()
    else:
        database_path = resolve_database_path()

    try:
        _ensure_base_reference_artifacts(
            base_yaml_path=base_yaml_path,
            base_tex_path=base_tex_path,
            base_pdf_path=base_pdf_path,
        )
    except Exception as exc:
        logger.error("Could not prepare base review artifacts: {}", exc)
        await _notify_preflight_failure(f"base_reference_artifacts_failed: {exc}")
        return

    async with DatabaseManager(str(database_path)) as db:
        await db.create_tables()
        await db.migrate_tailor_schema()
        await db.migrate_review_schema()
        await db.migrate_cost_schema()

        stale_count = await db.mark_stale_review_runs_failed(
            lease_seconds=lease_seconds
        )
        if stale_count > 0:
            logger.warning(
                "Marked {} stale PENDING review runs as FAILED on startup",
                stale_count,
            )

        if not should_loop:
            await _review_once(
                db=db,
                output_base_dir=output_base_dir,
                base_yaml_path=base_yaml_path,
                base_tex_path=base_tex_path,
                base_pdf_path=base_pdf_path,
                max_retries=max_retries,
                lease_seconds=lease_seconds,
                backoff_seconds=backoff_seconds,
                backoff_multiplier=backoff_multiplier,
                pi_model=pi_model,
            )
            return

        logger.info(
            "Review worker entering loop: poll={}s lease={}s max_retries={}",
            poll_interval_seconds,
            lease_seconds,
            max_retries,
        )

        while True:
            processed = 0
            try:
                processed = await _review_once(
                    db=db,
                    output_base_dir=output_base_dir,
                    base_yaml_path=base_yaml_path,
                    base_tex_path=base_tex_path,
                    base_pdf_path=base_pdf_path,
                    max_retries=max_retries,
                    lease_seconds=lease_seconds,
                    backoff_seconds=backoff_seconds,
                    backoff_multiplier=backoff_multiplier,
                    pi_model=pi_model,
                )
                logger.info("Review cycle complete: processed={}", processed)
            except Exception as exc:
                logger.exception("Review polling cycle failed: {}", exc)

            if processed == 0:
                await asyncio.sleep(poll_interval_seconds)


if __name__ == "__main__":
    asyncio.run(main())
