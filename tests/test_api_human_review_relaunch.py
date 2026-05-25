"""Contract tests for ``POST /api/human-review/{id}/relaunch-apply`` (Bug G).

The endpoint mirrors the tailor-side "Delete & retry" affordance: insert
a fresh PENDING ``apply_runs`` row for the handoff's job, mark the old
handoff APPROVED with a Relaunch note, and kick off the user-triggered
apply task immediately. Tests pin four contract requirements:

* Happy path inserts a new PENDING apply_run + claim_token, transitions
  the handoff to APPROVED, and spawns the background task.
* Already-resolved handoffs 409 with ``HANDOFF_ALREADY_RESOLVED``.
* Missing handoff ids 404 with ``HANDOFF_NOT_FOUND``.
* Handoffs whose original apply_run has been soft-deleted 404 with
  ``APPLY_RUN_DELETED`` rather than 500.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import main as api_main
from src.database.db_manager import DatabaseManager
from src.models.job_posting import JobPosting


async def _seed_handoff_with_job(db_path: Path) -> tuple[int, int, str]:
    """Seed a PENDING_REVIEW handoff and return ``(handoff_id, apply_run_id, job_hash)``."""

    async with DatabaseManager(str(db_path)) as db:
        await db.create_tables()
        await db.migrate_apply_schema()

        job = JobPosting(
            source="greenhouse_test",
            source_url="https://example.com/jobs/relaunch",
            company="Cloudflare",
            title="ML Engineer Intern",
            description="A test posting.",
        )
        job_hash = job.job_hash
        await db.insert_job(job.to_db_dict())

        assert db.conn is not None
        await db.conn.execute(
            """
            INSERT INTO tailor_runs (job_hash, status, started_at,
                artifact_tex_path, artifact_pdf_path)
            VALUES (?, 'SUCCESS', CURRENT_TIMESTAMP,
                '/tmp/tailored.tex', '/tmp/tailored.pdf')
            """,
            (job_hash,),
        )
        tailor_cursor = await db.conn.execute("SELECT last_insert_rowid() AS id")
        tailor_row = await tailor_cursor.fetchone()
        assert tailor_row is not None
        tailor_run_id = int(tailor_row["id"])

        await db.conn.execute(
            """
            INSERT INTO review_runs (
                job_hash, tailor_run_id, status, verdict, started_at,
                selected_tex_path, selected_pdf_path,
                fallback_base_tex_path, fallback_base_pdf_path
            )
            VALUES (?, ?, 'SUCCESS', 'TAILORED', CURRENT_TIMESTAMP,
                '/tmp/tailored.tex', '/tmp/tailored.pdf',
                '/tmp/base.tex', '/tmp/base.pdf')
            """,
            (job_hash, tailor_run_id),
        )
        review_cursor = await db.conn.execute("SELECT last_insert_rowid() AS id")
        review_row = await review_cursor.fetchone()
        assert review_row is not None
        review_run_id = int(review_row["id"])

        await db.conn.execute(
            """
            INSERT INTO apply_runs (
                job_hash, review_run_id, status, claim_token, started_at,
                outcome
            )
            VALUES (?, ?, 'SUCCESS', 'tok-1', CURRENT_TIMESTAMP, 'NEEDS_REVIEW')
            """,
            (job_hash, review_run_id),
        )
        apply_cursor = await db.conn.execute("SELECT last_insert_rowid() AS id")
        apply_row = await apply_cursor.fetchone()
        assert apply_row is not None
        apply_run_id = int(apply_row["id"])
        await db.conn.commit()

        await db.record_apply_handoff(
            apply_run_id=apply_run_id,
            job_hash=job_hash,
            review_run_id=review_run_id,
            apply_outcome="NEEDS_REVIEW",
            resume_source="TAILORED",
            resume_pdf_path="/tmp/tailored.pdf",
            confidence_score=0.42,
            confidence_report_json=None,
            unresolved_fields_json=None,
            screenshot_path=None,
            dom_snapshot_path=None,
            ats_platform="greenhouse",
            page_url="https://example.com",
            deferred_questions_json=None,
            finisher_diagnostics_json=None,
        )

        handoff_cursor = await db.conn.execute(
            "SELECT id FROM apply_handoffs WHERE apply_run_id = ?",
            (apply_run_id,),
        )
        handoff_row = await handoff_cursor.fetchone()
        assert handoff_row is not None
        return int(handoff_row["id"]), apply_run_id, job_hash


@pytest.fixture
def relaunch_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TestClient, Path]:
    """Build an isolated TestClient + redirect background task spawn.

    The relaunch endpoint kicks off a real ``_spawn_user_apply_task``
    which would attempt CDP connections; replace it with a no-op
    coroutine so the API contract tests stay hermetic.
    """

    db_path = tmp_path / "jobs.db"
    monkeypatch.setattr(api_main, "resolve_database_path", lambda: db_path)

    from api.routers import apply_runs as _apply_runs  # noqa: PLC0415

    async def _noop_spawn(*, db_path: str, merged_row: Mapping[str, object]) -> None:
        """No-op stand-in capturing the call without touching Chrome."""

        _captured_spawn_calls.append({"db_path": db_path, "merged_row": dict(merged_row)})

    _captured_spawn_calls.clear()
    monkeypatch.setattr(_apply_runs, "_spawn_user_apply_task", _noop_spawn)

    return TestClient(api_main.app), db_path


_captured_spawn_calls: list[dict[str, object]] = []


def test_relaunch_apply_inserts_pending_run_and_resolves_old_handoff(
    relaunch_client: tuple[TestClient, Path],
) -> None:
    """Happy path: new apply_run row + handoff transitions to APPROVED."""

    client, db_path = relaunch_client
    handoff_id, old_apply_run_id, job_hash = asyncio.run(
        _seed_handoff_with_job(db_path)
    )

    response = client.post(f"/api/human-review/{handoff_id}/relaunch-apply")
    assert response.status_code == 200, response.text
    body = response.json()
    new_run_id = int(body["apply_run_id"])
    assert new_run_id != old_apply_run_id
    assert body["status"] == "PENDING"
    assert body["job_hash"] == job_hash

    async def _verify_db_state() -> None:
        async with DatabaseManager(str(db_path)) as db:
            new_run = await db.get_apply_run(new_run_id)
            assert new_run is not None
            assert str(new_run["status"]) == "PENDING"
            assert str(new_run["claim_token"] or "") != ""

            assert db.conn is not None
            cursor = await db.conn.execute(
                "SELECT handoff_status, reviewer_notes FROM apply_handoffs WHERE id = ?",
                (handoff_id,),
            )
            row = await cursor.fetchone()
            assert row is not None
            assert str(row["handoff_status"]) == "APPROVED"
            assert "Relaunched" in str(row["reviewer_notes"])

    asyncio.run(_verify_db_state())

    # The background task was scheduled with the freshly enqueued row.
    assert len(_captured_spawn_calls) == 1
    spawned = _captured_spawn_calls[0]["merged_row"]
    assert isinstance(spawned, dict)
    assert int(spawned["_apply_run_id"]) == new_run_id


def test_relaunch_apply_returns_409_for_resolved_handoff(
    relaunch_client: tuple[TestClient, Path],
) -> None:
    """Already-APPROVED handoffs cannot be relaunched a second time."""

    client, db_path = relaunch_client
    handoff_id, _apply_run_id, _job_hash = asyncio.run(
        _seed_handoff_with_job(db_path)
    )

    # First relaunch succeeds and flips the handoff to APPROVED.
    first = client.post(f"/api/human-review/{handoff_id}/relaunch-apply")
    assert first.status_code == 200

    # Second relaunch on the same handoff must 409.
    second = client.post(f"/api/human-review/{handoff_id}/relaunch-apply")
    assert second.status_code == 409
    assert second.json()["code"] == "HANDOFF_ALREADY_RESOLVED"


def test_relaunch_apply_returns_404_for_missing_handoff(
    relaunch_client: tuple[TestClient, Path],
) -> None:
    """Unknown handoff ids 404 cleanly."""

    client, db_path = relaunch_client

    async def _init() -> None:
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            await db.migrate_apply_schema()

    asyncio.run(_init())

    response = client.post("/api/human-review/9999/relaunch-apply")
    assert response.status_code == 404
    assert response.json()["code"] == "HANDOFF_NOT_FOUND"


def test_relaunch_apply_returns_404_when_original_apply_run_deleted(
    relaunch_client: tuple[TestClient, Path],
) -> None:
    """Orphaned handoffs (apply_run soft-deleted) 404 instead of 500."""

    client, db_path = relaunch_client
    handoff_id, apply_run_id, _job_hash = asyncio.run(
        _seed_handoff_with_job(db_path)
    )

    async def _soft_delete_apply() -> None:
        async with DatabaseManager(str(db_path)) as db:
            await db.soft_delete_apply_run(apply_run_id)

    asyncio.run(_soft_delete_apply())

    response = client.post(f"/api/human-review/{handoff_id}/relaunch-apply")
    assert response.status_code == 404
    assert response.json()["code"] == "APPLY_RUN_DELETED"
