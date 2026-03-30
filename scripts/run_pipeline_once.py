#!/usr/bin/env python3
"""Run one full discovery-plus-gate pipeline cycle.

Examples:
  uv run python -m scripts.run_pipeline_once
  uv run python -m scripts.run_pipeline_once --limit 50
"""

from __future__ import annotations

import argparse
import asyncio
import os

from dotenv import load_dotenv
from loguru import logger

from main import run_job_discovery
from scripts.process_new_jobs import (
    DEFAULT_AGENT_MAX_RETRIES,
    DEFAULT_AGENT_RETRY_BACKOFF_MULTIPLIER,
    DEFAULT_AGENT_RETRY_BACKOFF_SECONDS,
    ModelConfigurationError,
    process_once,
)
from src.database.db_manager import DatabaseManager
from src.utils.paths import resolve_database_path

DEFAULT_PIPELINE_LIMIT = 25


def _load_positive_int_env(name: str, default_value: int) -> int:
    """Read a positive integer from environment with safe fallback.

    Purpose:
        Keep one-shot pipeline retries configurable through env variables while
        preventing malformed values from breaking manual operations.
    Args:
        name: Environment variable name to parse.
        default_value: Fallback integer for invalid or missing values.
    Output:
        Returns a positive integer for the requested configuration value.
    """

    raw_value = os.getenv(name)
    if raw_value is None:
        return default_value

    try:
        parsed = int(raw_value)
    except ValueError:
        logger.warning(
            "Invalid integer for {}='{}'; using default {}",
            name,
            raw_value,
            default_value,
        )
        return default_value

    if parsed <= 0:
        logger.warning(
            "Non-positive value for {}={}; using default {}",
            name,
            parsed,
            default_value,
        )
        return default_value
    return parsed


async def run_pipeline_once(*, limit: int) -> int:
    """Execute one discovery cycle followed by one agent processing batch.

    Purpose:
        Provide an explicit one-shot command for local verification and manual
        operations that mirrors production producer/consumer behavior.
    Args:
        limit: Maximum number of pending jobs to process in the gate batch.
    Output:
        Returns the number of jobs successfully processed by the gate batch.
    """

    await run_job_discovery()

    max_retries = _load_positive_int_env("AGENT_MAX_RETRIES", DEFAULT_AGENT_MAX_RETRIES)
    backoff_seconds = _load_positive_int_env(
        "AGENT_RETRY_BACKOFF_SECONDS",
        DEFAULT_AGENT_RETRY_BACKOFF_SECONDS,
    )
    backoff_multiplier = _load_positive_int_env(
        "AGENT_RETRY_BACKOFF_MULTIPLIER",
        DEFAULT_AGENT_RETRY_BACKOFF_MULTIPLIER,
    )

    db_path = str(resolve_database_path())
    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        await db.migrate_agent_schema()
        return await process_once(
            db=db,
            limit=limit,
            max_retries=max_retries,
            backoff_seconds=backoff_seconds,
            backoff_multiplier=backoff_multiplier,
        )


async def main() -> int:
    """Parse CLI args and run one full pipeline cycle.

    Purpose:
        Expose `run_pipeline_once` as a user-facing command-line entrypoint.
    Args:
        None.
    Output:
        Returns process exit code semantics for shell and scheduler callers.
    """

    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Run one discovery cycle followed by one gate-processing batch",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=_load_positive_int_env("AGENT_BATCH_LIMIT", DEFAULT_PIPELINE_LIMIT),
        help="Max jobs to process in the gate batch",
    )
    args = parser.parse_args()

    try:
        processed_count = await run_pipeline_once(limit=args.limit)
    except ModelConfigurationError as exc:
        logger.error("Decider model not configured: {}", exc)
        return 1

    logger.info("Pipeline complete. Gate processed {} jobs.", processed_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))


__all__ = [
    "logger",
    "run_pipeline_once",
    "main",
]
