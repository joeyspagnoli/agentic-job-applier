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


def _seed_workday_and_legacy_apify_rows(db_path: Path) -> dict[str, str]:
    """Insert one ``workday_*`` row and one legacy ``apify_workday_*`` row.

    Purpose:
        Build fixture rows that exercise the `%apify%` LIKE clause retained
        for backwards compatibility; both rows must match the `WORKDAY`
        filter even though the source strings differ.
    Args:
        db_path: SQLite database path used by the API test client.
    Output:
        Returns mapping of label key (`workday`, `legacy_apify`) to job hash.
    """

    async def _seed_async() -> dict[str, str]:
        """Persist one current and one legacy Workday row for the regression test.

        Purpose:
            Centralize the async seeding logic used by the synchronous test.
        Args:
            None.
        Output:
            Returns mapping of label key to inserted job hash.
        """

        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()

            current_workday_job = JobPosting(
                source="workday_acme",
                source_url="https://example.com/jobs/workday/acme",
                company="Acme",
                title="Platform Engineer",
                description="Current Workday source row",
            )
            legacy_apify_job = JobPosting(
                source="apify_workday_legacy_co",
                source_url="https://example.com/jobs/apify/legacy",
                company="Legacy Co",
                title="Platform Engineer",
                description="Legacy Apify Workday source row",
            )

            await db.insert_job(current_workday_job.to_db_dict())
            await db.insert_job(legacy_apify_job.to_db_dict())

            return {
                "workday": current_workday_job.job_hash,
                "legacy_apify": legacy_apify_job.job_hash,
            }

    return asyncio.run(_seed_async())


def test_jobs_api_workday_filter_matches_legacy_apify_workday_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify the `WORKDAY` filter still matches legacy `apify_workday_*` rows.

    Purpose:
        The Apify Workday actor was replaced by the free CXS scraper, but
        existing crawl_history and job_postings rows still use the
        `apify_workday_*` source prefix. Removing the `%apify%` LIKE branch
        would silently hide that historical data; this test guards it.
    Args:
        tmp_path: Pytest temporary directory fixture.
        monkeypatch: Fixture used to redirect API database-path resolution.
    Output:
        Returns `None`; passes when the WORKDAY filter returns both rows.
    """

    database_path = tmp_path / "jobs.db"
    expected_hashes = _seed_workday_and_legacy_apify_rows(database_path)
    monkeypatch.setattr(api_main, "resolve_database_path", lambda: database_path)

    client = TestClient(api_main.app)
    response = client.get(
        "/api/jobs", params={"source": "WORKDAY", "page_size": 100}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["total_items"] == 2
    returned_hashes = {item["job_hash"] for item in payload["items"]}
    assert returned_hashes == set(expected_hashes.values())


def test_source_label_maps_legacy_apify_workday_source_to_workday() -> None:
    """Verify ``_source_label`` collapses legacy ``apify_workday_*`` to ``WORKDAY``.

    Purpose:
        The frontend source filter is keyed off `_source_label`'s output; legacy
        rows must surface as ``WORKDAY`` so existing dashboards do not lose data.
    Args:
        None.
    Output:
        Returns ``None``; passes when the helper returns ``WORKDAY``.
    """

    label = api_main._source_label("apify_workday_legacy_co")

    assert label == "WORKDAY"


@pytest.mark.parametrize(
    "raw_source, expected_label",
    [
        ("greenhouse_stripe", "GREENHOUSE"),
        ("workday_kbr", "WORKDAY"),
        ("apify_workday_legacy", "WORKDAY"),
        ("jobspy_indeed_civil_engineer", "JOBSPY"),
        ("linkedin_civil_engineering_intern", "LINKEDIN"),
        ("icims_skanska_usa", "ICIMS"),
        ("taleo_johnson_and_johnson", "TALEO"),
        ("lever_coupa_software", "LEVER"),
        ("ashby_anrok", "ASHBY"),
        ("adzuna_us", "ADZUNA"),
        ("adzuna_gb", "ADZUNA"),
        ("github_simplifyjobs_summer2026-internships", "GITHUB_REPOS"),
        ("manual_import_user_42", "MANUAL_IMPORT"),
        ("totally_unknown_fetcher_xyz", "OTHER"),
    ],
)
def test_source_label_covers_every_known_fetcher_family(
    raw_source: str, expected_label: str
) -> None:
    """Lock the raw-source -> dashboard-label mapping for every fetcher.

    Purpose:
        Guard against silent reclassification when a new fetcher family is
        added. Every prefix that lands in `job_postings.source` must map to
        a stable label the dashboard understands.
    Args:
        raw_source: Source string a fetcher might persist.
        expected_label: Canonical user-facing label the dashboard renders.
    Output:
        Returns ``None``; assertion failure surfaces a contract regression.
    """

    label = api_main._source_label(raw_source)

    assert label == expected_label


@pytest.mark.parametrize(
    "filter_label, raw_source, should_match",
    [
        ("LINKEDIN", "linkedin_civil_engineering_intern", True),
        ("LINKEDIN", "jobspy_linkedin_python", False),
        ("ICIMS", "icims_skanska_usa", True),
        ("TALEO", "taleo_johnson_and_johnson", True),
        ("LEVER", "lever_coupa_software", True),
        ("ASHBY", "ashby_anrok", True),
        ("ADZUNA", "adzuna_us", True),
        ("ADZUNA", "linkedin_civil_engineering_intern", False),
        ("GITHUB_REPOS", "github_simplifyjobs_summer2026", True),
        ("MANUAL_IMPORT", "manual_import_user_42", True),
        ("JOBSPY", "linkedin_civil_engineering_intern", False),
    ],
)
def test_jobs_api_extended_source_filters_round_trip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    filter_label: str,
    raw_source: str,
    should_match: bool,
) -> None:
    """Verify each new label filter selects only its own fetcher family.

    Purpose:
        After extending `_source_label` and `_source_filter_sql` to cover
        LinkedIn, iCIMS, Taleo, Lever, Ashby, GitHub repos, and manual
        imports, prove the round trip: a raw source written by family X
        must surface under filter label X and not leak across families.
    Args:
        tmp_path: Pytest temporary directory fixture.
        monkeypatch: Fixture used to redirect API database-path resolution.
        filter_label: Canonical filter value the frontend sends.
        raw_source: Raw source string seeded into `job_postings`.
        should_match: True when this filter should return the seeded row.
    Output:
        Returns ``None``; assertion failure surfaces a contract regression.
    """

    async def _seed_one() -> str:
        """Seed one job row and return its hash."""

        async with DatabaseManager(str(tmp_path / "jobs.db")) as db:
            await db.create_tables()
            job = JobPosting(
                source=raw_source,
                source_url=f"https://example.com/jobs/{raw_source}",
                company="Acme",
                title="Engineering Intern",
                description="seed row",
            )
            await db.insert_job(job.to_db_dict())
            return job.job_hash

    job_hash = asyncio.run(_seed_one())
    monkeypatch.setattr(
        api_main, "resolve_database_path", lambda: tmp_path / "jobs.db"
    )

    response = TestClient(api_main.app).get(
        "/api/jobs", params={"source": filter_label, "page_size": 100}
    )

    assert response.status_code == 200
    payload = response.json()
    if should_match:
        assert payload["total_items"] == 1
        assert payload["items"][0]["job_hash"] == job_hash
    else:
        assert payload["total_items"] == 0
