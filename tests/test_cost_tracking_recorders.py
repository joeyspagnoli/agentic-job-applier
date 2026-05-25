"""Tests for the cost-tracking recorders and budget guard.

Covers the three public recorders in :mod:`src.utils.cost_tracking`:

* ``record_llm_call_cost`` persists every provider/model/token column.
* ``record_apply_browser_stub`` writes a zero-cost ``cost_source='internal'``
  row tagged with ``model='browser_ops'``.
* ``check_budget_before_claim`` returns ``False`` when the budget is
  exhausted.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.database.db_manager import DatabaseManager
from src.providers.types import (
    CompletionResponse,
    CostBreakdown,
    TokenUsage,
)
from src.utils.cost_tracking import (
    PIPELINE_STAGE_APPLY,
    PIPELINE_STAGE_TAILOR,
    check_budget_before_claim,
    record_apply_browser_stub,
    record_llm_call_cost,
)


# ---------------------------------------------------------------------------
# record_llm_call_cost
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_llm_call_cost_persists_every_column(tmp_path: Path) -> None:
    """All provider / model / token columns land in the DB row."""

    db_path = tmp_path / "cost.db"
    async with DatabaseManager(str(db_path)) as db:
        await db.create_tables()
        await db.migrate_cost_schema()

        response = CompletionResponse(
            content="hi",
            model="gpt-5.4-mini",
            provider="openai",
            usage=TokenUsage(
                prompt_tokens=320, completion_tokens=80,
                cached_input_tokens=64, reasoning_tokens=12,
            ),
            cost=CostBreakdown(
                input_cost_usd=0.001, output_cost_usd=0.002,
                cached_input_cost_usd=0.0003, total_cost_usd=0.0033,
                source="computed",
            ),
        )

        await record_llm_call_cost(
            db=db,
            stage=PIPELINE_STAGE_TAILOR,
            run_id="42",
            phase="tailor",
            response=response,
            job_hash="abc",
            extra_metadata={"extra_key": "extra_value"},
        )

        conn = db._require_conn()
        row_cursor = await conn.execute(
            "SELECT * FROM cost_events ORDER BY id DESC LIMIT 1"
        )
        row = await row_cursor.fetchone()

    assert row is not None
    assert row["stage"] == PIPELINE_STAGE_TAILOR
    assert row["run_id"] == "42"
    assert row["phase"] == "tailor"
    assert row["job_hash"] == "abc"
    assert row["provider"] == "openai"
    assert row["model"] == "gpt-5.4-mini"
    assert row["prompt_tokens"] == 320
    assert row["completion_tokens"] == 80
    assert row["cached_input_tokens"] == 64
    assert row["reasoning_tokens"] == 12
    assert row["cost_source"] == "computed"
    assert float(row["cost_usd"]) == pytest.approx(0.0033)
    # metadata_json should round-trip through json.dumps; the extra key landed.
    import json

    metadata = json.loads(str(row["metadata_json"]))
    assert metadata["extra_key"] == "extra_value"
    assert metadata["cost_source"] == "computed"


@pytest.mark.asyncio
async def test_record_llm_call_cost_writes_unknown_cost_source(tmp_path: Path) -> None:
    """A response with ``cost.source='unknown'`` lands ``cost_source='unknown'``."""

    db_path = tmp_path / "cost_unknown.db"
    async with DatabaseManager(str(db_path)) as db:
        await db.create_tables()
        await db.migrate_cost_schema()

        response = CompletionResponse(
            content="",
            model="weird-model",
            provider="openai",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=5),
            cost=CostBreakdown(source="unknown"),
        )

        await record_llm_call_cost(
            db=db, stage=PIPELINE_STAGE_TAILOR, run_id="r1", phase="review", response=response,
        )

        conn = db._require_conn()
        cursor = await conn.execute(
            "SELECT cost_source, cost_usd FROM cost_events ORDER BY id DESC LIMIT 1"
        )
        row = await cursor.fetchone()

    assert row is not None
    assert row["cost_source"] == "unknown"
    assert float(row["cost_usd"]) == 0.0


# ---------------------------------------------------------------------------
# record_apply_browser_stub
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_apply_browser_stub_writes_internal_zero_cost_row(tmp_path: Path) -> None:
    """The stub recorder lands one APPLY-stage row with ``cost_source='internal'``."""

    db_path = tmp_path / "stub.db"
    async with DatabaseManager(str(db_path)) as db:
        await db.create_tables()
        await db.migrate_cost_schema()

        await record_apply_browser_stub(
            db=db,
            job_hash="j1",
            run_id="r1",
            metadata={"status": "PENDING", "attempt": 1},
        )

        conn = db._require_conn()
        cursor = await conn.execute(
            "SELECT * FROM cost_events ORDER BY id DESC LIMIT 1"
        )
        row = await cursor.fetchone()

    assert row is not None
    assert row["stage"] == PIPELINE_STAGE_APPLY
    assert float(row["cost_usd"]) == 0.0
    assert row["cost_source"] == "internal"
    assert row["provider"] == "internal"
    assert row["model"] == "browser_ops"
    assert row["prompt_tokens"] == 0
    assert row["completion_tokens"] == 0


# ---------------------------------------------------------------------------
# check_budget_before_claim
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_budget_before_claim_true_when_not_exhausted(tmp_path: Path) -> None:
    """With the default budget and no spend the guard returns True."""

    db_path = tmp_path / "budget_ok.db"
    async with DatabaseManager(str(db_path)) as db:
        await db.create_tables()
        await db.migrate_cost_schema()

        allowed = await check_budget_before_claim(db=db, stage=PIPELINE_STAGE_TAILOR)

    assert allowed is True


@pytest.mark.asyncio
async def test_check_budget_before_claim_false_when_budget_exhausted(tmp_path: Path) -> None:
    """When ``is_budget_exceeded`` reports True the guard returns False."""

    db_path = tmp_path / "budget_low.db"
    async with DatabaseManager(str(db_path)) as db:
        await db.create_tables()
        await db.migrate_cost_schema()

        # Push the budget to zero and record one penny of spend.
        await db.set_budget_settings(monthly_budget_usd=0.0)

        allowed = await check_budget_before_claim(db=db, stage=PIPELINE_STAGE_TAILOR)

    assert allowed is False
