"""Tailor-stage worker loop for the agentic job applier pipeline.

Runs inside ``LoopSupervisor`` as an asyncio task. Reads
``automation.tailor_mode`` from the database on every cycle; when the
mode is ``autonomous`` or ``both``, sweeps stale PENDING runs and claims
one QUALIFIED job to dispatch through
``src.agents.resume_tailor.run_tailor_review_pipeline``.
"""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

from loguru import logger

from src.utils.paths import resolve_database_path
from src.agents.resume_tailor import (
    TailorRunResult,
    run_tailor_review_pipeline,
)
from src.database._mixins.system_settings import TAILOR_MODE_KEY
from src.database.db_manager import DEFAULT_TAILOR_CLAIM_LEASE_SECONDS, DatabaseManager
from src.utils.cost_tracking import PIPELINE_STAGE_TAILOR, check_budget_before_claim
from src.utils.notifications import send_ntfy_notification

# Default poll interval when the worker finds no claimable job.
DEFAULT_TAILOR_POLL_INTERVAL_SECONDS = 30

# Retry budget before a job is permanently excluded from claiming.
DEFAULT_TAILOR_MAX_RETRIES = 2

# Repo-relative output directory for per-job tailor artifacts.
DEFAULT_TAILOR_OUTPUT_DIR = "data/tailored_resumes"

# Repo-relative path to the base resume template.
DEFAULT_TAILOR_RESUME_TEX_PATH = "config/resume.tex"

# Repo-relative path to the candidate profile YAML used for personalization.
DEFAULT_CANDIDATE_PROFILE_YAML_PATH = "config/candidate_profile.yaml"

# The mode string indicating user-triggered-only (no autonomous claiming).
OPT_IN_MODE = "opt_in"

# Modes that permit autonomous claiming on each cycle.
AUTONOMOUS_MODES: frozenset[str] = frozenset({"autonomous", "both"})

# Canonical hex pattern for job hashes; enforced before using hash as a path component.
_JOB_HASH_RE = re.compile(r"^[a-f0-9]{32,64}$")


class TailorPreflightError(RuntimeError):
    """Represent a fatal preflight check failure for the tailor worker."""


def _validate_job_hash(job_hash: str) -> None:
    """Reject job_hash values that could enable path traversal.

    Purpose:
        Per-job output directories are derived from ``job_hash``; only the
        canonical hex hash shape is allowed onto the filesystem.
    Args:
        job_hash: Hash value pulled from the claim result.
    Output:
        Returns ``None`` when the value matches the canonical hex shape.
    Raises:
        ValueError: When the value contains anything outside hex or is the
            wrong length.
    """
    if not _JOB_HASH_RE.match(job_hash):
        raise ValueError(
            f"Invalid job_hash format — expected 32-64 hex chars, got {job_hash!r}"
        )


