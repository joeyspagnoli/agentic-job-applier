"""Tests for the Bug E planner-rationale artifact.

Covers three concerns:

* The pure ``_build_planner_artifact_payload`` helper returns the
  rationale-first payload shape we persist to disk.
* ``_write_planner_artifact`` writes that payload as
  ``tailored_v1.plan.json`` next to the compiled tailored artifacts and
  produces parseable JSON.
* ``record_tailor_success`` persists the path under the new
  ``tailor_runs.plan_json_path`` column.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, cast

from src.agents.resume_tailor.pipeline import (
    PLAN_JSON_BASENAME,
    _build_planner_artifact_payload,
    _write_planner_artifact,
)
from src.agents.resume_tailor.pipeline_schemas import (
    BulletPatchProposal,
    SkippedBulletNote,
    TailorOutput,
)
from src.database.db_manager import DatabaseManager


def _build_sample_tailor_output() -> TailorOutput:
    """Build a deterministic TailorOutput stand-in for the helpers."""

    return TailorOutput(
        rewrite_plan="Targeting bullets b1 and b2 for keyword fit.",
        bullets=[
            BulletPatchProposal(
                id="b1",
                rationale="Tighten verb to match JD vocabulary.",
                action="rewrite",
                new_text="Classified anomalous traffic with 99.2% precision.",
            ),
            BulletPatchProposal(
                id="b2",
                rationale="Original already matches the JD; keep verbatim.",
                action="keep",
                new_text="",
            ),
        ],
        skipped_bullets=[
            SkippedBulletNote(
                id="b3",
                reason="Outside the section the JD emphasizes.",
            )
        ],
    )


def test_build_planner_artifact_payload_returns_rationale_first_shape() -> None:
    """The payload captures every field the dashboard renders."""

    payload = _build_planner_artifact_payload(
        tailor_output=_build_sample_tailor_output(),
        model="openai/gpt-5.4",
        bullets_applied=1,
        bullets_dropped=[
            BulletPatchProposal(
                id="b_unknown",
                rationale="Manifest did not surface this bullet.",
                action="rewrite",
                new_text="(unused)",
            )
        ],
    )

    assert payload["model"] == "openai/gpt-5.4"
    assert isinstance(payload["saved_at"], str) and payload["saved_at"]
    rewrite_plan = cast(str, payload["rewrite_plan"])
    assert rewrite_plan.startswith("Targeting bullets")
    assert payload["bullets_applied"] == 1
    assert payload["bullets_dropped"] == [
        {"id": "b_unknown", "rationale": "Manifest did not surface this bullet."}
    ]
    bullets = cast(list[dict[str, Any]], payload["bullets"])
    assert [bullet["id"] for bullet in bullets] == ["b1", "b2"]
    assert cast(str, bullets[0]["rationale"]).startswith("Tighten verb")
    assert payload["kept_unchanged"] == [
        {"id": "b3", "reason": "Outside the section the JD emphasizes."}
    ]


def test_write_planner_artifact_persists_parseable_json(tmp_path: Path) -> None:
    """The artifact lands at ``tailored_v1.plan.json`` and round-trips."""

    payload = _build_planner_artifact_payload(
        tailor_output=_build_sample_tailor_output(),
        model="openai/gpt-5.4",
        bullets_applied=1,
        bullets_dropped=[],
    )

    plan_path = _write_planner_artifact(variant_dir=tmp_path, payload=payload)

    assert plan_path == tmp_path / PLAN_JSON_BASENAME
    assert plan_path.exists()
    parsed = json.loads(plan_path.read_text(encoding="utf-8"))
    assert parsed["model"] == "openai/gpt-5.4"
    assert parsed["bullets"][0]["new_text"].startswith("Classified anomalous")


def test_record_tailor_success_persists_plan_json_path(tmp_path: Path) -> None:
    """The database column is populated when the helper passes a path."""

    async def _run() -> tuple[str | None, dict[str, Any]]:
        db_path = tmp_path / "jobs.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            await db.migrate_tailor_schema()

            assert db.conn is not None
            await db.conn.execute(
                """
                INSERT INTO tailor_runs (job_hash, status, started_at)
                VALUES ('hash-1', 'RUNNING', CURRENT_TIMESTAMP)
                """
            )
            cursor = await db.conn.execute("SELECT last_insert_rowid() AS id")
            row = await cursor.fetchone()
            assert row is not None
            run_id = int(row["id"])
            await db.conn.commit()

            await db.record_tailor_success(
                run_id=run_id,
                artifact_yaml_path="",
                artifact_tex_path="/tmp/tailored.tex",
                artifact_pdf_path="/tmp/tailored.pdf",
                page_count=1,
                plan_json_path="/tmp/tailored_v1.plan.json",
            )

            row_final = await db.get_tailor_run(run_id)
            if row_final is None:
                return None, {}
            plan_path_val = cast(
                "str | None", row_final.get("plan_json_path")
            )
            return plan_path_val, cast(dict[str, Any], row_final)

    plan_path, row_final = asyncio.run(_run())
    assert plan_path == "/tmp/tailored_v1.plan.json"
    assert row_final["status"] == "SUCCESS"


def test_record_tailor_success_without_plan_path_leaves_column_null(
    tmp_path: Path,
) -> None:
    """Legacy callers that omit ``plan_json_path`` land NULL in the column,
    so the dashboard correctly hides the "Why these edits" affordance.
    """

    async def _run() -> str | None:
        db_path = tmp_path / "jobs.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            await db.migrate_tailor_schema()

            assert db.conn is not None
            await db.conn.execute(
                """
                INSERT INTO tailor_runs (job_hash, status, started_at)
                VALUES ('hash-2', 'RUNNING', CURRENT_TIMESTAMP)
                """
            )
            cursor = await db.conn.execute("SELECT last_insert_rowid() AS id")
            row = await cursor.fetchone()
            assert row is not None
            run_id = int(row["id"])
            await db.conn.commit()

            await db.record_tailor_success(
                run_id=run_id,
                artifact_yaml_path="",
                artifact_tex_path="/tmp/tailored.tex",
                artifact_pdf_path="/tmp/tailored.pdf",
                page_count=1,
            )

            row_final = await db.get_tailor_run(run_id)
            if row_final is None:
                return None
            return cast("str | None", row_final.get("plan_json_path"))

    assert asyncio.run(_run()) is None
