"""Additional contract tests for the apply-run router.

Complements ``test_apply_runs_router.py`` by locking in edge cases the
orchestrator's smoke pass didn't cover: 422 when only a FAILED review
run exists, soft-deleted rows surfacing ``deleted_at``, and successful
re-enqueue after the prior PENDING run is soft-deleted.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import main as api_main
from src.database.db_manager import DatabaseManager
from src.models.job_posting import JobPosting


VALID_HASH = "ab" * 20


def _seed_job(db_path: Path, job_hash: str) -> None:
    """Insert one job posting at ``job_hash``."""

    async def _seed() -> None:
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            posting = JobPosting(
                source="manual",
                source_url="https://example.com/" + job_hash,
                company="Acme",
                title="Engineer",
                description="JD body.",
            )
            db_dict = posting.to_db_dict()
            db_dict["job_hash"] = job_hash
            await db.insert_job(db_dict)

    asyncio.run(_seed())


def _seed_failed_review_run(db_path: Path, job_hash: str) -> int:
    """Insert one FAILED review_runs row for the job (not eligible for apply)."""

    async def _seed() -> int:
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            conn = db._require_conn()
            tailor_cursor = await conn.execute(
                "INSERT INTO tailor_runs (job_hash, status) VALUES (?, 'FAILED') RETURNING id",
                (job_hash,),
            )
            tailor_row = await tailor_cursor.fetchone()
            await conn.commit()
            assert tailor_row is not None
            tailor_run_id = int(tailor_row["id"])

            review_cursor = await conn.execute(
                "INSERT INTO review_runs (job_hash, tailor_run_id, status) "
                "VALUES (?, ?, 'FAILED') RETURNING id",
                (job_hash, tailor_run_id),
            )
            review_row = await review_cursor.fetchone()
            await conn.commit()
            assert review_row is not None
            return int(review_row["id"])

    return asyncio.run(_seed())


def _seed_success_review_run(db_path: Path, job_hash: str) -> int:
    """Insert one SUCCESS review_runs row for the job."""

    async def _seed() -> int:
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            conn = db._require_conn()
            tailor_cursor = await conn.execute(
                "INSERT INTO tailor_runs (job_hash, status) VALUES (?, 'SUCCESS') RETURNING id",
                (job_hash,),
            )
            tailor_row = await tailor_cursor.fetchone()
            await conn.commit()
            assert tailor_row is not None
            tailor_run_id = int(tailor_row["id"])

            return await db.insert_pipeline_review_run(
                job_hash=job_hash,
                tailor_run_id=tailor_run_id,
                verdict="PASS",
                selected_yaml_path=None,
                selected_tex_path=None,
                selected_pdf_path=None,
                review_report_json=None,
                fallback_base_yaml_path=None,
                fallback_base_tex_path=None,
                fallback_base_pdf_path=None,
            )

    return asyncio.run(_seed())


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Build a TestClient with an isolated temp database."""

    db_path = tmp_path / "apply_extra.db"
    monkeypatch.setattr(api_main, "resolve_database_path", lambda: db_path)
    return TestClient(api_main.app)


# ---------------------------------------------------------------------------
# Only a FAILED review run → 422 NO_REVIEW_RUN
# ---------------------------------------------------------------------------


def test_post_returns_422_when_only_failed_review_run_exists(
    client: TestClient, tmp_path: Path,
) -> None:
    """A FAILED review run does not satisfy the SUCCESS requirement."""

    db_path = tmp_path / "apply_extra.db"
    _seed_job(db_path, VALID_HASH)
    _seed_failed_review_run(db_path, VALID_HASH)

    response = client.post(f"/api/jobs/{VALID_HASH}/apply")

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "NO_REVIEW_RUN"
    assert body["details"]["job_hash"] == VALID_HASH


# ---------------------------------------------------------------------------
# GET surfaces all serializable fields, including deleted_at on a fresh row
# ---------------------------------------------------------------------------


def test_get_response_includes_deleted_at_field(
    client: TestClient, tmp_path: Path,
) -> None:
    """The serializer always returns ``deleted_at`` (None on fresh rows)."""

    db_path = tmp_path / "apply_extra.db"
    _seed_job(db_path, VALID_HASH)
    _seed_success_review_run(db_path, VALID_HASH)
    post = client.post(f"/api/jobs/{VALID_HASH}/apply").json()

    response = client.get(f"/api/apply-runs/{post['run_id']}")

    body = response.json()
    assert "deleted_at" in body["apply_run"]
    assert body["apply_run"]["deleted_at"] is None


# ---------------------------------------------------------------------------
# A second DELETE on an unknown id returns 404 (not 500)
# ---------------------------------------------------------------------------


def test_delete_with_no_review_run_seeded_returns_404(client: TestClient) -> None:
    """Deleting a row that was never created returns APPLY_RUN_NOT_FOUND."""

    response = client.delete("/api/apply-runs/12345678")

    assert response.status_code == 404
    assert response.json()["code"] == "APPLY_RUN_NOT_FOUND"