def _load_int_env(name: str, default_value: int) -> int:
    """Read a positive integer from environment with a safe fallback.

    Purpose:
        Worker tuning knobs are env-driven; invalid values must not crash
        startup and must not silently disable the worker by resolving to
        zero or a negative number.
    Args:
        name: Environment variable name.
        default_value: Fallback when the env var is absent, non-integer,
            or non-positive.
    Output:
        Returns the parsed positive integer or ``default_value``.
    """
    raw_value = os.getenv(name)
    if raw_value is None:
        return default_value
    try:
        parsed_value = int(raw_value)
    except ValueError:
        logger.warning(
            "Invalid integer for {}={!r}; using default {}",
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


def _check_preflight() -> None:
    """Validate that the database parent directory is writable.

    Purpose:
        Fail fast on a missing database directory before the worker tries
        its first claim. Called at CLI startup; not called inside the loop
        itself because the DB connection is already open by then.
    Args:
        None.
    Output:
        Returns ``None`` when the check passes.
    Raises:
        TailorPreflightError: When the database parent directory cannot
            be resolved or does not exist.
    """
    try:
        db_path = resolve_database_path()
        if not db_path.parent.exists():
            raise TailorPreflightError(
                f"Database parent directory does not exist: {db_path.parent}"
            )
    except RuntimeError as exc:
        raise TailorPreflightError(f"Database path resolution failed: {exc}") from exc


async def _notify_preflight_failure(error: str) -> None:
    """Send a one-time ntfy alert for tailor preflight failure.

    Purpose:
        Surface fatal startup misconfiguration so operators know to act
        rather than silently waiting for a healthy cycle that will never
        arrive.
    Args:
        error: Preflight error text describing the missing piece.
    Output:
        Returns ``None`` after a best-effort notification attempt.
    """
    await send_ntfy_notification(
        title="Resume tailor worker preflight failure",
        message=(
            f"Tailor worker could not start due to preflight failure.\nerror={error}"
        ),
        tags=("warning", "gear"),
        priority="high",
    )


async def _notify_terminal_failure(*, job_hash: str, error: str) -> None:
    """Send an ntfy alert when a job exhausts the retry budget.

    Purpose:
        Pipeline errors land here only after ``claim_next_tailor_job``
        refuses to retry further; surfacing them lets the user intervene
        before the job is permanently excluded.
    Args:
        job_hash: Stable deduplication hash of the failed job.
        error: Final error message stored on the tailor_runs row.
    Output:
        Returns ``None`` after a best-effort notification attempt.
    """
    await send_ntfy_notification(
        title="Resume tailor terminal failure",
        message=(
            "Resume tailor exhausted retries and needs intervention.\n"
            f"job_hash={job_hash}\n"
            f"error={error}"
        ),
        tags=("warning", "page_facing_up"),
        priority="high",
    )


async def _tailor_once(
    *,
    db: DatabaseManager,
    output_base_dir: Path,
    resume_tex_path: Path,
    candidate_profile_yaml_path: Path,
    max_retries: int,
    lease_seconds: int,
) -> int:
    """Claim and run the resume-tailor pipeline for one QUALIFIED job.

    Purpose:
        Wire one cycle of the worker: budget guard → claim → pipeline.
        The pipeline owns its own DB writes (RUNNING / SUCCESS / FAILED),
        so this wrapper only needs to invoke it and log the outcome.
    Args:
        db: Connected database manager.
        output_base_dir: Per-run artifact root directory.
        resume_tex_path: Absolute path to ``config/resume.tex``.
        candidate_profile_yaml_path: Absolute path to
            ``config/candidate_profile.yaml``.
        max_retries: Maximum FAILED runs before a job is excluded by
            claim.
        lease_seconds: PENDING claim lease length in seconds.
    Output:
        Returns ``1`` when a job was attempted (regardless of pipeline
        success), ``0`` otherwise (no budget, no claimable job, or
        invalid claim data).
    """
    if not await check_budget_before_claim(db=db, stage=PIPELINE_STAGE_TAILOR):
        return 0

    job = await db.claim_next_tailor_job(
        max_retries=max_retries, lease_seconds=lease_seconds
    )
    if job is None:
        return 0

    run_id_raw = job["_tailor_run_id"]
    if not isinstance(run_id_raw, int):
        logger.error("Invalid _tailor_run_id type: {}", type(run_id_raw))
        return 0
    tailor_run_id: int = run_id_raw

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
            run_id=tailor_run_id,
            error=f"invalid_job_hash: {exc}",
            next_retry_at=None,
        )
        return 0

    run_output_dir = output_base_dir / job_hash
    result: TailorRunResult = await run_tailor_review_pipeline(
        db=db,
        tailor_run_id=tailor_run_id,
        job_hash=job_hash,
        base_resume_tex_path=resume_tex_path,
        candidate_profile_yaml_path=candidate_profile_yaml_path,
        output_dir=run_output_dir,
    )

    if result.success:
        logger.info(
            "Tailor SUCCESS: job_hash={} verdict={} pdf={}",
            job_hash,
            result.verdict,
            result.selected_pdf_path,
        )
        return 1

    # Notify when the job has consumed its full retry budget so the user
    # can inspect the failure and intervene rather than discovering a
    # silently-excluded job later.
    failure_count = await db.get_tailor_failure_count(job_hash)
    if failure_count >= max_retries:
        await _notify_terminal_failure(
            job_hash=job_hash, error=result.error or "unknown_failure"
        )
    logger.warning(
        "Tailor FAILED: job_hash={} error={} retry_count={}/{}",
        job_hash,
        result.error,
        failure_count,
        max_retries,
    )
    return 1


