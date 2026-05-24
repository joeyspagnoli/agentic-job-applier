#!/usr/bin/env python3
"""Resume-tailor worker daemon driven by the resume-tailor pipeline.

Reads `automation.tailor_mode` from `system_settings` on every poll cycle.
When the mode is `autonomous` or `both`, claim one QUALIFIED job and run
the new resume-tailor pipeline (`src.agents.resume_tailor.run_tailor_review_pipeline`).
When the mode is `opt_in`, skip claiming entirely — the user triggers
runs from the dashboard — but still sweep stale PENDING rows every cycle
so crashed user-triggered runs are reaped.

Run once:
  python -m scripts.process_qualified_jobs

Run continuously:
  TAILOR_POLL_INTERVAL_SECONDS=30 python -m scripts.process_qualified_jobs --loop
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

from src.agents.resume_tailor import (
    TailorRunResult,
    run_tailor_review_pipeline,
)
from src.database._mixins.system_settings import TAILOR_MODE_KEY
from src.database.db_manager import DEFAULT_TAILOR_CLAIM_LEASE_SECONDS, DatabaseManager
from src.utils.cost_tracking import PIPELINE_STAGE_TAILOR, check_budget_before_claim
from src.utils.notifications import send_ntfy_notification
from src.utils.paths import resolve_database_path, resolve_repo_root

DEFAULT_TAILOR_POLL_INTERVAL_SECONDS = 30
DEFAULT_TAILOR_MAX_RETRIES = 2
DEFAULT_TAILOR_OUTPUT_DIR = "data/tailored_resumes"
DEFAULT_TAILOR_RESUME_TEX_PATH = "config/resume.tex"
DEFAULT_CANDIDATE_PROFILE_YAML_PATH = "config/candidate_profile.yaml"

OPT_IN_MODE = "opt_in"
AUTONOMOUS_MODES: frozenset[str] = frozenset({"autonomous", "both"})

_JOB_HASH_RE = re.compile(r"^[a-f0-9]{32,64}$")


class TailorPreflightError(RuntimeError):
    """Represent a fatal preflight check failure for the tailor worker."""


def _validate_job_hash(job_hash: str) -> None:
    """Reject job_hash values that could enable path traversal.

    Purpose:
        Per-job output directories are derived from `job_hash`; only the
        canonical hex hash shape is allowed onto the filesystem.
    Args:
        job_hash: Hash value pulled from the claim result.
    Output:
        Returns `None` when the value matches the canonical hex shape.
    Raises:
        ValueError: When the value contains anything outside hex.
    """

    if not _JOB_HASH_RE.match(job_hash):
        raise ValueError(
            f"Invalid job_hash format — expected 32-64 hex chars, got {job_hash!r}"
        )


def _load_int_env(name: str, default_value: int) -> int:
    """Read a positive integer from environment with a safe fallback.

    Purpose:
        Worker tuning knobs are env-driven; invalid values must not crash
        startup and must not silently disable the worker.
    Args:
        name: Environment variable name.
        default_value: Fallback when parsing fails or the value is non-positive.
    Output:
        Returns the parsed positive integer or `default_value`.
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
        its first claim. The LaTeX engine (tectonic) is bundled into the
        runtime container and verified once on app startup, so a
        per-worker check is no longer needed.
    Args:
        None.
    Output:
        Returns `None` when checks pass.
    Raises:
        TailorPreflightError: When the database parent directory cannot
            be resolved.
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
        Surface fatal startup misconfiguration so operators know to act.
    Args:
        error: Preflight error text describing the missing piece.
    Output:
        Returns `None` after a best-effort notification attempt.
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
        Pipeline errors land here only after `claim_next_tailor_job`
        refuses to retry; surfacing them lets the user intervene.
    Args:
        job_hash: Stable deduplication hash of the failed job.
        error: Final error message stored on the row.
    Output:
        Returns `None` after a best-effort notification attempt.
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
        output_base_dir: Per-run artifact root.
        resume_tex_path: Path to `config/resume.tex`.
        candidate_profile_yaml_path: Path to `config/candidate_profile.yaml`.
        max_retries: Maximum FAILED runs before a job is excluded by claim.
        lease_seconds: PENDING claim lease length.
    Output:
        Returns `1` when a job was attempted (regardless of pipeline
        success), `0` otherwise.
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
        every cycle regardless of mode and the mode-gated claim only
        fires when automation is enabled.
    Args:
        db: Connected database manager.
        output_base_dir: Per-run artifact root.
        resume_tex_path: Path to `config/resume.tex`.
        candidate_profile_yaml_path: Path to `config/candidate_profile.yaml`.
        max_retries: Worker max-retry knob forwarded to claim.
        lease_seconds: Claim lease length (also used as staleness threshold).
    Output:
        Returns `1` when a job was claimed and processed, `0` otherwise.
    """

    stale_count = await db.mark_stale_tailor_runs_failed(lease_seconds=lease_seconds)
    if stale_count > 0:
        logger.warning("Marked {} stale tailor runs as FAILED", stale_count)

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
    """Public one-shot tailor processing entry point.

    Purpose:
        Stable wrapper retained for tests and external scripts that drive
        a single processing pass without entering the loop.
    Args:
        db: Connected database manager.
        output_base_dir: Per-run artifact root.
        resume_tex_path: Path to `config/resume.tex`.
        candidate_profile_yaml_path: Path to `config/candidate_profile.yaml`.
        max_retries: Worker max-retry knob forwarded to claim.
        lease_seconds: Claim lease length (also used as staleness threshold).
    Output:
        Returns the inner cycle's processed count.
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
        Provide an importable entry point so the API supervisor can run
        the tailor loop as an in-process asyncio task without spawning a
        new container or process. Loops forever until cancelled; the
        cancellation propagates out and the supervisor handles cleanup.
    Args:
        db: Connected database manager shared with other in-process loops.
        output_base_dir: Per-run artifact root.
        resume_tex_path: Path to `config/resume.tex`.
        candidate_profile_yaml_path: Path to `config/candidate_profile.yaml`.
        max_retries: Maximum FAILED runs before a job is excluded by claim.
        lease_seconds: PENDING claim lease length.
        poll_interval_seconds: Sleep duration when no job was claimed.
    Output:
        Returns `None` only on `asyncio.CancelledError` (re-raised).
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

        if processed == 0:
            await asyncio.sleep(poll_interval_seconds)


