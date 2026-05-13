"""Integration tests for the manual `POST /api/jobs/import` endpoint.

Purpose:
    Lock the contract for the dashboard's Import Job button. The endpoint
    must route the payload through the same `JobPosting.to_db_dict()` →
    `insert_job()` path the fetchers use so the row matches the
    `job_postings` schema (column names, NOT NULL columns, `status`
    CHECK constraint), and so the inserted job is immediately visible to
    the existing `GET /api/jobs` listing.

    Regression target: a previous implementation INSERTed against column
    names that do not exist in the schema (`position`, `pay`,
    `work_type`, `discovered`, `job_posting_url`) and a lowercase status
    value that violated the status CHECK constraint. Every request
    failed with a 500. These tests pin the corrected behavior.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api import main as api_main
from src.database.db_manager import DatabaseManager


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Return a `TestClient` wired to an isolated SQLite file.

    Purpose:
        Each test gets a fresh database so dedup and row-count assertions
        do not bleed across cases.
    """

    db_path = tmp_path / "jobs.db"
    monkeypatch.setattr(api_main, "resolve_database_path", lambda: db_path)
    return TestClient(api_main.app)


def _fetch_job_row(db_path: Path, job_hash: str) -> Mapping[str, Any]:
    """Read one job_postings row by hash for assertions."""

    async def _fetch() -> Mapping[str, Any]:
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            row = await db.get_job_by_hash(job_hash)
            assert row is not None, f"job not found for hash={job_hash}"
            return row

    return asyncio.run(_fetch())


def test_url_mode_inserts_a_row_in_the_right_columns(
    client: TestClient, tmp_path: Path
) -> None:
    """URL-mode import lands in `job_postings` with the expected fields."""

    response = client.post(
        "/api/jobs/import",
        json={
            "mode": "url",
            "url": "https://example.com/careers/eng-123",
            "company": "AcmeCo",
            "title": "Senior Engineer",
            "location": "Remote — US",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert isinstance(body["job_id"], int)
    assert isinstance(body["job_hash"], str) and len(body["job_hash"]) == 64
    assert body["duplicate"] is False

    row = _fetch_job_row(tmp_path / "jobs.db", body["job_hash"])
    # Columns that previously held bogus names — assert canonical schema.
    assert row["company"] == "AcmeCo"
    assert row["title"] == "Senior Engineer"
    assert row["location"] == "Remote — US"
    assert row["source"] == "manual_import"
    assert row["source_url"] == "https://example.com/careers/eng-123"
    assert row["status"] == "NEW"
    # `is_remote` is auto-inferred from a "remote" location string.
    assert bool(row["is_remote"]) is True


def test_text_mode_inserts_with_description_and_optional_fields(
    client: TestClient, tmp_path: Path
) -> None:
    """Text-mode import stores the pasted description and optional fields."""

    response = client.post(
        "/api/jobs/import",
        json={
            "mode": "text",
            "title": "Staff Backend Engineer",
            "company": "Beta Inc",
            "location": "New York, NY",
            "description": "Build distributed systems. Python + Go.",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["duplicate"] is False

    row = _fetch_job_row(tmp_path / "jobs.db", body["job_hash"])
    assert row["title"] == "Staff Backend Engineer"
    assert row["company"] == "Beta Inc"
    assert row["location"] == "New York, NY"
    assert row["description"] == "Build distributed systems. Python + Go."
    assert row["status"] == "NEW"
    # In-office location should not flip the remote heuristic.
    assert bool(row["is_remote"]) is False


def test_imported_row_is_visible_from_listing_endpoint(client: TestClient) -> None:
    """A freshly imported job appears in `GET /api/jobs?source=MANUAL_IMPORT`."""

    create = client.post(
        "/api/jobs/import",
        json={
            "mode": "url",
            "url": "https://example.com/eng-listing",
            "company": "GammaCorp",
            "title": "Platform Engineer",
        },
    )
    assert create.status_code == 200, create.text
    job_hash = create.json()["job_hash"]

    listing = client.get("/api/jobs", params={"source": "MANUAL_IMPORT"})
    assert listing.status_code == 200, listing.text
    items = listing.json()["items"]
    matching = [item for item in items if item["job_hash"] == job_hash]
    assert len(matching) == 1
    only = matching[0]
    assert only["company"] == "GammaCorp"
    assert only["position"] == "Platform Engineer"
    assert only["source"] == "MANUAL_IMPORT"
    assert only["status"] == "NEW"


def test_duplicate_import_returns_existing_id_with_duplicate_flag(
    client: TestClient,
) -> None:
    """Re-importing identical content dedups via the `JobPosting.job_hash`."""

    payload = {
        "mode": "url",
        "url": "https://example.com/dup-job",
        "company": "DupCo",
        "title": "Engineer",
    }
    first = client.post("/api/jobs/import", json=payload)
    second = client.post("/api/jobs/import", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    first_body = first.json()
    second_body = second.json()

    assert first_body["duplicate"] is False
    assert second_body["duplicate"] is True
    # Same content → same hash → same row id.
    assert first_body["job_hash"] == second_body["job_hash"]
    assert first_body["job_id"] == second_body["job_id"]


def test_url_mode_requires_url(client: TestClient) -> None:
    """URL mode without `url` returns 422 with the documented code."""

    response = client.post("/api/jobs/import", json={"mode": "url"})

    assert response.status_code == 422, response.text
    payload = response.json()
    assert payload["ok"] is False
    assert payload["code"] == "MISSING_URL"


def test_text_mode_requires_title(client: TestClient) -> None:
    """Text mode without `title` returns 422 with the documented code."""

    response = client.post(
        "/api/jobs/import",
        json={"mode": "text", "description": "body only"},
    )

    assert response.status_code == 422, response.text
    payload = response.json()
    assert payload["ok"] is False
    assert payload["code"] == "MISSING_TITLE"
