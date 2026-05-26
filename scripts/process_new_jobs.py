#!/usr/bin/env python3
"""Process NEW jobs with the RootApplyDecider agent.

Run once (default):
  uv run python -m scripts.process_new_jobs

Run continuously:
  AGENT_POLL_INTERVAL_SECONDS=60 uv run python -m scripts.process_new_jobs --loop
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv
from loguru import logger

# Re-export names that supervisor, run_pipeline_once, and tests import
# from this module. Importing them into the module namespace means that
# monkeypatching `process_new_jobs.<name>` in tests intercepts calls made
# by the local `process_once` wrapper below (Python resolves free names in
# the module's global dict at call time, not at definition time).
from src.workers.gate import (  # noqa: F401  re-export
    DEFAULT_AGENT_BATCH_LIMIT,
    DEFAULT_AGENT_MAX_RETRIES,
    DEFAULT_AGENT_POLL_INTERVAL_SECONDS,
    DEFAULT_AGENT_RETRY_BACKOFF_MULTIPLIER,
    DEFAULT_AGENT_RETRY_BACKOFF_SECONDS,
    ModelConfigurationError,
    _is_gate_mode_active,
    _load_int_env,
    _process_once,
    run_gate_loop,
)
from src.database.db_manager import DatabaseManager
from src.providers.factory import build_provider_from_env
from src.providers.types import AIProvider
from src.utils.paths import resolve_database_path


async def process_once(
    *,
    db: DatabaseManager,
    limit: int,
    provider: AIProvider | None = None,
    max_retries: int = DEFAULT_AGENT_MAX_RETRIES,
    backoff_seconds: int = DEFAULT_AGENT_RETRY_BACKOFF_SECONDS,
    backoff_multiplier: int = DEFAULT_AGENT_RETRY_BACKOFF_MULTIPLIER,
) -> int:
    """Run one public processing batch for external orchestration calls.

    Purpose:
        Expose a stable one-shot processing API for scripts/tests that should
        not depend on private helper naming. Defined locally so that tests can
        monkeypatch `process_new_jobs._process_once` and
        `process_new_jobs.build_provider_from_env` and have those patches
        observed by this function (Python resolves module-global names at call
        time).

    Arg(s):
        db: Connected database manager used for queue reads and updates.
        limit: Maximum number of jobs to process in this batch.
        provider: Configured AI provider; built from env when not supplied.
        max_retries: Maximum attempts before terminal failure.
        backoff_seconds: Base backoff delay for retry scheduling.
        backoff_multiplier: Multiplicative backoff factor per retry attempt.

    Output:
        Returns the number of jobs successfully processed in the batch.
    """
    resolved_provider = provider if provider is not None else build_provider_from_env()
    return await _process_once(
        db=db,
        limit=limit,
        provider=resolved_provider,
        max_retries=max_retries,
        backoff_seconds=backoff_seconds,
        backoff_multiplier=backoff_multiplier,
    )


async def main() -> None:
    """Parse CLI args and run one-shot or looping agent processing.

    Purpose:
        Provide the script entrypoint that loads environment variables, prepares
        the database, and decides whether to run once or poll continuously.
    Args:
        None.
    Output:
        Returns `None` after completing the requested processing mode.
    """

    load_dotenv()

    if not os.environ.get("OPENAI_API_KEY"):
        logger.warning(
            "OPENAI_API_KEY is not set — gate worker is disabled. "
            "Jobs will be fetched and stored as NEW but not classified. "
            "Set OPENAI_API_KEY to enable the gate worker."
        )
        if "--loop" in sys.argv:
            while True:
                await asyncio.sleep(3600)
        return

    parser = argparse.ArgumentParser(description="Process NEW jobs with the gate decider")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--loop", action="store_true", help="Poll forever")
    mode_group.add_argument(
        "--once",
        action="store_true",
        help="Process once and exit (default behavior)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=_load_int_env(
            "AGENT_BATCH_LIMIT",
            _load_int_env("AGENT_BATCH_SIZE", DEFAULT_AGENT_BATCH_LIMIT),
        ),
        help=(
            "Max jobs to process per cycle "
            "(default: env AGENT_BATCH_LIMIT/AGENT_BATCH_SIZE or 25)"
        ),
    )
    args = parser.parse_args()

    should_loop = args.loop and not args.once
    poll_interval_seconds = _load_int_env(
        "AGENT_POLL_INTERVAL_SECONDS",
        DEFAULT_AGENT_POLL_INTERVAL_SECONDS,
    )
    max_retries = _load_int_env("AGENT_MAX_RETRIES", DEFAULT_AGENT_MAX_RETRIES)
    backoff_seconds = _load_int_env(
        "AGENT_RETRY_BACKOFF_SECONDS",
        DEFAULT_AGENT_RETRY_BACKOFF_SECONDS,
    )
    backoff_multiplier = _load_int_env(
        "AGENT_RETRY_BACKOFF_MULTIPLIER",
        DEFAULT_AGENT_RETRY_BACKOFF_MULTIPLIER,
    )

    # Build the provider once; validates the API key before entering the loop.
    provider = build_provider_from_env()

    db_path = str(resolve_database_path())
    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        await db.migrate_agent_schema()
        await db.migrate_cost_schema()

        # The default behavior is a single batch run so the script remains easy
        # to invoke manually and safe to schedule externally.
        if not should_loop:
            await _process_once(
                db=db,
                limit=args.limit,
                provider=provider,
                max_retries=max_retries,
                backoff_seconds=backoff_seconds,
                backoff_multiplier=backoff_multiplier,
            )
            return

        while True:
            try:
                if not await _is_gate_mode_active(db):
                    await asyncio.sleep(poll_interval_seconds)
                    continue
                processed = await _process_once(
                    db=db,
                    limit=args.limit,
                    provider=provider,
                    max_retries=max_retries,
                    backoff_seconds=backoff_seconds,
                    backoff_multiplier=backoff_multiplier,
                )
                logger.info("Agent batch complete: processed={}", processed)
            except Exception as exc:
                logger.exception("Agent polling cycle failed: {}", exc)
            await asyncio.sleep(poll_interval_seconds)


if __name__ == "__main__":
    asyncio.run(main())


__all__ = [
    "AIProvider",
    "DEFAULT_AGENT_BATCH_LIMIT",
    "DEFAULT_AGENT_MAX_RETRIES",
    "DEFAULT_AGENT_POLL_INTERVAL_SECONDS",
    "DEFAULT_AGENT_RETRY_BACKOFF_MULTIPLIER",
    "DEFAULT_AGENT_RETRY_BACKOFF_SECONDS",
    "DatabaseManager",
    "ModelConfigurationError",
    "_is_gate_mode_active",
    "_load_int_env",
    "_process_once",
    "asyncio",
    "build_provider_from_env",
    "load_dotenv",
    "logger",
    "main",
    "process_once",
    "resolve_database_path",
    "run_gate_loop",
]
