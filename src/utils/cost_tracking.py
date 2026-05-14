"""Record configurable pipeline cost events for dashboard analytics.

This module centralizes environment-driven stage rates so each worker can
emit consistent cost telemetry without duplicating parsing logic. Stages
that emit token counts in their cost-event metadata (tailor, review)
opt into a more precise per-model rate computed from
`COST_RATE_<MODEL>_IN_USD` / `_OUT_USD` env vars; stages without that
data (apply browser ops) keep the flat env-rate path.
"""

from __future__ import annotations

import json
import os
import re
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

_TOKENS_PER_RATE_UNIT = 1000.0

_MODEL_NAME_SANITIZE_PATTERN = re.compile(r"[/.\-]")

_WARNED_UNKNOWN_MODELS: set[str] = set()


def _env_var_names_for_model(model: str) -> tuple[str, str]:
    """Return the `(input_rate_env, output_rate_env)` names for one model.

    Purpose:
        Derive the two env-var names operators set when they want a
        precise per-model rate. Replaces `/`, `.`, and `-` with `_` and
        uppercases the result so identifiers stay shell-friendly.
    Args:
        model: Fully qualified `provider/model` string.
    Output:
        Returns `(in_env_name, out_env_name)`.
    """

    sanitized = _MODEL_NAME_SANITIZE_PATTERN.sub("_", model).upper()
    return f"COST_RATE_{sanitized}_IN_USD", f"COST_RATE_{sanitized}_OUT_USD"


def _parse_rate_env(env_name: str) -> float | None:
    """Read one rate env var, returning `None` when unparseable or negative.

    Purpose:
        Centralize parsing so both the model and stage rate paths reject
        malformed values consistently.
    Args:
        env_name: Name of the env var to read.
    Output:
        Returns the parsed non-negative `float`, or `None` when unset or
        invalid.
    """

    raw_value = os.getenv(env_name)
    if raw_value is None or raw_value.strip() == "":
        return None
    try:
        parsed_value = float(raw_value)
    except ValueError:
        return None
    if parsed_value < 0:
        return None
    return parsed_value


def _token_cost_from_metadata(metadata: Mapping[str, Any]) -> float | None:
    """Compute USD cost from token-usage metadata when rates are configured.

    Purpose:
        Replace the flat env-rate per stage with model-aware token-based
        pricing for stages whose metadata carries `model`,
        `prompt_tokens`, and `completion_tokens`. Stages without that
        shape (apply browser ops) fall through to the stage rate.
    Args:
        metadata: Cost-event metadata dict. Expected keys: `model` (str),
            `prompt_tokens` (int), `completion_tokens` (int).
    Output:
        Returns the computed USD cost (may be `0.0` for known model +
        zero tokens), or `None` when the model is unknown, the tokens
        are missing/malformed, or the env vars are not set.
    """

    model = metadata.get("model")
    prompt_raw = metadata.get("prompt_tokens")
    completion_raw = metadata.get("completion_tokens")

    if not isinstance(model, str) or model.strip() == "":
        return None
    if not isinstance(prompt_raw, int) or isinstance(prompt_raw, bool):
        return None
    if not isinstance(completion_raw, int) or isinstance(completion_raw, bool):
        return None
    if prompt_raw < 0 or completion_raw < 0:
        return None

    in_env, out_env = _env_var_names_for_model(model)
    in_rate = _parse_rate_env(in_env)
    out_rate = _parse_rate_env(out_env)
    if in_rate is None or out_rate is None:
        if model not in _WARNED_UNKNOWN_MODELS:
            _WARNED_UNKNOWN_MODELS.add(model)
            logger.warning(
                "cost_tracking: no token rate configured for model '{}' "
                "(checked {} / {}); falling back to stage rate",
                model,
                in_env,
                out_env,
            )
        return None

    return (
        (prompt_raw / _TOKENS_PER_RATE_UNIT) * in_rate
        + (completion_raw / _TOKENS_PER_RATE_UNIT) * out_rate
    )


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

    token_cost: float | None = None
    if metadata is not None:
        token_cost = _token_cost_from_metadata(metadata)
    cost_usd = token_cost if token_cost is not None else _coerce_stage_rate_usd(stage)

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
