"""HTTP contract tests for the `/api/jobs/{hash}/tailor` family.

Purpose:
    Lock the user-triggered tailor-run endpoints — enqueue (POST), read
    (GET), and soft-delete (DELETE) — including every documented 4xx
    rejection. The BackgroundTask body is patched out so the tests stay
    synchronous and deterministic; success on the enqueue path means the
    row is PENDING with a freshly generated id.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import main as api_main
from api.routers import tailor_runs as tailor_runs_router
from src.database._mixins.system_settings import TAILOR_MODE_KEY
from src.database.db_manager import DatabaseManager
from src.models.job_posting import JobPosting


VALID_HASH = "ab" * 20  # 40 hex chars — matches JOB_HASH_PATTERN


def _seed_qualified_job(db_path: Path, job_hash: str) -> None:
    """Insert one QUALIFIED job at the requested hash for the API tests."""

    async def _seed() -> None:
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            posting = JobPosting(
                source="manual",
                source_url="https://example.com/" + job_hash,
                company="ACME",
                title="Engineer",
                description="An interesting role.",
            )
            db_dict = posting.to_db_dict()
            db_dict["job_hash"] = job_hash
            await db.insert_job(db_dict)

    asyncio.run(_seed())


def _set_tailor_mode(db_path: Path, mode: str) -> None:
    """Write the automation tailor mode directly."""

    async def _set() -> None:
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            await db.set_automation_mode(TAILOR_MODE_KEY, mode)

    asyncio.run(_set())


@pytest.fixture()
def client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    """Construct an isolated TestClient with a stubbed BackgroundTask."""

    db_path = tmp_path / "tailor_api.db"
    monkeypatch.setattr(api_main, "resolve_database_path", lambda: db_path)

    async def _noop_background(**_kwargs: object) -> None:
        return None

    monkeypatch.setattr(
        tailor_runs_router,
        "_run_pipeline_background",
        _noop_background,
    )
    return TestClient(api_main.app)


def test_post_enqueues_pending_run_and_returns_202(
    client: TestClient,
    tmp_path: Path,
) -> None:
    """Happy path: 202 envelope with a positive run id and PENDING status."""

    db_path = tmp_path / "tailor_api.db"
    _seed_qualified_job(db_path, VALID_HASH)

    response = client.post(f"/api/jobs/{VALID_HASH}/tailor")

    assert response.status_code == 202
    body = response.json()
    assert body["ok"] is True
    assert body["status"] == "PENDING"
    assert body["job_hash"] == VALID_HASH
    assert isinstance(body["tailor_run_id"], int) and body["tailor_run_id"] > 0


def test_post_rejects_invalid_hash_with_400(client: TestClient) -> None:
    """Path validator rejects non-hex hashes."""

    response = client.post("/api/jobs/not-a-valid-hash/tailor")

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_JOB_HASH"


def test_post_returns_404_when_job_missing(client: TestClient) -> None:
    """Valid-shape hash that doesn't exist in DB → 404 JOB_NOT_FOUND."""

    response = client.post(f"/api/jobs/{VALID_HASH}/tailor")

    assert response.status_code == 404
    assert response.json()["code"] == "JOB_NOT_FOUND"


def test_post_returns_409_when_mode_autonomous(
    client: TestClient,
    tmp_path: Path,
) -> None:
    """Autonomous mode disables manual triggers."""

    db_path = tmp_path / "tailor_api.db"
    _seed_qualified_job(db_path, VALID_HASH)
    _set_tailor_mode(db_path, "autonomous")

    response = client.post(f"/api/jobs/{VALID_HASH}/tailor")

    assert response.status_code == 409
    assert response.json()["code"] == "MODE_AUTONOMOUS"


def test_post_returns_409_when_run_already_exists(
    client: TestClient,
    tmp_path: Path,
) -> None:
    """A second POST while a PENDING row exists returns RUN_ALREADY_EXISTS."""

    db_path = tmp_path / "tailor_api.db"
    _seed_qualified_job(db_path, VALID_HASH)

    first = client.post(f"/api/jobs/{VALID_HASH}/tailor")
    assert first.status_code == 202

    second = client.post(f"/api/jobs/{VALID_HASH}/tailor")

    assert second.status_code == 409
    assert second.json()["code"] == "RUN_ALREADY_EXISTS"


