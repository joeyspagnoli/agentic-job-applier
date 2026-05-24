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
from datetime import datetime, timedelta, timezone
from collections.abc import Mapping

from dotenv import load_dotenv
from google.adk.agents import BaseAgent
from loguru import logger

from src.agents.root_apply_decider import (
    ApplyDecision,
    GateRunResult,
    build_root_agent,
    get_decider_model,
    get_decider_model_name,
    get_decider_provider,
    map_decision_to_status,
    run_decider_for_job,
)
from src.database._mixins.system_settings import GATE_MODE_KEY
from src.database.db_manager import DatabaseManager
from src.utils.cost_tracking import PIPELINE_STAGE_GATE
from src.utils.cost_tracking import check_budget_before_claim
from src.utils.cost_tracking import record_stage_cost_event
from src.utils.notifications import send_ntfy_notification
from src.utils.paths import resolve_database_path

DEFAULT_AGENT_BATCH_LIMIT = 25
DEFAULT_AGENT_POLL_INTERVAL_SECONDS = 60
DEFAULT_AGENT_MAX_RETRIES = 3
DEFAULT_AGENT_RETRY_BACKOFF_SECONDS = 300
DEFAULT_AGENT_RETRY_BACKOFF_MULTIPLIER = 3

# When the autonomous toggle is OFF, the gate row is set to `opt_in` and the
# loop must skip all LLM-calling work — the gate has no user-trigger entry
# point today, so opt_in effectively means "do nothing this cycle".
GATE_OPT_IN_MODE = "opt_in"
GATE_AUTONOMOUS_MODES: frozenset[str] = frozenset({"autonomous", "both"})


class ModelConfigurationError(RuntimeError):
    """Represent missing or invalid model configuration for the gate worker."""


def _map_status(decision: ApplyDecision) -> str:
    """Translate an agent decision into the stored workflow status.

    Purpose:
        Keep the mapping from gate output to database workflow status in one
        place so both scripts persist the same status values.
    Args:
        decision: Apply/skip decision returned by the gate.
    Output:
        Returns `QUALIFIED` for apply decisions and `FILTERED` for skip decisions.
    """

    return map_decision_to_status(decision)


