"""Contract tests for the human-review answers endpoint and queue shape.

Covers Bug B fixes:

* ``GET /api/human-review`` prefers the finisher's
  ``deferred_questions_json`` over the older ``unresolved_fields_json``
  when both are present, so reviewers see the human-readable labels
  the finisher captured (e.g. ``"Gender"``) instead of the legacy
  ``"Unresolved field"`` placeholder.
* The legacy fallback never surfaces ``"Unresolved field"``; it now
  degrades to the ``field_id`` and finally to ``"(no label)"``.
* ``POST /api/human-review/{id}/answers`` persists the reviewer-typed
  payload to ``apply_handoffs.user_answers_json`` and a subsequent
  GET returns it on the row.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import main as api_main
from src.database.db_manager import DatabaseManager
from src.models.job_posting import JobPosting


async def _seed_one_handoff(
    db_path: Path,
    *,
    deferred_questions_json: str | None,
    unresolved_fields_json: str | None,
) -> int:
    """Seed one job + review + apply + handoff row; return the handoff id.

    Purpose:
        Build a deterministic fixture row the API test can read back.
        Inserts directly via SQL where possible to avoid pulling in
        the full apply-runner stack.
    Args:
        db_path: Temp SQLite database path.
        deferred_questions_json: Pre-serialized JSON for the
            finisher-deferred questions column.
        unresolved_fields_json: Pre-serialized JSON for the legacy
            unresolved-fields column.
    Returns:
        Primary key of the inserted ``apply_handoffs`` row.
    """

    async with DatabaseManager(str(db_path)) as db:
        await db.create_tables()
        await db.migrate_apply_schema()

        job = JobPosting(
            source="greenhouse_test",
            source_url="https://example.com/jobs/test",
            company="Cloudflare",
            title="ML Engineer Intern",
            description="A test posting.",
        )
        job_hash = job.job_hash
        await db.insert_job(job.to_db_dict())

        assert db.conn is not None
        conn = db.conn
        # Seed a tailor_run + review_runs + apply_runs chain so the
        # NOT NULL constraints (review_runs.tailor_run_id,
        # apply_runs.review_run_id) are satisfied.
        await conn.execute(
            """
            INSERT INTO tailor_runs (job_hash, status, started_at)
            VALUES (?, 'SUCCESS', CURRENT_TIMESTAMP)
            """,
            (job_hash,),
        )
        tailor_cursor = await conn.execute("SELECT last_insert_rowid() AS id")
        tailor_row = await tailor_cursor.fetchone()
        assert tailor_row is not None
        tailor_run_id = int(tailor_row["id"])

        await conn.execute(
            """
            INSERT INTO review_runs (job_hash, tailor_run_id, status, verdict, started_at)
            VALUES (?, ?, 'SUCCESS', 'TAILORED', CURRENT_TIMESTAMP)
            """,
            (job_hash, tailor_run_id),
        )
        review_cursor = await conn.execute(
            "SELECT last_insert_rowid() AS id"
        )
        review_row = await review_cursor.fetchone()
        assert review_row is not None
        review_run_id = int(review_row["id"])

        await conn.execute(
            """
            INSERT INTO apply_runs (job_hash, review_run_id, status, claim_token, started_at)
            VALUES (?, ?, 'SUCCESS', 'tok', CURRENT_TIMESTAMP)
            """,
            (job_hash, review_run_id),
        )
        apply_cursor = await conn.execute("SELECT last_insert_rowid() AS id")
        apply_row = await apply_cursor.fetchone()
        assert apply_row is not None
        apply_run_id = int(apply_row["id"])
        await conn.commit()

        await db.record_apply_handoff(
            apply_run_id=apply_run_id,
            job_hash=job_hash,
            review_run_id=review_run_id,
            apply_outcome="NEEDS_REVIEW",
            resume_source="TAILORED",
            resume_pdf_path="/tmp/resume.pdf",
            confidence_score=0.42,
            confidence_report_json=None,
            unresolved_fields_json=unresolved_fields_json,
            screenshot_path=None,
            dom_snapshot_path=None,
            ats_platform="greenhouse",
            page_url="https://example.com",
            deferred_questions_json=deferred_questions_json,
            finisher_diagnostics_json=None,
        )

        cursor = await db.conn.execute(
            "SELECT id FROM apply_handoffs WHERE apply_run_id = ?",
            (apply_run_id,),
        )
        row = await cursor.fetchone()
        assert row is not None
        return int(row["id"])


@pytest.fixture
def human_review_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TestClient, Path]:
    """Build an isolated TestClient pointed at a fresh temp SQLite file.

    Returns:
        Tuple of (client, database_path). Tests seed the database via
        the path before issuing HTTP requests.
    """

    db_path = tmp_path / "jobs.db"
    monkeypatch.setattr(api_main, "resolve_database_path", lambda: db_path)
    return TestClient(api_main.app), db_path


def test_get_human_review_prefers_deferred_questions_over_unresolved_fields(
    human_review_client: tuple[TestClient, Path],
) -> None:
    """When both JSON blobs are populated, the API surfaces the finisher's
    deferred questions (which carry real labels) and ignores the legacy
    placeholder list (which carries only nulls).
    """

    client, db_path = human_review_client

    deferred = json.dumps(
        [
            {
                "field_id": "e368",
                "label": "Gender",
                "field_type": "combobox",
                "category": "eeo",
                "reason": "EEO field; Tier 3.",
            }
        ]
    )
    legacy = json.dumps([{"field_id": None, "label": None}])

    asyncio.run(
        _seed_one_handoff(
            db_path,
            deferred_questions_json=deferred,
            unresolved_fields_json=legacy,
        )
    )

    response = client.get("/api/human-review", params={"page_size": 50})
    assert response.status_code == 200

    payload = response.json()
    assert payload["ok"] is True
    assert payload["total_items"] == 1
    item = payload["items"][0]

    fields = item["unresolved_fields"]
    assert len(fields) == 1
    assert fields[0]["field_id"] == "e368"
    assert fields[0]["field_name"] == "Gender"
    assert fields[0]["reasoning"] == "EEO field; Tier 3."
    # The reviewer must never see the prior placeholder text.
    assert all(field["field_name"] != "Unresolved field" for field in fields)


def test_get_human_review_falls_back_to_field_id_when_label_missing(
    human_review_client: tuple[TestClient, Path],
) -> None:
    """Legacy rows lacking a label degrade to field_id, not the literal
    ``"Unresolved field"`` placeholder.
    """

    client, db_path = human_review_client

    legacy_only = json.dumps([{"field_id": "fallback_id_42"}])

    asyncio.run(
        _seed_one_handoff(
            db_path,
            deferred_questions_json=None,
            unresolved_fields_json=legacy_only,
        )
    )

    response = client.get("/api/human-review", params={"page_size": 50})
    assert response.status_code == 200
    item = response.json()["items"][0]
    fields = item["unresolved_fields"]
    assert fields[0]["field_name"] == "fallback_id_42"
    assert "Unresolved field" not in [field["field_name"] for field in fields]


def test_post_answers_persists_and_subsequent_get_returns_them(
    human_review_client: tuple[TestClient, Path],
) -> None:
    """POST writes user_answers_json; GET surfaces the round-tripped list."""

    client, db_path = human_review_client

    deferred = json.dumps(
        [
            {"field_id": "e368", "label": "Gender", "field_type": "combobox",
             "category": "eeo", "reason": "EEO."},
            {"field_id": "e385", "label": "Hispanic/Latino?",
             "field_type": "combobox", "category": "eeo", "reason": "EEO."},
        ]
    )
    handoff_id = asyncio.run(
        _seed_one_handoff(
            db_path,
            deferred_questions_json=deferred,
            unresolved_fields_json=None,
        )
    )

    save = client.post(
        f"/api/human-review/{handoff_id}/answers",
        json={
            "answers": [
                {"field_id": "e368", "answer": "Female"},
                {"field_id": "e385", "answer": "No"},
            ]
        },
    )
    assert save.status_code == 200, save.text
    assert save.json()["ok"] is True
    assert save.json()["user_answers"] == [
        {"field_id": "e368", "answer": "Female"},
        {"field_id": "e385", "answer": "No"},
    ]

    queue = client.get("/api/human-review", params={"page_size": 50})
    assert queue.status_code == 200
    item = queue.json()["items"][0]
    assert item["user_answers"] == [
        {"field_id": "e368", "answer": "Female"},
        {"field_id": "e385", "answer": "No"},
    ]


def test_post_answers_returns_404_for_missing_handoff(
    human_review_client: tuple[TestClient, Path],
) -> None:
    """Posting answers to a non-existent handoff yields a 404."""

    client, db_path = human_review_client

    # Initialize an empty database so the apply_handoffs table exists.
    async def _init() -> None:
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            await db.migrate_apply_schema()

    asyncio.run(_init())

    response = client.post(
        "/api/human-review/9999/answers",
        json={"answers": [{"field_id": "x", "answer": "y"}]},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "HANDOFF_NOT_FOUND"


def test_post_answers_overwrites_prior_payload(
    human_review_client: tuple[TestClient, Path],
) -> None:
    """A second POST replaces the first; the GET reflects only the latest."""

    client, db_path = human_review_client

    deferred = json.dumps(
        [{"field_id": "e1", "label": "Q1", "field_type": "text",
          "category": "other", "reason": "n/a"}]
    )
    handoff_id = asyncio.run(
        _seed_one_handoff(
            db_path,
            deferred_questions_json=deferred,
            unresolved_fields_json=None,
        )
    )

    client.post(
        f"/api/human-review/{handoff_id}/answers",
        json={"answers": [{"field_id": "e1", "answer": "first"}]},
    )
    client.post(
        f"/api/human-review/{handoff_id}/answers",
        json={"answers": [{"field_id": "e1", "answer": "second"}]},
    )

    item = client.get("/api/human-review").json()["items"][0]
    assert item["user_answers"] == [{"field_id": "e1", "answer": "second"}]
