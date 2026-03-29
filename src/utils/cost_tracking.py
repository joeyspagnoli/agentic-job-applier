"""Record configurable pipeline cost events for dashboard analytics.

This module centralizes environment-driven stage rates so each worker can
emit consistent cost telemetry without duplicating parsing logic.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Any

from loguru import logger

from src.database.db_manager import DatabaseManager

PIPELINE_STAGE_GATE = "GATE"
PIPELINE_STAGE_TAILOR = "TAILOR"
PIPELINE_STAGE_REVIEW = "REVIEW"
PIPELINE_STAGE_APPLY = "APPLY"
PIPELINE_STAGE_DISCOVERY = "DISCOVERY"

_STAGE_RATE_ENV_KEYS: dict[str, str] = {
    PIPELINE_STAGE_GATE: "COST_RATE_GATE_USD",
    PIPELINE_STAGE_TAILOR: "COST_RATE_TAILOR_USD",
    PIPELINE_STAGE_REVIEW: "COST_RATE_REVIEW_USD",
    PIPELINE_STAGE_APPLY: "COST_RATE_APPLY_USD",
    PIPELINE_STAGE_DISCOVERY: "COST_RATE_DISCOVERY_USD",
}

_DEFAULT_STAGE_RATE_USD = 0.0


def _coerce_stage_rate_usd(stage: str) -> float:
    """Resolve one stage rate from environment with safe fallback.

    Purpose:
        Keep worker cost writes resilient to missing or malformed env values so
        operational pipelines continue while surfacing configuration issues.
    Args:
        stage: Pipeline stage label used to select the corresponding env key.
    Output:
        Returns a non-negative USD rate for this stage.
    """

    env_key = _STAGE_RATE_ENV_KEYS.get(stage)
    if env_key is None:
        return _DEFAULT_STAGE_RATE_USD

    raw_value = os.getenv(env_key)
    if raw_value is None or raw_value.strip() == "":
        return _DEFAULT_STAGE_RATE_USD

    try:
        parsed_value = float(raw_value)
    except ValueError:
        logger.warning(
            "Invalid {}='{}'; using {}",
            env_key,
            raw_value,
            _DEFAULT_STAGE_RATE_USD,
        )
        return _DEFAULT_STAGE_RATE_USD

    if parsed_value < 0:
        logger.warning(
            "Negative {}={}; using {}",
            env_key,
            parsed_value,
            _DEFAULT_STAGE_RATE_USD,
        )
        return _DEFAULT_STAGE_RATE_USD

    return parsed_value


async def record_stage_cost_event(
    *,
    db: DatabaseManager,
    stage: str,
    job_hash: str | None,
    run_id: str | None,
    metadata: Mapping[str, Any] | None = None,
) -> None:
    """Record one forward-only cost event for a pipeline stage execution.

    Purpose:
        Persist stage telemetry consistently across workers so cost dashboards
        can report spend by day and by stage.
    Args:
        db: Connected database manager used for persistence.
        stage: Pipeline stage label (for example, `GATE` or `TAILOR`).
        job_hash: Optional stable job identifier associated with this run.
        run_id: Optional stage-run identifier.
        metadata: Optional mapping with contextual fields such as model/provider.
    Output:
        Returns `None` after writing the cost event.
    """

    cost_usd = _coerce_stage_rate_usd(stage)
    metadata_json: str | None = None
    if metadata is not None:
        metadata_json = json.dumps(dict(metadata), ensure_ascii=True, sort_keys=True)

    await db.record_cost_event(
        stage=stage,
        cost_usd=cost_usd,
        job_hash=job_hash,
        run_id=run_id,
        metadata_json=metadata_json,
    )


async def check_budget_before_claim(*, db: DatabaseManager, stage: str) -> bool:
    """Check budget exhaustion before claiming additional stage work.

    Purpose:
        Enforce the "finish current step, block new step claims" rule by
        allowing workers to skip claim operations when budget is exhausted.
    Args:
        db: Connected database manager used to read budget state.
        stage: Pipeline stage label emitting the claim guard log line.
    Output:
        Returns `True` when workers may continue claiming, else `False`.
    """

    is_exceeded = await db.is_budget_exceeded()
    if is_exceeded:
        logger.warning(
            "Budget exceeded; pausing new {} claims until budget is increased",
            stage,
        )
        return False
    return True