async def main() -> None:
    """Parse CLI args and run the worker once or in a polling loop.

    Purpose:
        Entry point invoked by the systemd unit and CLI users. Loads
        env, validates dependencies, prepares the database, then either
        runs one pass or polls forever — both paths honor the per-stage
        automation mode read on every cycle.
    Args:
        None.
    Output:
        Returns `None` after the requested processing mode completes.
    """

    load_dotenv()

    if not os.environ.get("OPENAI_API_KEY"):
        logger.warning(
            "OPENAI_API_KEY is not set — tailor worker is disabled. "
            "Set OPENAI_API_KEY to enable the tailor pipeline."
        )
        if "--loop" in sys.argv:
            while True:
                await asyncio.sleep(3600)
        return

    parser = argparse.ArgumentParser(
        description="Process QUALIFIED jobs through the resume tailor pipeline",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--loop", action="store_true", help="Poll forever")
    mode_group.add_argument(
        "--once", action="store_true", help="Process once and exit (default)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=os.getenv("TAILOR_OUTPUT_DIR", DEFAULT_TAILOR_OUTPUT_DIR),
    )
    parser.add_argument(
        "--resume-tex-path",
        type=str,
        default=os.getenv("TAILOR_RESUME_TEX_PATH", DEFAULT_TAILOR_RESUME_TEX_PATH),
    )
    parser.add_argument(
        "--candidate-profile-yaml-path",
        type=str,
        default=os.getenv(
            "CANDIDATE_PROFILE_YAML_PATH", DEFAULT_CANDIDATE_PROFILE_YAML_PATH
        ),
    )
    parser.add_argument(
        "--database-path",
        type=str,
        default=None,
        help="SQLite database path (default: from DATABASE_PATH env)",
    )
    args = parser.parse_args()

    should_loop = args.loop and not args.once
    poll_interval_seconds = _load_int_env(
        "TAILOR_POLL_INTERVAL_SECONDS",
        DEFAULT_TAILOR_POLL_INTERVAL_SECONDS,
    )
    max_retries = _load_int_env("TAILOR_MAX_RETRIES", DEFAULT_TAILOR_MAX_RETRIES)
    lease_seconds = _load_int_env(
        "TAILOR_CLAIM_LEASE_SECONDS", DEFAULT_TAILOR_CLAIM_LEASE_SECONDS
    )

    try:
        _check_preflight()
    except TailorPreflightError as exc:
        logger.error("Tailor preflight failed: {}", exc)
        await _notify_preflight_failure(str(exc))
        return

    repo_root = resolve_repo_root()

    output_base_dir = Path(args.output_dir)
    if not output_base_dir.is_absolute():
        output_base_dir = repo_root / output_base_dir

    resume_tex_path = Path(args.resume_tex_path)
    if not resume_tex_path.is_absolute():
        resume_tex_path = repo_root / resume_tex_path

    candidate_profile_yaml_path = Path(args.candidate_profile_yaml_path)
    if not candidate_profile_yaml_path.is_absolute():
        candidate_profile_yaml_path = repo_root / candidate_profile_yaml_path

    if not resume_tex_path.exists():
        logger.error("Resume TeX not found: {}", resume_tex_path)
        await _notify_preflight_failure(f"Resume TeX not found: {resume_tex_path}")
        return

    if args.database_path:
        db_path = str(Path(args.database_path).resolve())
    else:
        db_path = str(resolve_database_path())

    async with DatabaseManager(db_path) as db:
        await db.create_tables()

        if not should_loop:
            await _run_one_cycle(
                db=db,
                output_base_dir=output_base_dir,
                resume_tex_path=resume_tex_path,
                candidate_profile_yaml_path=candidate_profile_yaml_path,
                max_retries=max_retries,
                lease_seconds=lease_seconds,
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
                processed = await _run_one_cycle(
                    db=db,
                    output_base_dir=output_base_dir,
                    resume_tex_path=resume_tex_path,
                    candidate_profile_yaml_path=candidate_profile_yaml_path,
                    max_retries=max_retries,
                    lease_seconds=lease_seconds,
                )
            except Exception as exc:
                logger.exception("Tailor polling cycle failed: {}", exc)

            if processed == 0:
                await asyncio.sleep(poll_interval_seconds)


if __name__ == "__main__":
    asyncio.run(main())
