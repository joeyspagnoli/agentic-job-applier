"""Gate-stage worker loop for the agentic job pipeline.

Runs inside `LoopSupervisor` as an asyncio task when `automation.gate_mode`
is `autonomous` or `both`. Also invocable from the CLI shim in
`scripts/process_new_jobs.py`.
"""

from __future__ import annotations

import asyncio
import json as _json
import os
from datetime import datetime, timedelta, timezone

from loguru import logger

from src.agents.root_apply_decider import (
    GateRunOutcome,
    map_decision_to_status,
    run_gate_with_provider,
)
from src.database._mixins.system_settings import GATE_MODE_KEY
from src.database.db_manager import DatabaseManager
from src.providers.factory import build_provider_from_env
from src.providers.types import AIProvider
from src.utils.cost_tracking import PIPELINE_STAGE_GATE
from src.utils.cost_tracking import check_budget_before_claim
from src.utils.cost_tracking import record_llm_call_cost
from src.utils.notifications import send_ntfy_notification

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


async def _process_once(
    *,
    db: DatabaseManager,
    limit: int,
    provider: AIProvider,
    max_retries: int = DEFAULT_AGENT_MAX_RETRIES,
    backoff_seconds: int = DEFAULT_AGENT_RETRY_BACKOFF_SECONDS,
    backoff_multiplier: int = DEFAULT_AGENT_RETRY_BACKOFF_MULTIPLIER,
) -> int:
    """Process one batch of pending jobs through the decider.

    Purpose:
        Drive the end-to-end batch workflow for fetching pending jobs,
        handling failures, and recording successful decisions. Uses the
        provider-agnostic unified runtime so token-based cost rows fire
        correctly for every gate call.

    Arg(s):
        db: Connected database manager used to load and update job rows.
        limit: Maximum number of pending jobs to process in this batch.
        provider: Configured AI provider built once at worker startup.
        max_retries: Maximum attempts allowed before terminal failure.
        backoff_seconds: Base delay in seconds for retry scheduling.
        backoff_multiplier: Multiplicative factor applied per retry attempt.

    Output:
        Returns the number of jobs successfully processed in the batch.
    """

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
            outcome: GateRunOutcome = await run_gate_with_provider(
                provider=provider,
                job=job,
            )
        except Exception as exc:
            error_text = str(exc)
            retry_count_raw = job.get("agent_retry_count")
            retry_count = int(retry_count_raw) + 1 if isinstance(retry_count_raw, int) else 1
            # No CompletionResponse available on failure — write a zero-cost row
            # directly via db.record_cost_event so the dashboard retains the event.
            await db.record_cost_event(
                stage=PIPELINE_STAGE_GATE,
                cost_usd=0.0,
                job_hash=job_hash,
                run_id=f"gate-{job_hash}-{retry_count}",
                metadata_json=_json.dumps(
                    {
                        "status": "FAILED",
                        "retry_count": retry_count,
                        "phase": "gate_failed",
                    },
                    ensure_ascii=True,
                    sort_keys=True,
                ),
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

        result = outcome.result
        await db.record_agent_decision(
            job_hash=job_hash,
            agent_result=result.model_dump_json(),
            status=map_decision_to_status(result.decision),
        )
        await record_llm_call_cost(
            db=db,
            stage=PIPELINE_STAGE_GATE,
            run_id=f"gate-{job_hash}",
            phase="decision",
            response=outcome.response,
            job_hash=job_hash,
            extra_metadata={"decision": result.decision.value},
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
    provider: AIProvider | None = None,
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
        when the mode is `opt_in`. The provider is built once at loop
        startup so the API key is validated immediately rather than
        per-batch.
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

    provider = build_provider_from_env()

    while True:
        try:
            if await _is_gate_mode_active(db):
                processed = await _process_once(
                    db=db,
                    limit=limit,
                    provider=provider,
                    max_retries=max_retries,
                    backoff_seconds=backoff_seconds,
                    backoff_multiplier=backoff_multiplier,
                )
                logger.info("Gate batch complete: processed={}", processed)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Gate polling cycle failed: {}", exc)

        await asyncio.sleep(poll_interval_seconds)
