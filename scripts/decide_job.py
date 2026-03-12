#!/usr/bin/env python3
"""Run RootApplyDecider for a single job.

Examples:
  uv run python scripts/decide_job.py --job-hash <hash>
  uv run python scripts/decide_job.py --job-hash <hash> --save
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

# Add repo root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.root_apply_decider import build_root_agent, get_decider_model  # noqa: E402
from src.database.db_manager import DatabaseManager  # noqa: E402
from scripts.process_new_jobs import (  # noqa: E402
    _load_candidate_profile,
    _map_status,
    _run_decider_for_job,
)


async def main() -> None:
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
    except Exception as e:
        logger.error(f"Decider model not configured: {e}")
        return

    agent = build_root_agent(model=model)
    candidate_profile = _load_candidate_profile()

    db_path = os.getenv("DATABASE_PATH", "data/jobs.db")
    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        await db.migrate_agent_schema()

        job = await db.get_job_by_hash(args.job_hash)
        if not job:
            logger.error(f"Job not found: {args.job_hash}")
            return

        result = await _run_decider_for_job(
            agent=agent,
            job=job,
            candidate_profile=candidate_profile,
        )

        print(result.model_dump_json(indent=2))

        if args.save:
            await db.record_agent_decision(
                job_hash=args.job_hash,
                agent_result=result.model_dump_json(),
                status=_map_status(result.decision),
            )


if __name__ == "__main__":
    asyncio.run(main())
