"""Contract tests for the new `has_tailor_run` / `tailor_state` filters.

Purpose:
    Lock the GET `/api/jobs` filter semantics added for the Tailored
    Resumes sidebar tab and the polling state machine: rows with a
    soft-deleted tailor run must not match `has_tailor_run=1`, and the
    `tailor_state` filter must be case-insensitive.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient

from api import main as api_main
from src.database.db_manager import DatabaseManager
from src.models.job_posting import JobPosting


JOB_WITH_RUN_HASH = "11" * 20
JOB_WITHOUT_RUN_HASH = "22" * 20
JOB_WITH_DELETED_RUN_HASH = "33" * 20


def _seed_jobs(db_path: Path) -> None:
    """Insert three jobs and bind a tailor row to two of them."""

    async def _seed() -> None:
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            for job_hash, company in (
                (JOB_WITH_RUN_HASH, "WithRunCo"),
                (JOB_WITHOUT_RUN_HASH, "NoRunCo"),
                (JOB_WITH_DELETED_RUN_HASH, "DeletedRunCo"),
            ):
                posting = JobPosting(
                    source="manual",
                    source_url="https://example.com/" + job_hash,
                    company=company,
                    title="Engineer",
                    description="desc",
                )
                row = posting.to_db_dict()
                row["job_hash"] = job_hash
                await db.insert_job(row)

            await db.insert_user_triggered_tailor_run(job_hash=JOB_WITH_RUN_HASH)

            deleted_insert = await db.insert_user_triggered_tailor_run(
                job_hash=JOB_WITH_DELETED_RUN_HASH
            )
            assert deleted_insert is not None
            await db.soft_delete_tailor_run(cast(int, deleted_insert["id"]))

    asyncio.run(_seed())


@pytest.fixture()
def client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    """TestClient wired to an isolated SQLite file."""

    db_path = tmp_path / "jobs.db"
    monkeypatch.setattr(api_main, "resolve_database_path", lambda: db_path)
    _seed_jobs(db_path)
    return TestClient(api_main.app)


def test_has_tailor_run_filter_returns_only_jobs_with_active_run(
    client: TestClient,
) -> None:
    """Soft-deleted runs are excluded; only the active-run job comes back."""

    response = client.get("/api/jobs", params={"has_tailor_run": "true"})

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["job_hash"] == JOB_WITH_RUN_HASH


def test_default_listing_includes_every_job(client: TestClient) -> None:
    """Without filters all three rows come back, with `tailor_run` populated."""

    response = client.get("/api/jobs", params={"page_size": 100})

    assert response.status_code == 200
    body = response.json()
    assert body["total_items"] == 3
    by_hash = {item["job_hash"]: item for item in body["items"]}
    assert by_hash[JOB_WITH_RUN_HASH]["tailor_run"] is not None
    assert by_hash[JOB_WITH_RUN_HASH]["tailor_run"]["status"] == "PENDING"
    assert by_hash[JOB_WITHOUT_RUN_HASH]["tailor_run"] is None
    assert by_hash[JOB_WITH_DELETED_RUN_HASH]["tailor_run"] is None


def test_tailor_state_filter_narrows_to_exact_status(
    client: TestClient,
) -> None:
    """`tailor_state=PENDING` matches PENDING rows only."""

    response = client.get(
        "/api/jobs",
        params={"has_tailor_run": "true", "tailor_state": "PENDING"},
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["job_hash"] == JOB_WITH_RUN_HASH


def test_tailor_state_filter_is_case_insensitive(
    client: TestClient,
) -> None:
    """Lowercase input is upper-cased server-side before SQL comparison."""

    response = client.get(
        "/api/jobs",
        params={"has_tailor_run": "true", "tailor_state": "pending"},
    )

    assert response.status_code == 200
    assert len(response.json()["items"]) == 1


def test_tailor_state_filter_with_no_match_returns_zero(
    client: TestClient,
) -> None:
    """`tailor_state=SUCCESS` does not match the PENDING-only fixture."""

    response = client.get(
        "/api/jobs",
        params={"has_tailor_run": "true", "tailor_state": "SUCCESS"},
    )

    assert response.status_code == 200
    assert response.json()["items"] == []