async def _run_one_cycle(
    *,
    db: DatabaseManager,
    output_base_dir: Path,
    resume_tex_path: Path,
    candidate_profile_yaml_path: Path,
    max_retries: int,
    lease_seconds: int,
) -> int:
    """Run one poll cycle: sweep stale rows, then maybe claim one job.

    Purpose:
        Centralize per-cycle behavior so the staleness sweep runs in
        every cycle regardless of mode, and the mode-gated claim only
        fires when automation is enabled. Reading the mode on every cycle
        (rather than once at startup) means toggling the UI takes effect
        within one cycle without a worker restart.
    Args:
        db: Connected database manager.
        output_base_dir: Per-run artifact root directory.
        resume_tex_path: Absolute path to ``config/resume.tex``.
        candidate_profile_yaml_path: Absolute path to
            ``config/candidate_profile.yaml``.
        max_retries: Worker max-retry knob forwarded to claim.
        lease_seconds: Claim lease length; also used as the staleness
            threshold for sweeping crashed user-triggered runs.
    Output:
        Returns ``1`` when a job was claimed and processed, ``0``
        otherwise.
    """
    # Always sweep stale PENDING rows so crashed user-triggered runs are
    # reaped even when the mode is opt_in.
    stale_count = await db.mark_stale_tailor_runs_failed(lease_seconds=lease_seconds)
    if stale_count > 0:
        logger.warning("Marked {} stale tailor runs as FAILED", stale_count)

    # Re-read the mode on every cycle so mode flips are respected without
    # restarting the worker process or the asyncio task.
    mode = await db.get_automation_mode(TAILOR_MODE_KEY)
    if mode == OPT_IN_MODE:
        logger.debug("Tailor mode is opt_in; skipping claim this cycle")
        return 0
    if mode not in AUTONOMOUS_MODES:
        logger.warning("Unknown tailor mode {!r}; treating as opt_in", mode)
        return 0

    return await _tailor_once(
        db=db,
        output_base_dir=output_base_dir,
        resume_tex_path=resume_tex_path,
        candidate_profile_yaml_path=candidate_profile_yaml_path,
        max_retries=max_retries,
        lease_seconds=lease_seconds,
    )


async def tailor_once(
    *,
    db: DatabaseManager,
    output_base_dir: Path,
    resume_tex_path: Path,
    candidate_profile_yaml_path: Path,
    max_retries: int = DEFAULT_TAILOR_MAX_RETRIES,
    lease_seconds: int = DEFAULT_TAILOR_CLAIM_LEASE_SECONDS,
) -> int:
    """Run one tailor processing pass without entering the poll loop.

    Purpose:
        Stable one-shot entry point retained for tests and external
        scripts that drive a single processing cycle. Delegates to
        ``_run_one_cycle`` so the stale-run sweep and mode check still
        execute.
    Args:
        db: Connected database manager.
        output_base_dir: Per-run artifact root directory.
        resume_tex_path: Absolute path to ``config/resume.tex``.
        candidate_profile_yaml_path: Absolute path to
            ``config/candidate_profile.yaml``.
        max_retries: Worker max-retry knob forwarded to claim.
        lease_seconds: Claim lease length in seconds.
    Output:
        Returns ``1`` when a job was claimed and attempted, ``0``
        otherwise.
    """
    return await _run_one_cycle(
        db=db,
        output_base_dir=output_base_dir,
        resume_tex_path=resume_tex_path,
        candidate_profile_yaml_path=candidate_profile_yaml_path,
        max_retries=max_retries,
        lease_seconds=lease_seconds,
    )


async def run_tailor_loop(
    *,
    db: DatabaseManager,
    output_base_dir: Path,
    resume_tex_path: Path,
    candidate_profile_yaml_path: Path,
    max_retries: int = DEFAULT_TAILOR_MAX_RETRIES,
    lease_seconds: int = DEFAULT_TAILOR_CLAIM_LEASE_SECONDS,
    poll_interval_seconds: int = DEFAULT_TAILOR_POLL_INTERVAL_SECONDS,
) -> None:
    """Run the tailor worker poll loop using a shared database manager.

    Purpose:
        Provide an importable entry point so ``LoopSupervisor`` can run
        the tailor loop as an in-process asyncio task without spawning a
        new container or process. Loops forever until cancelled; the
        ``asyncio.CancelledError`` propagates out and the supervisor
        handles cleanup.
    Args:
        db: Connected database manager shared with other in-process loops.
        output_base_dir: Per-run artifact root directory.
        resume_tex_path: Absolute path to ``config/resume.tex``.
        candidate_profile_yaml_path: Absolute path to
            ``config/candidate_profile.yaml``.
        max_retries: Maximum FAILED runs before a job is excluded by
            claim.
        lease_seconds: PENDING claim lease length in seconds.
        poll_interval_seconds: Sleep duration between cycles when no
            job was claimed.
    Output:
        Returns ``None`` only on ``asyncio.CancelledError`` (re-raised).
    """
    logger.info(
        "Tailor loop entering poll: poll={}s lease={}s max_retries={}",
        poll_interval_seconds,
        lease_seconds,
        max_retries,
    )

    while True:
        processed = 0
        try:
            processed = await _run_one_cycle(
                db=db,
                output_base_dir=output_base_dir,
                resume_tex_path=resume_tex_path,
                candidate_profile_yaml_path=candidate_profile_yaml_path,
                max_retries=max_retries,
                lease_seconds=lease_seconds,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Tailor polling cycle failed: {}", exc)

        # Only sleep when the cycle found nothing to process; if a job was
        # claimed, loop immediately to pick up the next one before sleeping.
        if processed == 0:
            await asyncio.sleep(poll_interval_seconds)
