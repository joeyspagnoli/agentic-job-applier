"""Verify `/api/jobs` source filtering stays aligned with source labels.

Purpose:
    Protect the backend/frontend source-filter contract by ensuring canonical
    filter values (`GREENHOUSE`, `WORKDAY`, `JOBSPY`) match persisted raw
    source strings from different fetchers.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import main as api_main
from src.database.db_manager import DatabaseManager
from src.models.job_posting import JobPosting


def _seed_jobs_for_source_filter(db_path: Path) -> dict[str, str]:
    """Insert one job per source family for source-filter contract tests.

    Purpose:
        Build deterministic fixture rows so `/api/jobs?source=...` behavior can
        be asserted for canonical source filter values.
    Args:
        db_path: SQLite database path used by the API test client.
    Output:
        Returns mapping of canonical source labels to inserted job hashes.
    """

    async def _seed_async() -> dict[str, str]:
        """Write test rows to SQLite and return their hashes.

        Purpose:
            Keep setup isolated in one async helper used by this sync test.
        Args:
            None.
        Output:
            Returns canonical-source to job-hash mapping.
        """

        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()

            greenhouse_job = JobPosting(
                source="greenhouse_engineering",
                source_url="https://example.com/jobs/greenhouse",
                company="Greenhouse Co",
                title="Backend Engineer",
                description="Greenhouse source row",
            )
            workday_job = JobPosting(
                source="workday_finance",
                source_url="https://example.com/jobs/workday",
                company="Workday Co",
                title="Platform Engineer",
                description="Workday source row",
            )
            jobspy_job = JobPosting(
                source="jobspy_linkedin_python",
                source_url="https://example.com/jobs/jobspy",
                company="JobSpy Co",
                title="Automation Engineer",
                description="JobSpy source row",
            )

            await db.insert_job(greenhouse_job.to_db_dict())
            await db.insert_job(workday_job.to_db_dict())
            await db.insert_job(jobspy_job.to_db_dict())

            return {
                "GREENHOUSE": greenhouse_job.job_hash,
                "WORKDAY": workday_job.job_hash,
                "JOBSPY": jobspy_job.job_hash,
            }

    return asyncio.run(_seed_async())


def test_jobs_api_source_filter_matches_canonical_labels(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify canonical source filters match raw persisted source values.

    Purpose:
        Regress source-contract drift by asserting `/api/jobs` accepts
        frontend source enums even when DB rows use detailed source strings.
    Args:
        tmp_path: Pytest temporary directory fixture.
        monkeypatch: Fixture used to redirect API database-path resolution.
    Output:
        Returns `None`; test passes when each canonical filter returns its row.
    """

    database_path = tmp_path / "jobs.db"
    expected_hashes = _seed_jobs_for_source_filter(database_path)
    monkeypatch.setattr(api_main, "resolve_database_path", lambda: database_path)

    client = TestClient(api_main.app)

    for source_label, expected_hash in expected_hashes.items():
        response = client.get(
            "/api/jobs",
            params={"source": source_label, "page_size": 100},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert payload["total_items"] == 1
        assert len(payload["items"]) == 1
        assert payload["items"][0]["job_hash"] == expected_hash
        assert payload["items"][0]["source"] == source_label
