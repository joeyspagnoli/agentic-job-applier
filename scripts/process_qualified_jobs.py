#!/usr/bin/env python3
"""Process QUALIFIED jobs by running the pi-mono resume tailor pipeline.

Purpose:
    Provide the autonomous tailor worker that claims QUALIFIED jobs from
    the database, invokes the resume-tailor pipeline for each one, and
    records success/failure with retry backoff.  Mirrors the gate worker
    pattern in `process_new_jobs.py`.

Run once (default):
  uv run python -m scripts.process_qualified_jobs

Run continuously:
  TAILOR_POLL_INTERVAL_SECONDS=30 uv run python -m scripts.process_qualified_jobs --loop
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

from src.agents.resume_tailor_pi import (
    TailorInvocationContract,
    TailorRunResult,
    run_resume_tailor_pipeline,
)
from src.database.db_manager import DEFAULT_TAILOR_CLAIM_LEASE_SECONDS, DatabaseManager
from src.utils.cost_tracking import PIPELINE_STAGE_TAILOR
from src.utils.cost_tracking import check_budget_before_claim
from src.utils.cost_tracking import record_stage_cost_event
from src.utils.notifications import send_ntfy_notification
from src.utils.paths import resolve_database_path, resolve_repo_root

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_TAILOR_POLL_INTERVAL_SECONDS = 30
DEFAULT_TAILOR_MAX_RETRIES = 2
DEFAULT_TAILOR_RETRY_BACKOFF_SECONDS = 600
DEFAULT_TAILOR_RETRY_BACKOFF_MULTIPLIER = 2
DEFAULT_TAILOR_OUTPUT_DIR = "data/tailored_resumes"
DEFAULT_TAILOR_RESUME_YAML_PATH = "config/resume_content.yaml"


class TailorPreflightError(RuntimeError):
    """Represent a fatal preflight check failure for the tailor worker."""


_JOB_HASH_RE = re.compile(r"^[a-f0-9]{32,64}$")


def _validate_job_hash(job_hash: str) -> None:
    """Validate that job_hash is a safe hexadecimal hash string.

    Purpose:
        Prevent path traversal attacks by rejecting job_hash values that
        contain path separators, null bytes, or non-hex characters before
        any filesystem operations are performed.

    Arg(s):
        job_hash: Hash value from the database claim result to validate.

    Output:
        Returns `None` when the hash passes validation.

    Raises:
        ValueError: When job_hash does not match the expected hex format.
    """
    if not _JOB_HASH_RE.match(job_hash):
        raise ValueError(
            f"Invalid job_hash format — expected 32-64 hex chars, got {job_hash!r}"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_int_env(name: str, default_value: int) -> int:
    """Read a positive integer from environment and fall back safely.

    Purpose:
        Keep CLI/env configuration parsing consistent for worker tuning
        knobs while preventing invalid values from crashing startup.
    Args:
        name: Environment variable name to read.
        default_value: Fallback integer when parsing fails or value is invalid.
    Output:
        Returns a positive integer parsed from environment or the fallback.
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
        Centralize the retry-backoff formula used by the tailor worker so
        behavior is deterministic and easy to test.
    Args:
        retry_count: The retry count value being scheduled (1-based).
        backoff_seconds: Base delay in seconds for the first retry.
        backoff_multiplier: Multiplier applied to each additional retry.
    Output:
        Returns the computed delay in seconds for the next retry timestamp.
    """

    exponent = max(retry_count - 1, 0)
    return int(backoff_seconds * (backoff_multiplier**exponent))


def _calculate_next_retry_at(
    *,
    retry_count: int,
    backoff_seconds: int,
    backoff_multiplier: int,
) -> str:
    """Calculate the UTC timestamp string for the next retry attempt.

    Purpose:
        Produce SQLite-compatible retry scheduling timestamps for transient
        tailor failures.
    Args:
        retry_count: The retry count value being scheduled (1-based).
        backoff_seconds: Base delay in seconds for the first retry.
        backoff_multiplier: Multiplier applied to each additional retry.
    Output:
        Returns a UTC timestamp string in `%Y-%m-%d %H:%M:%S` format.
    """

    delay_seconds = _calculate_retry_delay_seconds(
        retry_count=retry_count,
        backoff_seconds=backoff_seconds,
        backoff_multiplier=backoff_multiplier,
    )
    scheduled_time = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
    return scheduled_time.strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------


def _check_preflight() -> None:
    """Validate that required external tools are available.

    Purpose:
        Fail fast with an actionable error before the worker enters its
        polling loop rather than failing on the first tailor run.
    Args:
        None.
    Output:
        Returns `None` when all checks pass.
    Raises:
        TailorPreflightError: When a required tool or path is missing.
    """

    # Check pi command availability.
    has_pi_env = bool(
        os.getenv("PI_CODING_AGENT_COMMAND", "").strip()
        or os.getenv("PI_CODING_AGENT_COMMAND_ARGV", "").strip()
    )
    has_pi_binary = shutil.which("pi") is not None
    if not has_pi_env and not has_pi_binary:
        raise TailorPreflightError(
            "pi command not found. Set PI_CODING_AGENT_COMMAND or "
            "PI_CODING_AGENT_COMMAND_ARGV in .env, or ensure 'pi' is in PATH."
        )

    # Check latexmk availability.
    if shutil.which("latexmk") is None:
        raise TailorPreflightError(
            "latexmk not found in PATH. Install texlive: "
            "sudo apt-get install texlive-full latexmk"
        )

    # Check database path resolves.
    try:
        db_path = resolve_database_path()
        if not db_path.parent.exists():
            raise TailorPreflightError(
                f"Database parent directory does not exist: {db_path.parent}"
            )
    except RuntimeError as exc:
        raise TailorPreflightError(f"Database path resolution failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


async def _notify_terminal_failure(
    *,
    job_hash: str,
    error: str,
    retry_count: int,
) -> None:
    """Send an ntfy alert for a tailor job that exhausted all retries.

    Purpose:
        Notify operators when manual intervention is needed after terminal
        tailor processing failure.
    Args:
        job_hash: Stable deduplication hash for the failed job.
        error: Terminal error message stored in the database.
        retry_count: Number of attempts made before terminal failure.
    Output:
        Returns `None` after best-effort notification attempt.
    """

    await send_ntfy_notification(
        title="Resume tailor terminal failure",
        message=(
            "Resume tailor exhausted retries and needs intervention.\n"
            f"job_hash={job_hash}\n"
            f"retry_count={retry_count}\n"
            f"error={error}"
        ),
        tags=("warning", "page_facing_up"),
        priority="high",
    )


async def _notify_preflight_failure(error: str) -> None:
    """Send a one-time ntfy alert for tailor preflight failure.

    Purpose:
        Surface fatal startup misconfiguration to operators so they can
        fix the environment before the worker retries.
    Args:
        error: Preflight error text describing what is missing.
    Output:
        Returns `None` after best-effort notification attempt.
    """

    await send_ntfy_notification(
        title="Resume tailor worker preflight failure",
        message=(
            f"Tailor worker could not start due to preflight failure.\nerror={error}"
        ),
        tags=("warning", "gear"),
        priority="high",
    )


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------


async def _handle_tailor_failure(
    *,
    db: DatabaseManager,
    run_id: int,
    job_hash: str,
    error: str,
    max_retries: int,
    backoff_seconds: int,
    backoff_multiplier: int,
) -> None:
    """Record a tailor failure with retry scheduling and optional alert.

    Purpose:
        Centralize the failure-recording logic shared between the pipeline
        exception path and the page-overflow failure path, including retry
        count inspection, backoff calculation, and terminal-failure alerting.
        Wraps the secondary DB query in its own error handler so an unreachable
        database during recovery does not mask the original error.

    Arg(s):
        db: Connected database manager for failure recording.
        run_id: Primary key of the tailor_runs row to update.
        job_hash: Stable deduplication hash of the failed job.
        error: Error message to store (should be pre-truncated to 500 chars).
        max_retries: Maximum FAILED runs before terminal failure.
        backoff_seconds: Base backoff delay for retry scheduling.
        backoff_multiplier: Multiplicative backoff factor per retry.

    Output:
        Returns `None` after recording the failure and optionally sending
        a terminal-failure notification.
    """
    try:
        failed_count = await db.get_tailor_failure_count(job_hash) + 1
    except Exception as count_exc:
        logger.error(
            "Could not fetch failure count for {} during error recovery: {}; "
            "recording terminal failure",
            job_hash,
            count_exc,
        )
        failed_count = max_retries  # Assume terminal on secondary DB failure.

    if failed_count >= max_retries:
        next_retry = None
        await _notify_terminal_failure(
            job_hash=job_hash,
            error=error,
            retry_count=failed_count,
        )
    else:
        next_retry = _calculate_next_retry_at(
            retry_count=failed_count,
            backoff_seconds=backoff_seconds,
            backoff_multiplier=backoff_multiplier,
        )

    try:
        await db.record_tailor_failure(
            run_id=run_id,
            error=error,
            next_retry_at=next_retry,
        )
        await record_stage_cost_event(
            db=db,
            stage=PIPELINE_STAGE_TAILOR,
            job_hash=job_hash,
            run_id=str(run_id),
            metadata={
                "status": "FAILED",
                "retry_count": failed_count,
                "max_retries": max_retries,
            },
        )
    except Exception as record_exc:
        logger.error(
            "Failed to record tailor failure for run_id={}: {}",
            run_id,
            record_exc,
        )


async def _tailor_once(
    *,
    db: DatabaseManager,
    output_base_dir: Path,
    resume_yaml_path: Path,
    max_retries: int,
    lease_seconds: int,
    backoff_seconds: int,
    backoff_multiplier: int,
    pi_model: str | None = None,
) -> int:
    """Claim and tailor one QUALIFIED job through the pi-mono pipeline.

    Purpose:
        Drive the end-to-end single-job tailoring workflow: claim from
        the database, copy the YAML to a per-run working file, invoke the
        pipeline in a thread executor, and record the outcome.
    Args:
        db: Connected database manager for claim and recording.
        output_base_dir: Base directory for generated resume artifacts.
        resume_yaml_path: Absolute path to the canonical resume YAML.
        max_retries: Maximum FAILED runs before a job is excluded.
        lease_seconds: Seconds a PENDING claim stays valid.
        backoff_seconds: Base delay in seconds for retry scheduling.
        backoff_multiplier: Multiplicative factor per retry attempt.
        pi_model: Optional model identifier forwarded to the pi subprocess.
    Output:
        Returns `1` when a job was successfully tailored, `0` otherwise.
    """

    if not await check_budget_before_claim(db=db, stage=PIPELINE_STAGE_TAILOR):
        return 0

    job = await db.claim_next_tailor_job(
        max_retries=max_retries,
        lease_seconds=lease_seconds,
    )
    if job is None:
        logger.info("No QUALIFIED jobs pending tailor processing")
        return 0

    run_id_raw = job["_tailor_run_id"]
    if not isinstance(run_id_raw, int):
        logger.error("Invalid _tailor_run_id type: {}", type(run_id_raw))
        return 0
    run_id: int = run_id_raw

    job_hash_raw = job["job_hash"]
    if not isinstance(job_hash_raw, str):
        logger.error("Invalid job_hash type: {}", type(job_hash_raw))
        return 0
    job_hash: str = job_hash_raw

    try:
        _validate_job_hash(job_hash)
    except ValueError as exc:
        logger.error("Invalid job_hash rejected: {}", exc)
        await db.record_tailor_failure(
            run_id=run_id,
            error=f"invalid_job_hash: {exc}",
            next_retry_at=None,
        )
        return 0

    # Build per-job output directory and artifact paths.
    run_dir = output_base_dir / job_hash
    run_dir.mkdir(parents=True, exist_ok=True)
    tex_path = run_dir / "resume_tailored.tex"
    pdf_path = run_dir / "resume_tailored.pdf"

    # Copy YAML to a per-run working file so the canonical source is never
    # modified by the pipeline and concurrent runs cannot interfere.
    work_yaml_path = run_dir / "resume_content_work.yaml"
    try:
        shutil.copy2(resume_yaml_path, work_yaml_path)
    except OSError as exc:
        logger.error("Failed to copy YAML baseline for {}: {}", job_hash, exc)
        await db.record_tailor_failure(
            run_id=run_id,
            error=f"yaml_copy_failed: {exc}",
            next_retry_at=None,
        )
        return 0

    invocation_payload: dict[str, object] = {
        "job_ref": {"job_hash": job_hash},
        "database_path": str(db.db_path),
        "resume_yaml_path": str(work_yaml_path),
        "output_tex_path": str(tex_path),
        "output_pdf_path": str(pdf_path),
        "page_limit": 1,
        "content_readjust_attempts": 2,
    }
    if pi_model:
        invocation_payload["pi_model"] = pi_model
    invocation = TailorInvocationContract.model_validate(invocation_payload)

    result: TailorRunResult | None = None
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: run_resume_tailor_pipeline(invocation=invocation),
        )
    except Exception as exc:
        logger.error("Tailor pipeline raised for {}: {}", job_hash, exc)
        await _handle_tailor_failure(
            db=db,
            run_id=run_id,
            job_hash=job_hash,
            error=str(exc)[:500],
            max_retries=max_retries,
            backoff_seconds=backoff_seconds,
            backoff_multiplier=backoff_multiplier,
        )
        return 0

    if result is None:
        logger.error("Tailor pipeline returned None for {}", job_hash)
        await _handle_tailor_failure(
            db=db,
            run_id=run_id,
            job_hash=job_hash,
            error="pipeline_returned_none",
            max_retries=max_retries,
            backoff_seconds=backoff_seconds,
            backoff_multiplier=backoff_multiplier,
        )
        return 0

    if result.success:
        await db.record_tailor_success(
            run_id=run_id,
            artifact_yaml_path=str(work_yaml_path),
            artifact_tex_path=str(tex_path),
            artifact_pdf_path=str(pdf_path),
            page_count=result.final_page_count,
        )
        await record_stage_cost_event(
            db=db,
            stage=PIPELINE_STAGE_TAILOR,
            job_hash=job_hash,
            run_id=str(run_id),
            metadata={
                "status": "SUCCESS",
                "page_count": result.final_page_count,
            },
        )
        logger.info(
            "Tailor SUCCESS: job_hash={} pages={} pdf={}",
            job_hash,
            result.final_page_count,
            pdf_path,
        )
        return 1

    # Pipeline returned failure (e.g., page limit exceeded after all attempts).
    failure_reason = result.failure_reason or "unknown pipeline failure"
    await _handle_tailor_failure(
        db=db,
        run_id=run_id,
        job_hash=job_hash,
        error=failure_reason[:500],
        max_retries=max_retries,
        backoff_seconds=backoff_seconds,
        backoff_multiplier=backoff_multiplier,
    )

    logger.warning(
        "Tailor FAILED: job_hash={} error={}",
        job_hash,
        failure_reason,
    )
    return 0


async def tailor_once(
    *,
    db: DatabaseManager,
    output_base_dir: Path,
    resume_yaml_path: Path,
    max_retries: int = DEFAULT_TAILOR_MAX_RETRIES,
    lease_seconds: int = DEFAULT_TAILOR_CLAIM_LEASE_SECONDS,
    backoff_seconds: int = DEFAULT_TAILOR_RETRY_BACKOFF_SECONDS,
    backoff_multiplier: int = DEFAULT_TAILOR_RETRY_BACKOFF_MULTIPLIER,
    pi_model: str | None = None,
) -> int:
    """Run one public tailor processing pass for external callers.

    Purpose:
        Expose a stable one-shot processing API for scripts and tests
        that should not depend on private helper naming.
    Args:
        db: Connected database manager for claim and recording.
        output_base_dir: Base directory for generated resume artifacts.
        resume_yaml_path: Absolute path to the canonical resume YAML.
        max_retries: Maximum FAILED runs before a job is excluded.
        lease_seconds: Seconds a PENDING claim stays valid.
        backoff_seconds: Base backoff delay for retry scheduling.
        backoff_multiplier: Multiplicative backoff factor per retry.
        pi_model: Optional model identifier forwarded to the pi subprocess.
    Output:
        Returns `1` when a job was successfully tailored, `0` otherwise.
    """

    return await _tailor_once(
        db=db,
        output_base_dir=output_base_dir,
        resume_yaml_path=resume_yaml_path,
        max_retries=max_retries,
        lease_seconds=lease_seconds,
        backoff_seconds=backoff_seconds,
        backoff_multiplier=backoff_multiplier,
        pi_model=pi_model,
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


async def main() -> None:
    """Parse CLI args and run one-shot or looping tailor processing.

    Purpose:
        Provide the script entrypoint that loads environment variables,
        runs preflight checks, prepares the database, and decides whether
        to run once or poll continuously.
    Args:
        None.
    Output:
        Returns `None` after completing the requested processing mode.
    """

    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Process QUALIFIED jobs through the resume tailor pipeline",
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
        default=os.getenv("TAILOR_OUTPUT_DIR", DEFAULT_TAILOR_OUTPUT_DIR),
        help="Base directory for tailored resume artifacts",
    )
    parser.add_argument(
        "--resume-yaml-path",
        type=str,
        default=os.getenv("TAILOR_RESUME_YAML_PATH", DEFAULT_TAILOR_RESUME_YAML_PATH),
        help="Path to the canonical resume YAML file",
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
            "Model to pass to pi (e.g. openai/openai/gpt-5.1-mini-codex). "
            "Falls back to RESUME_TAILOR_MODEL env var."
        ),
    )
    args = parser.parse_args()

    should_loop = args.loop and not args.once
    poll_interval_seconds = _load_int_env(
        "TAILOR_POLL_INTERVAL_SECONDS",
        DEFAULT_TAILOR_POLL_INTERVAL_SECONDS,
    )
    max_retries = _load_int_env("TAILOR_MAX_RETRIES", DEFAULT_TAILOR_MAX_RETRIES)
    backoff_seconds = _load_int_env(
        "TAILOR_RETRY_BACKOFF_SECONDS",
        DEFAULT_TAILOR_RETRY_BACKOFF_SECONDS,
    )
    backoff_multiplier = _load_int_env(
        "TAILOR_RETRY_BACKOFF_MULTIPLIER",
        DEFAULT_TAILOR_RETRY_BACKOFF_MULTIPLIER,
    )
    lease_seconds = _load_int_env(
        "TAILOR_CLAIM_LEASE_SECONDS",
        DEFAULT_TAILOR_CLAIM_LEASE_SECONDS,
    )

    pi_model: str | None = (
        args.model
        or os.environ.get("RESUME_TAILOR_MODEL")
        or "openai/gpt-5.1-codex-mini"
    )

    # Preflight checks before entering the processing loop.
    try:
        _check_preflight()
    except TailorPreflightError as exc:
        logger.error("Tailor preflight failed: {}", exc)
        await _notify_preflight_failure(str(exc))
        return

    repo_root = resolve_repo_root()

    # Resolve output and YAML paths relative to repo root.
    output_base_dir = Path(args.output_dir)
    if not output_base_dir.is_absolute():
        output_base_dir = repo_root / output_base_dir

    resume_yaml_path = Path(args.resume_yaml_path)
    if not resume_yaml_path.is_absolute():
        resume_yaml_path = repo_root / resume_yaml_path

    if not resume_yaml_path.exists():
        logger.error("Resume YAML not found: {}", resume_yaml_path)
        await _notify_preflight_failure(f"Resume YAML not found: {resume_yaml_path}")
        return

    # Resolve database path.
    if args.database_path:
        db_path = str(Path(args.database_path).resolve())
    else:
        db_path = str(resolve_database_path())

    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        await db.migrate_tailor_schema()
        await db.migrate_cost_schema()

        # Cleanup stale claims from a previous crash.
        stale_count = await db.mark_stale_tailor_runs_failed(
            lease_seconds=lease_seconds,
        )
        if stale_count > 0:
            logger.warning(
                "Marked {} stale PENDING tailor runs as FAILED on startup",
                stale_count,
            )

        if not should_loop:
            await _tailor_once(
                db=db,
                output_base_dir=output_base_dir,
                resume_yaml_path=resume_yaml_path,
                max_retries=max_retries,
                lease_seconds=lease_seconds,
                backoff_seconds=backoff_seconds,
                backoff_multiplier=backoff_multiplier,
                pi_model=pi_model,
            )
            return

        logger.info(
            "Tailor worker entering loop: poll={}s lease={}s max_retries={}",
            poll_interval_seconds,
            lease_seconds,
            max_retries,
        )

        while True:
            processed = 0
            try:
                processed = await _tailor_once(
                    db=db,
                    output_base_dir=output_base_dir,
                    resume_yaml_path=resume_yaml_path,
                    max_retries=max_retries,
                    lease_seconds=lease_seconds,
                    backoff_seconds=backoff_seconds,
                    backoff_multiplier=backoff_multiplier,
                    pi_model=pi_model,
                )
                logger.info("Tailor cycle complete: processed={}", processed)
            except Exception as exc:
                logger.exception("Tailor polling cycle failed: {}", exc)

            if processed == 0:
                await asyncio.sleep(poll_interval_seconds)


if __name__ == "__main__":
    asyncio.run(main())