def _load_int_env(name: str, default_value: int) -> int:
    """Read a positive integer from environment and fall back safely.

    Purpose:
        Keep CLI/env configuration parsing consistent for worker tuning knobs
        while preventing invalid values from crashing startup.
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
        Centralize the retry-backoff formula used by the worker so behavior is
        deterministic and easy to test.
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
        agent failures.
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


async def _notify_terminal_failure(
    *,
    job_hash: str,
    error: str,
    retry_count: int,
) -> None:
    """Send an ntfy alert for a job that exhausted all retry attempts.

    Purpose:
        Notify operators when manual intervention is needed after terminal gate
        processing failure.
    Args:
        job_hash: Stable deduplication hash for the failed job.
        error: Terminal error message stored in the database.
        retry_count: Number of attempts made before terminal failure.
    Output:
        Returns `None` after best-effort notification attempt.
    """

    await send_ntfy_notification(
        title="Job gate terminal failure",
        message=(
            "Root gate exhausted retries and needs intervention.\n"
            f"job_hash={job_hash}\n"
            f"retry_count={retry_count}\n"
            f"error={error}"
        ),
        tags=("warning", "rotating_light"),
        priority="high",
    )


async def _notify_worker_configuration_failure(error: str) -> None:
    """Send a one-time ntfy alert for worker model configuration failure.

    Purpose:
        Surface fatal startup misconfiguration to operators without creating
        notification spam every polling cycle.
    Args:
        error: Configuration error text that prevented model creation.
    Output:
        Returns `None` after best-effort notification attempt.
    """

    await send_ntfy_notification(
        title="Job gate worker configuration failure",
        message=(
            "Root gate worker could not initialize its model configuration.\n"
            f"error={error}"
        ),
        tags=("warning", "gear"),
        priority="high",
    )


async def _run_decider_for_job(
    *,
    agent: BaseAgent,
    job: Mapping[str, object],
) -> GateRunResult:
    """Run the ADK decider for one job and parse its raw response locally.

    Purpose:
        Execute one isolated ADK session, capture the model's final text
        response, and turn it into a durable gate result payload.
    Args:
        agent: Configured ADK agent instance to run.
        job: Database row representing the job being evaluated.
    Output:
        Returns a validated `GateRunResult`, or raises an error when the
        decision cannot be recovered from the model response.
    """

    return await run_decider_for_job(
        agent=agent,
        job=job,
    )


async def _process_once(
    *,
    db: DatabaseManager,
    limit: int,
    max_retries: int = DEFAULT_AGENT_MAX_RETRIES,
    backoff_seconds: int = DEFAULT_AGENT_RETRY_BACKOFF_SECONDS,
    backoff_multiplier: int = DEFAULT_AGENT_RETRY_BACKOFF_MULTIPLIER,
) -> int:
    """Process one batch of pending jobs through the decider.

    Purpose:
        Drive the end-to-end batch workflow for loading the model, fetching
        pending jobs, handling failures, and recording successful decisions.

    Arg(s):
        db: Connected database manager used to load and update job rows.
        limit: Maximum number of pending jobs to process in this batch.
        max_retries: Maximum attempts allowed before terminal failure.
        backoff_seconds: Base delay in seconds for retry scheduling.
        backoff_multiplier: Multiplicative factor applied per retry attempt.

    Output:
        Returns the number of jobs successfully processed in the batch.
    """

    try:
        model = get_decider_model()
    except Exception as exc:
        raise ModelConfigurationError(str(exc)) from exc

    agent = build_root_agent(model=model)
    if not await check_budget_before_claim(db=db, stage=PIPELINE_STAGE_GATE):
        return 0

    jobs = await db.get_jobs_pending_agent_processing(limit=limit)
    if not jobs:
        logger.info("No NEW jobs pending agent processing")
        return 0

    processed = 0
    for job in jobs:
        job_hash_raw = job.get("job_hash")
        if not job_hash_raw or not isinstance(job_hash_raw, str):
            logger.warning("Skipping job without job_hash")
            continue
        job_hash: str = job_hash_raw

        # Each job is isolated so a single provider or parsing error does not
        # stop the rest of the batch from being evaluated and persisted.
        try:
            result = await _run_decider_for_job(
                agent=agent,
                job=job,
            )
        except Exception as exc:
            error_text = str(exc)
            retry_count_raw = job.get("agent_retry_count")
            retry_count = int(retry_count_raw) + 1 if isinstance(retry_count_raw, int) else 1
            await record_stage_cost_event(
                db=db,
                stage=PIPELINE_STAGE_GATE,
                job_hash=job_hash,
                run_id=f"gate-{job_hash}-{retry_count}",
                metadata={
                    "status": "FAILED",
                    "model": get_decider_model_name(),
                    "provider": get_decider_provider(),
                    "retry_count": retry_count,
                },
            )

            if retry_count < max_retries:
                next_retry_at = _calculate_next_retry_at(
                    retry_count=retry_count,
                    backoff_seconds=backoff_seconds,
                    backoff_multiplier=backoff_multiplier,
                )
                logger.warning(
                    "Decider failed for job {} (attempt {}/{}). "
                    "Retry scheduled at {}. Error: {}",
                    job_hash,
                    retry_count,
                    max_retries,
                    next_retry_at,
                    error_text,
                )
                await db.record_agent_retry(
                    job_hash=job_hash,
                    error=error_text,
                    retry_count=retry_count,
                    next_retry_at=next_retry_at,
                )
                continue

            logger.error(
                "Decider terminal failure for job {} after {} attempts: {}",
                job_hash,
                retry_count,
                error_text,
            )
            await db.mark_job_agent_terminal_failed(
                job_hash,
                error_text,
                retry_count=retry_count,
            )
            await _notify_terminal_failure(
                job_hash=job_hash,
                error=error_text,
                retry_count=retry_count,
            )
            continue

        await db.record_agent_decision(
            job_hash=job_hash,
            agent_result=result.model_dump_json(),
            status=_map_status(result.decision),
        )
        await record_stage_cost_event(
            db=db,
            stage=PIPELINE_STAGE_GATE,
            job_hash=job_hash,
            run_id=f"gate-{job_hash}",
            metadata={
                "status": "SUCCESS",
                "model": result.model,
                "provider": get_decider_provider(),
                "decision": result.decision.value,
            },
        )
        processed += 1

        confidence = result.debug.confidence
        confidence_text = f"{confidence:.2f}" if confidence is not None else "n/a"
        logger.info(
            "Processed {}: decision={} confidence={} model={} parse_mode={}",
            job_hash,
            result.decision.value,
            confidence_text,
            result.model,
            result.parse_mode,
        )

    return processed


    # If Codex home has auth, prefer unified path.
    codex_home = os.getenv("CODEX_HOME", "")
    if codex_home:
        auth_path = os.path.join(codex_home, "auth.json")
        if os.path.isfile(auth_path):
            return True
    return False


async def _is_gate_mode_active(db: DatabaseManager) -> bool:
    """Return True when the stored gate mode permits LLM calls this cycle.

    Purpose:
        Hard-gate every poll cycle on the per-stage automation mode so
        the gate worker emits zero LLM calls (and therefore zero spend)
        when the user has the autonomous toggle off.
    Args:
        db: Connected database manager.
    Output:
        Returns `True` for `autonomous` and `both`; `False` for `opt_in`
        and any unknown value.
    """

    mode = await db.get_automation_mode(GATE_MODE_KEY)
    if mode in GATE_AUTONOMOUS_MODES:
        return True
    if mode == GATE_OPT_IN_MODE:
        logger.debug("Gate mode is opt_in; skipping batch this cycle")
        return False
    logger.warning("Unknown gate mode {!r}; treating as opt_in", mode)
    return False


async def process_once(
    *,
    db: DatabaseManager,
    limit: int,
    max_retries: int = DEFAULT_AGENT_MAX_RETRIES,
    backoff_seconds: int = DEFAULT_AGENT_RETRY_BACKOFF_SECONDS,
    backoff_multiplier: int = DEFAULT_AGENT_RETRY_BACKOFF_MULTIPLIER,
) -> int:
    """Run one public processing batch for external orchestration calls.

    Purpose:
        Expose a stable one-shot processing API for scripts/tests that should
        not depend on private helper naming.

    Arg(s):
        db: Connected database manager used for queue reads and updates.
        limit: Maximum number of jobs to process in this batch.
        max_retries: Maximum attempts before terminal failure.
        backoff_seconds: Base backoff delay for retry scheduling.
        backoff_multiplier: Multiplicative backoff factor per retry attempt.

    Output:
        Returns the number of jobs successfully processed in the batch.
    """
    return await _process_once(
        db=db,
        limit=limit,
        max_retries=max_retries,
        backoff_seconds=backoff_seconds,
        backoff_multiplier=backoff_multiplier,
    )


async def run_gate_loop(
    *,
    db: DatabaseManager,
    limit: int = DEFAULT_AGENT_BATCH_LIMIT,
    max_retries: int = DEFAULT_AGENT_MAX_RETRIES,
    backoff_seconds: int = DEFAULT_AGENT_RETRY_BACKOFF_SECONDS,
    backoff_multiplier: int = DEFAULT_AGENT_RETRY_BACKOFF_MULTIPLIER,
    poll_interval_seconds: int = DEFAULT_AGENT_POLL_INTERVAL_SECONDS,
) -> None:
    """Run the gate worker poll loop using a shared database manager.

    Purpose:
        Provide an importable entry point so the API supervisor can run
        the gate loop as an in-process asyncio task. The loop reads the
        per-stage automation mode every cycle and emits zero LLM calls
        when the mode is `opt_in`.
    Args:
        db: Connected database manager shared with other in-process loops.
        limit: Maximum jobs claimed per batch.
        max_retries: Maximum agent retries before terminal failure.
        backoff_seconds: Base retry backoff delay.
        backoff_multiplier: Exponential backoff factor per retry.
        poll_interval_seconds: Sleep duration between cycles.
    Output:
        Returns `None` only on `asyncio.CancelledError` (re-raised).
    """

    logger.info(
        "Gate loop entering poll: poll={}s limit={} max_retries={}",
        poll_interval_seconds,
        limit,
        max_retries,
    )

    while True:
        try:
            if await _is_gate_mode_active(db):
                processed = await process_once(
                    db=db,
                    limit=limit,
                    max_retries=max_retries,
                    backoff_seconds=backoff_seconds,
                    backoff_multiplier=backoff_multiplier,
                )
                logger.info("Gate batch complete: processed={}", processed)
        except asyncio.CancelledError:
            raise
        except ModelConfigurationError as exc:
            logger.error("Decider model not configured; will retry: {}", exc)
        except Exception as exc:
            logger.exception("Gate polling cycle failed: {}", exc)

        await asyncio.sleep(poll_interval_seconds)


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

    parser = argparse.ArgumentParser(description="Process NEW jobs using ADK decider")
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
    db_path = str(resolve_database_path())
    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        await db.migrate_agent_schema()
        await db.migrate_cost_schema()
        startup_alert_sent = False

        # The default behavior is a single batch run so the script remains easy
        # to invoke manually and safe to schedule externally.
        if not should_loop:
            try:
                await _process_once(
                    db=db,
                    limit=args.limit,
                    max_retries=max_retries,
                    backoff_seconds=backoff_seconds,
                    backoff_multiplier=backoff_multiplier,
                )
            except ModelConfigurationError as exc:
                logger.error("Decider model not configured: {}", exc)
                await _notify_worker_configuration_failure(str(exc))
            return

        while True:
            try:
                if not await _is_gate_mode_active(db):
                    await asyncio.sleep(poll_interval_seconds)
                    continue
                processed = await _process_once(
                    db=db,
                    limit=args.limit,
                    max_retries=max_retries,
                    backoff_seconds=backoff_seconds,
                    backoff_multiplier=backoff_multiplier,
                )
                logger.info(
                    "Agent batch complete: processed={} provider={} model={}",
                    processed,
                    get_decider_provider(),
                    get_decider_model_name(),
                )
                startup_alert_sent = False
            except ModelConfigurationError as exc:
                logger.error(
                    "Decider model not configured; worker will retry next cycle: {}",
                    exc,
                )
                if not startup_alert_sent:
                    await _notify_worker_configuration_failure(str(exc))
                    startup_alert_sent = True
            except Exception as exc:
                logger.exception(f"Agent polling cycle failed: {exc}")
            await asyncio.sleep(poll_interval_seconds)


if __name__ == "__main__":
    asyncio.run(main())


__all__ = [
    "asyncio",
    "process_once",
    "_process_once",
    "main",
]
