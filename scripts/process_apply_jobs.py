#!/usr/bin/env python3
"""Thin shim: apply worker CLI entry point.

The loop body lives in ``src.workers.apply``. This module re-exports every
name that external callers (supervisor, routers, tests) import from this path
so backward-compatible imports keep working unchanged.

Run once (default):
  uv run python -m scripts.process_apply_jobs

Run continuously:
  APPLY_POLL_INTERVAL_SECONDS=60 uv run python -m scripts.process_apply_jobs --loop
"""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

# Re-export every name that external callers import from this module path.
# supervisor.py, apply_runs.py, and test monkeypatchers all reach these names
# via ``from scripts.process_apply_jobs import <name>`` or attribute access on
# the module object — they must remain available here.
from src.workers.apply import (  # re-export
    DEFAULT_APPLY_MAX_RETRIES,
    DEFAULT_APPLY_OUTPUT_DIR,
    DEFAULT_APPLY_POLL_INTERVAL_SECONDS,
    DEFAULT_APPLY_RETRY_BACKOFF_MULTIPLIER,
    DEFAULT_APPLY_RETRY_BACKOFF_SECONDS,
    ApplyPreflightError,
    _apply_once,
    _calculate_next_retry_at,
    _check_chrome_preflight,
    _check_preflight,
    _is_apply_mode_active,
    _load_int_env,
    _process_apply_row,
    apply_to_job,
    check_chrome_reachable,
    run_apply_loop,
)
from src.agents.apply_worker.finisher_integration import safe_mode_from_env
from src.agents.apply_worker.schemas import DEFAULT_CDP_URL
from src.database.db_manager import DEFAULT_APPLY_CLAIM_LEASE_SECONDS
from src.database.db_manager import DatabaseManager
from src.utils.paths import resolve_database_path
from src.utils.paths import resolve_repo_root
from src.workers.apply import AUTO_SUBMIT_DISABLED_MESSAGE  # re-export

__all__ = [
    "AUTO_SUBMIT_DISABLED_MESSAGE",
    "ApplyPreflightError",
    "DEFAULT_APPLY_MAX_RETRIES",
    "DEFAULT_APPLY_OUTPUT_DIR",
    "DEFAULT_APPLY_POLL_INTERVAL_SECONDS",
    "DEFAULT_APPLY_RETRY_BACKOFF_MULTIPLIER",
    "DEFAULT_APPLY_RETRY_BACKOFF_SECONDS",
    "_apply_once",
    "_calculate_next_retry_at",
    "_check_chrome_preflight",
    "_check_preflight",
    "_is_apply_mode_active",
    "_load_int_env",
    "_process_apply_row",
    "apply_to_job",
    "check_chrome_reachable",
    "main",
    "run_apply_loop",
]


async def main() -> None:
    """Entry point for the apply worker CLI."""

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
