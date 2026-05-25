"""Persist per-LLM-call cost telemetry for dashboard analytics.

The previous env-rate protocol (`COST_RATE_*` per-stage and per-model
env vars) is gone. Providers now compute their own `CostBreakdown`
and the recorder writes it as-is. Stages that do not invoke an LLM
(the apply browser-ops stub) still emit a zero-cost row tagged
`cost_source="internal"` so dashboards keep their per-stage counts.

Public functions:
    record_llm_call_cost(...) — primary write path; persists the
        provider-computed cost alongside model, token, and phase
        metadata.
    record_apply_browser_stub(...) — apply-stage browser-op stub
        that records a "this run happened" event without LLM tokens.
    check_budget_before_claim(...) — claim guard for workers.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from loguru import logger

from src.database.db_manager import DatabaseManager
from src.providers.types import CompletionResponse

PIPELINE_STAGE_GATE = "GATE"
PIPELINE_STAGE_TAILOR = "TAILOR"
PIPELINE_STAGE_REVIEW = "REVIEW"
PIPELINE_STAGE_APPLY = "APPLY"
PIPELINE_STAGE_DISCOVERY = "DISCOVERY"


async def record_llm_call_cost(
    *,
    db: DatabaseManager,
    stage: str,
    run_id: str | None,
    phase: str | None,
    response: CompletionResponse,
    job_hash: str | None = None,
    extra_metadata: Mapping[str, Any] | None = None,
) -> None:
    """Persist one provider-computed LLM-call cost row.

    Purpose:
        Single write path for every billed model call (gate, tailor,
        review, apply finisher). The provider has already computed the
        cost in its own units; the recorder writes it without further
        pricing logic.
    Args:
        db: Connected database manager used for persistence.
        stage: Pipeline stage label (`GATE`, `TAILOR`, `REVIEW`, `APPLY`).
        run_id: Optional stage-run identifier (string form so apply IDs
            and gate hashes can share the column).
        phase: Optional sub-phase name within the stage (e.g. `tailor`,
            `trim`, `reviewer`, `finisher_turn_3`).
        response: Completion response with populated `usage` and `cost`.
        job_hash: Optional stable job identifier.
        extra_metadata: Optional mapping merged into the persisted
            `metadata_json` payload (does not override canonical fields).
    Output:
        Returns `None` after writing the cost event.
    """

    usage = response.usage
    cost = response.cost
    metadata: dict[str, Any] = {
        "provider": response.provider,
        "model": response.model,
        "phase": phase,
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "cached_input_tokens": usage.cached_input_tokens,
        "reasoning_tokens": usage.reasoning_tokens,
        "cost_source": cost.source,
        "input_cost_usd": cost.input_cost_usd,
        "output_cost_usd": cost.output_cost_usd,
        "cached_input_cost_usd": cost.cached_input_cost_usd,
    }
    if extra_metadata:
        for key, value in extra_metadata.items():
            metadata.setdefault(key, value)

    metadata_json = json.dumps(metadata, ensure_ascii=True, sort_keys=True)

    await db.record_cost_event(
        stage=stage,
        cost_usd=cost.total_cost_usd,
        job_hash=job_hash,
        run_id=run_id,
        metadata_json=metadata_json,
        provider=response.provider,
        model=response.model,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        cached_input_tokens=usage.cached_input_tokens,
        reasoning_tokens=usage.reasoning_tokens,
        phase=phase,
        cost_source=cost.source,
    )


async def record_apply_browser_stub(
    *,
    db: DatabaseManager,
    job_hash: str | None,
    run_id: str | None,
    metadata: Mapping[str, Any] | None = None,
) -> None:
    """Record an apply-stage browser-ops event with no LLM cost.

    Purpose:
        Preserve per-stage event counts on the cost dashboard for runs
        whose browser automation did not invoke an LLM. Cost is zero;
        `cost_source` is `internal` so analytics can distinguish stubs
        from genuinely-unpriced model calls.
    Args:
        db: Connected database manager.
        job_hash: Optional stable job identifier.
        run_id: Optional apply-run identifier.
        metadata: Optional context dict (status, outcome, attempt, ...).
    Output:
        Returns `None` after writing the event.
    """

    metadata_payload: dict[str, Any] = {
        "provider": "internal",
        "model": "browser_ops",
        "cost_source": "internal",
    }
    if metadata:
        for key, value in metadata.items():
            metadata_payload.setdefault(key, value)
    metadata_json = json.dumps(metadata_payload, ensure_ascii=True, sort_keys=True)

    await db.record_cost_event(
        stage=PIPELINE_STAGE_APPLY,
        cost_usd=0.0,
        job_hash=job_hash,
        run_id=run_id,
        metadata_json=metadata_json,
        provider="internal",
        model="browser_ops",
        prompt_tokens=0,
        completion_tokens=0,
        cached_input_tokens=0,
        reasoning_tokens=0,
        phase=None,
        cost_source="internal",
    )


async def record_stage_cost_event(
    *,
    db: DatabaseManager,
    stage: str,
    job_hash: str | None,
    run_id: str | None,
    metadata: Mapping[str, Any] | None = None,
) -> None:
    """Record one cost event for a pipeline stage execution.

    Purpose:
        Compatibility shim preserving the pre-refactor call-site contract so
        existing callers (e.g., ``resume_tailor.pipeline``) continue to work
        while Phase G migrates them to ``record_llm_call_cost``.
    Args:
        db: Connected database manager used for persistence.
        stage: Pipeline stage label (e.g. ``GATE`` or ``TAILOR``).
        job_hash: Optional stable job identifier.
        run_id: Optional stage-run identifier.
        metadata: Optional mapping with contextual fields.

    Returns:
        None after writing the cost event.
    """
    metadata_json: str | None = None
    if metadata is not None:
        metadata_json = json.dumps(dict(metadata), ensure_ascii=True, sort_keys=True)

    await db.record_cost_event(
        stage=stage,
        cost_usd=0.0,
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
