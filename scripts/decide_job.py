#!/usr/bin/env python3
"""Run RootApplyDecider for a single stored job.

Examples:
  uv run python -m scripts.decide_job --job-hash <hash>
  uv run python -m scripts.decide_job --job-hash <hash> --save
"""

from __future__ import annotations

import argparse
import asyncio

from dotenv import load_dotenv
from loguru import logger

from src.agents.root_apply_decider import (
    build_root_agent,
    get_decider_model,
    map_decision_to_status,
    run_decider_for_job,
)
from src.database.db_manager import DatabaseManager
from src.utils.paths import resolve_database_path


async def main() -> None:
    """Parse CLI args, run the decider for one job, and optionally persist it.

    Purpose:
        Provide a focused debugging and inspection tool for running the agent on
        a single stored job outside the batch processor.
    Args:
        None.
    Output:
        Returns `None` after printing the agent result and optionally saving the
        resulting status transition back to the database.
    """

    load_dotenv()

    parser = argparse.ArgumentParser(description="Run RootApplyDecider on a job")
    parser.add_argument("--job-hash", required=True)
    parser.add_argument(
        "--save",
        action="store_true",
        help="Persist agent_result and status updates back to the DB",
    )
    args = parser.parse_args()

    try:
        model = get_decider_model()
    except Exception as exc:
        logger.error(f"Decider model not configured: {exc}")
        return

    agent = build_root_agent(model=model)
    db_path = str(resolve_database_path())

    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        await db.migrate_agent_schema()

        # The script operates on an existing stored row so the hash lookup is
        # validated before any model work is attempted.
        job = await db.get_job_by_hash(args.job_hash)
        if not job:
            logger.error(f"Job not found: {args.job_hash}")
            return

        result = await run_decider_for_job(
            agent=agent,
            job=job,
        )
        print(result.model_dump_json(indent=2))

        # Saving is optional so the script can be used as a dry-run debugging
        # tool without mutating the stored status of the target job.
        if args.save:
            await db.record_agent_decision(
                job_hash=args.job_hash,
                agent_result=result.model_dump_json(),
                status=map_decision_to_status(result.decision),
            )


if __name__ == "__main__":
    asyncio.run(main())
