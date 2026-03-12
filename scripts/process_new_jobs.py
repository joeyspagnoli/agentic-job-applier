#!/usr/bin/env python3
"""Process NEW jobs with the RootApplyDecider agent.

Run once (default):
  uv run python scripts/process_new_jobs.py

Run continuously:
  AGENT_POLL_INTERVAL_SECONDS=60 uv run python scripts/process_new_jobs.py --loop
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from loguru import logger

# Add repo root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.root_apply_decider import (  # noqa: E402
    DECIDER_OUTPUT_KEY,
    ApplyDecision,
    RootApplyDeciderOutput,
    build_root_agent,
    get_decider_model,
)
from src.database.db_manager import DatabaseManager  # noqa: E402


def _load_candidate_profile() -> dict[str, Any]:
    profile_path_raw = os.getenv("CANDIDATE_PROFILE_PATH")
    if not profile_path_raw:
        logger.warning("CANDIDATE_PROFILE_PATH not set; using placeholder profile")
        return {"summary": "No candidate profile provided."}

    profile_path = Path(profile_path_raw)
    if not profile_path.exists():
        logger.warning(
            f"Candidate profile not found at {profile_path}; using placeholder"
        )
        return {"summary": f"Candidate profile missing at {profile_path}"}

    raw_text = profile_path.read_text(encoding="utf-8")

    if profile_path.suffix.lower() in {".yml", ".yaml"}:
        try:
            import yaml  # local import to keep module import minimal

            parsed = yaml.safe_load(raw_text)
            return parsed if isinstance(parsed, dict) else {"profile": parsed}
        except Exception as e:
            logger.warning(f"Failed to parse YAML profile ({profile_path}): {e}")
            return {"raw_text": raw_text}

    if profile_path.suffix.lower() == ".json":
        try:
            parsed = json.loads(raw_text)
            return parsed if isinstance(parsed, dict) else {"profile": parsed}
        except Exception as e:
            logger.warning(f"Failed to parse JSON profile ({profile_path}): {e}")
            return {"raw_text": raw_text}

    return {"raw_text": raw_text}


def _build_prompt(job: dict[str, Any], candidate_profile: dict[str, Any]) -> str:
    job_payload = {
        "job_hash": job.get("job_hash"),
        "source": job.get("source"),
        "source_url": job.get("source_url"),
        "company": job.get("company"),
        "title": job.get("title"),
        "location": job.get("location"),
        "is_remote": job.get("is_remote"),
        "job_type": job.get("job_type"),
        "description": job.get("description"),
        "requirements": job.get("requirements"),
    }
    return json.dumps(
        {"candidate_profile": candidate_profile, "job_posting": job_payload},
        ensure_ascii=False,
    )


async def _run_decider_for_job(
    *,
    agent: Any,
    job: dict[str, Any],
    candidate_profile: dict[str, Any],
) -> RootApplyDeciderOutput:
    session_service = InMemorySessionService()

    app_name = "job_apply_decider"
    user_id = "worker"
    session_id = str(uuid.uuid4())
    await session_service.create_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
        state={},
    )

    runner = Runner(agent=agent, app_name=app_name, session_service=session_service)
    try:
        new_message = types.Content(
            role="user",
            parts=[types.Part(text=_build_prompt(job, candidate_profile))],
        )

        # Consume events until completion to ensure session state is persisted.
        async for _event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=new_message,
        ):
            pass
    finally:
        await runner.close()

    session = await session_service.get_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )

    if session is None:
        raise RuntimeError("Failed to load ADK session after run")

    output_raw = session.state.get(DECIDER_OUTPUT_KEY)
    if output_raw is None:
        raise RuntimeError(
            f"Agent did not write '{DECIDER_OUTPUT_KEY}' to session state"
        )

    if isinstance(output_raw, str):
        return RootApplyDeciderOutput.model_validate_json(output_raw)

    return RootApplyDeciderOutput.model_validate(output_raw)


def _map_status(decision: ApplyDecision) -> str:
    return "QUALIFIED" if decision == ApplyDecision.APPLY else "FILTERED"


async def _process_once(*, db: DatabaseManager, limit: int) -> int:
    try:
        model = get_decider_model()
    except Exception as e:
        logger.warning(
            f"Decider model not configured; skipping job processing. Error: {e}"
        )
        return 0

    agent = build_root_agent(model=model)
    candidate_profile = _load_candidate_profile()

    jobs = await db.get_jobs_pending_agent_processing(limit=limit)
    if not jobs:
        logger.info("No NEW jobs pending agent processing")
        return 0

    processed = 0
    for job in jobs:
        job_hash = job.get("job_hash")
        if not job_hash:
            logger.warning("Skipping job without job_hash")
            continue

        try:
            result = await _run_decider_for_job(
                agent=agent,
                job=job,
                candidate_profile=candidate_profile,
            )
        except Exception as e:
            logger.error(f"Decider failed for job {job_hash}: {e}")
            await db.mark_job_agent_failed(job_hash, str(e))
            continue

        await db.record_agent_decision(
            job_hash=job_hash,
            agent_result=result.model_dump_json(),
            status=_map_status(result.decision),
        )
        processed += 1
        logger.info(
            f"Processed {job_hash}: decision={result.decision.value} confidence={result.confidence:.2f}"
        )

    return processed


async def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Process NEW jobs using ADK decider")
    parser.add_argument("--loop", action="store_true", help="Poll forever")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process once and exit (default behavior)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=int(
            os.getenv("AGENT_BATCH_LIMIT", os.getenv("AGENT_BATCH_SIZE", "25"))
        ),
        help=(
            "Max jobs to process per cycle (default: env AGENT_BATCH_LIMIT/AGENT_BATCH_SIZE or 25)"
        ),
    )
    args = parser.parse_args()

    should_loop = args.loop
    poll_interval_seconds = int(os.getenv("AGENT_POLL_INTERVAL_SECONDS", "60"))

    db_path = os.getenv("DATABASE_PATH", "data/jobs.db")
    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        await db.migrate_agent_schema()

        if not should_loop:
            await _process_once(db=db, limit=args.limit)
            return

        while True:
            await _process_once(db=db, limit=args.limit)
            await asyncio.sleep(poll_interval_seconds)


if __name__ == "__main__":
    asyncio.run(main())
