"""Contract tests for ``GET /api/tailor-runs/{id}/plan`` (Bug E).

The dashboard's "Why these edits" panel calls this endpoint and renders
the JSON verbatim. The tests pin three contract requirements:

* SUCCESS rows with a populated ``plan_json_path`` return the file's
  JSON contents under a ``plan`` key.
* Rows that lack a recorded path 404 with
  ``code="TAILOR_PLAN_NOT_AVAILABLE"`` so the frontend can hide the
  panel without speculating about ATS-specific failure modes.
* Rows whose recorded path is missing on disk 404 with
  ``code="TAILOR_PLAN_FILE_MISSING"`` so artifact-cleanup races are
  diagnosable without the frontend looking at logs.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import main as api_main
from src.database.db_manager import DatabaseManager


async def _seed_tailor_run(
    db_path: Path,
    *,
    plan_json_path: str | None,
) -> int:
    """Seed one SUCCESS tailor_runs row and return its primary key."""

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
            plan_json_path=plan_json_path,
        )
        return run_id


@pytest.fixture
def tailor_plan_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TestClient, Path]:
    """Build a TestClient with the DB path redirected to a fresh temp file."""

    db_path = tmp_path / "jobs.db"
    monkeypatch.setattr(api_main, "resolve_database_path", lambda: db_path)
    return TestClient(api_main.app), db_path


def test_returns_planner_json_when_artifact_exists(
    tailor_plan_client: tuple[TestClient, Path],
    tmp_path: Path,
) -> None:
    """A successful run with a written artifact streams it back as JSON."""

    client, db_path = tailor_plan_client

    plan_file = tmp_path / "tailored_v1.plan.json"
    plan_payload = {
        "model": "openai/gpt-5.4",
        "rewrite_plan": "Targeted bullets b1 and b2.",
        "bullets": [
            {
                "id": "b1",
                "rationale": "Verb swap to mirror the JD.",
                "action": "rewrite",
                "new_text": "Classified anomalous traffic with 99.2% precision.",
            }
        ],
        "kept_unchanged": [],
    }
    plan_file.write_text(json.dumps(plan_payload), encoding="utf-8")

    run_id = asyncio.run(
        _seed_tailor_run(db_path, plan_json_path=str(plan_file))
    )

    response = client.get(f"/api/tailor-runs/{run_id}/plan")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["plan"] == plan_payload


def test_returns_404_when_plan_path_not_recorded(
    tailor_plan_client: tuple[TestClient, Path],
) -> None:
    """Runs predating Bug E (no plan path recorded) cleanly 404."""

    client, db_path = tailor_plan_client
    run_id = asyncio.run(_seed_tailor_run(db_path, plan_json_path=None))

    response = client.get(f"/api/tailor-runs/{run_id}/plan")
    assert response.status_code == 404
    assert response.json()["code"] == "TAILOR_PLAN_NOT_AVAILABLE"


def test_returns_404_when_plan_file_missing_on_disk(
    tailor_plan_client: tuple[TestClient, Path],
    tmp_path: Path,
) -> None:
    """If the recorded path no longer exists on disk we surface a
    distinct error code so artifact-cleanup races are debuggable.
    """

    client, db_path = tailor_plan_client
    ghost_path = tmp_path / "deleted" / "tailored_v1.plan.json"
    run_id = asyncio.run(
        _seed_tailor_run(db_path, plan_json_path=str(ghost_path))
    )

    response = client.get(f"/api/tailor-runs/{run_id}/plan")
    assert response.status_code == 404
    assert response.json()["code"] == "TAILOR_PLAN_FILE_MISSING"


def test_returns_404_for_unknown_run_id(
    tailor_plan_client: tuple[TestClient, Path],
) -> None:
    """Unknown run ids 404 with the same code the existing GET uses."""

    client, db_path = tailor_plan_client

    # Initialize the schema so the tailor_runs SELECT does not crash.
    async def _init() -> None:
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            await db.migrate_tailor_schema()

    asyncio.run(_init())

    response = client.get("/api/tailor-runs/99999/plan")
    assert response.status_code == 404
    assert response.json()["code"] == "TAILOR_RUN_NOT_FOUND"