def test_post_returns_409_when_budget_exceeded(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Budget exhaustion shows up as 409 BUDGET_EXCEEDED.

    Purpose:
        The handoff explicitly mentioned the bug-fix follow-up that wired
        the budget guard into the opt-in API path; lock the behavior.
    """

    db_path = tmp_path / "tailor_api.db"
    _seed_qualified_job(db_path, VALID_HASH)

    async def _exceeded(self: object) -> bool:
        return True

    monkeypatch.setattr(
        "src.database._mixins.costs.CostsMixin.is_budget_exceeded",
        _exceeded,
    )

    response = client.post(f"/api/jobs/{VALID_HASH}/tailor")

    assert response.status_code == 409
    assert response.json()["code"] == "BUDGET_EXCEEDED"


def test_get_returns_row_for_pending_with_null_pdf_url(
    client: TestClient,
    tmp_path: Path,
) -> None:
    """GET on a PENDING row returns the serialized row with `pdf_url=None`."""

    db_path = tmp_path / "tailor_api.db"
    _seed_qualified_job(db_path, VALID_HASH)
    post = client.post(f"/api/jobs/{VALID_HASH}/tailor").json()

    response = client.get(f"/api/tailor-runs/{post['tailor_run_id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["tailor_run"]["id"] == post["tailor_run_id"]
    assert body["tailor_run"]["status"] == "PENDING"
    assert body["tailor_run"]["pdf_url"] is None


def test_get_returns_404_for_unknown_id(client: TestClient) -> None:
    """Unknown run ids produce TAILOR_RUN_NOT_FOUND."""

    response = client.get("/api/tailor-runs/99999")

    assert response.status_code == 404
    assert response.json()["code"] == "TAILOR_RUN_NOT_FOUND"


def test_get_exposes_pdf_url_only_when_success(
    client: TestClient,
    tmp_path: Path,
) -> None:
    """Once a row is SUCCESS, `pdf_url` resolves to the resume endpoint."""

    db_path = tmp_path / "tailor_api.db"
    _seed_qualified_job(db_path, VALID_HASH)
    post = client.post(f"/api/jobs/{VALID_HASH}/tailor").json()

    async def _mark_success() -> None:
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            await db.record_tailor_success(
                run_id=post["tailor_run_id"],
                artifact_yaml_path="/tmp/a.yaml",
                artifact_tex_path="/tmp/a.tex",
                artifact_pdf_path="/tmp/a.pdf",
                page_count=1,
            )

    asyncio.run(_mark_success())

    response = client.get(f"/api/tailor-runs/{post['tailor_run_id']}")

    assert response.status_code == 200
    assert response.json()["tailor_run"]["pdf_url"] == f"/api/jobs/{VALID_HASH}/resume"


def test_delete_clears_slot_for_re_enqueue(
    client: TestClient,
    tmp_path: Path,
) -> None:
    """POST → DELETE → POST returns a new id; soft-delete frees the slot."""

    db_path = tmp_path / "tailor_api.db"
    _seed_qualified_job(db_path, VALID_HASH)
    first_post = client.post(f"/api/jobs/{VALID_HASH}/tailor").json()

    delete_response = client.delete(f"/api/tailor-runs/{first_post['tailor_run_id']}")
    assert delete_response.status_code == 204

    second_post = client.post(f"/api/jobs/{VALID_HASH}/tailor")
    assert second_post.status_code == 202
    assert second_post.json()["tailor_run_id"] != first_post["tailor_run_id"]


def test_delete_returns_404_for_unknown_id(client: TestClient) -> None:
    """Deleting a row that never existed → 404 TAILOR_RUN_NOT_FOUND."""

    response = client.delete("/api/tailor-runs/99999")

    assert response.status_code == 404
    assert response.json()["code"] == "TAILOR_RUN_NOT_FOUND"


def test_delete_returns_404_when_already_deleted(
    client: TestClient,
    tmp_path: Path,
) -> None:
    """Re-deleting an already soft-deleted row → TAILOR_RUN_ALREADY_DELETED."""

    db_path = tmp_path / "tailor_api.db"
    _seed_qualified_job(db_path, VALID_HASH)
    post = client.post(f"/api/jobs/{VALID_HASH}/tailor").json()
    assert client.delete(f"/api/tailor-runs/{post['tailor_run_id']}").status_code == 204

    response = client.delete(f"/api/tailor-runs/{post['tailor_run_id']}")

    assert response.status_code == 404
    assert response.json()["code"] == "TAILOR_RUN_ALREADY_DELETED"
