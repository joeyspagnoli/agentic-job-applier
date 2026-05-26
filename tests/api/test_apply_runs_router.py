"""HTTP contract tests for the `/api/jobs/{hash}/apply` family.

Purpose:
    Lock the apply-run endpoints — enqueue (POST), read (GET), and
    soft-delete (DELETE) — including every documented 4xx rejection.
    No background pipeline is spawned; all DB operations are synchronous
    helpers seeded before the HTTP call.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import main as api_main
from api.routers import apply_runs as apply_runs_router
from src.agents.resume_tailor.compiler import ResumeCompileError
from src.database.db_manager import DatabaseManager
from src.models.job_posting import JobPosting


VALID_HASH = "cd" * 20  # 40 hex chars — matches JOB_HASH_PATTERN


def _seed_job(db_path: Path, job_hash: str) -> None:
    """Insert one job posting at the requested hash."""

    async def _seed() -> None:
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            posting = JobPosting(
                source="manual",
                source_url="https://example.com/" + job_hash,
                company="ACME",
                title="Engineer",
                description="Interesting role.",
            )
            db_dict = posting.to_db_dict()
            db_dict["job_hash"] = job_hash
            await db.insert_job(db_dict)

    asyncio.run(_seed())


def _seed_review_run(db_path: Path, job_hash: str) -> int:
    """Insert one SUCCESS review_runs row for the job and return its id."""

    async def _seed() -> int:
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            # insert_pipeline_review_run requires a tailor_run_id; insert a
            # minimal tailor_runs row first.
            conn = db._require_conn()
            tailor_cursor = await conn.execute(
                "INSERT INTO tailor_runs (job_hash, status) VALUES (?, 'SUCCESS') RETURNING id",
                (job_hash,),
            )
            tailor_row = await tailor_cursor.fetchone()
            await conn.commit()
            assert tailor_row is not None
            tailor_run_id = int(tailor_row["id"])

            review_id = await db.insert_pipeline_review_run(
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
        return review_id

    return asyncio.run(_seed())


@pytest.fixture()
def client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    """Construct an isolated TestClient backed by a temp database."""

    db_path = tmp_path / "apply_api.db"
    monkeypatch.setattr(api_main, "resolve_database_path", lambda: db_path)
    return TestClient(api_main.app)


@pytest.fixture()
def stub_base_compile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Replace ``compile_base_resume_pdf`` with a deterministic stub.

    Purpose:
        Avoid invoking tectonic from unit tests. Returns the path of a
        zero-byte stub PDF the synthesizer will store in the new
        ``review_runs.fallback_base_pdf_path`` column.
    """

    stub_pdf = tmp_path / "base_resume_stub.pdf"
    stub_pdf.write_bytes(b"%PDF-stub")

    async def _stub_compile(**_kwargs: object) -> Path:
        return stub_pdf

    monkeypatch.setattr(
        apply_runs_router, "compile_base_resume_pdf", _stub_compile
    )
    return stub_pdf


# ---------------------------------------------------------------------------
# POST /api/jobs/{hash}/apply
# ---------------------------------------------------------------------------


def test_post_enqueues_pending_run_and_returns_200(
    client: TestClient,
    tmp_path: Path,
) -> None:
    """Happy path: 200 envelope with a positive run_id and PENDING status."""

    db_path = tmp_path / "apply_api.db"
    _seed_job(db_path, VALID_HASH)
    _seed_review_run(db_path, VALID_HASH)

    response = client.post(f"/api/jobs/{VALID_HASH}/apply")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["run_id"], int) and body["run_id"] > 0
    assert body["status"] == "PENDING"


def test_post_rejects_invalid_hash_with_400(client: TestClient) -> None:
    """Path validator rejects non-hex hashes."""

    response = client.post("/api/jobs/not-a-valid-hash/apply")

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_JOB_HASH"


def test_post_returns_422_when_no_review_run(
    client: TestClient,
    tmp_path: Path,
) -> None:
    """Default resume_mode=tailored still requires a SUCCESS review."""

    db_path = tmp_path / "apply_api.db"
    _seed_job(db_path, VALID_HASH)

    # Default body (omitted) keeps the original contract.
    response = client.post(f"/api/jobs/{VALID_HASH}/apply")

    assert response.status_code == 422
    assert response.json()["code"] == "NO_REVIEW_RUN"

    # Explicit `resume_mode=tailored` is equivalent.
    explicit_response = client.post(
        f"/api/jobs/{VALID_HASH}/apply",
        json={"resume_mode": "tailored"},
    )
    assert explicit_response.status_code == 422
    assert explicit_response.json()["code"] == "NO_REVIEW_RUN"


def test_post_with_resume_mode_base_returns_200_when_no_review_run(
    client: TestClient,
    tmp_path: Path,
    stub_base_compile: Path,
) -> None:
    """`resume_mode=base` synthesizes a tailor+review chain and enqueues apply.

    The skip-tailoring path that the NotTailoredModal's "Apply anyways"
    button uses must succeed even though the job has no SUCCESS review.
    """

    db_path = tmp_path / "apply_api.db"
    _seed_job(db_path, VALID_HASH)

    response = client.post(
        f"/api/jobs/{VALID_HASH}/apply",
        json={"resume_mode": "base"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "PENDING"
    assert isinstance(body["run_id"], int) and body["run_id"] > 0

    async def _read_review() -> tuple[str, str]:
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            apply_row = await db.get_apply_run(body["run_id"])
            assert apply_row is not None
            conn = db._require_conn()
            review_cursor = await conn.execute(
                "SELECT verdict, fallback_base_pdf_path FROM review_runs "
                "WHERE id = ?",
                (apply_row["review_run_id"],),
            )
            review_row = await review_cursor.fetchone()
            assert review_row is not None
            return str(review_row["verdict"]), str(
                review_row["fallback_base_pdf_path"]
            )

    verdict, pdf_path = asyncio.run(_read_review())
    assert verdict == "BASE"
    assert pdf_path == str(stub_base_compile)


def test_post_with_resume_mode_base_returns_409_when_inflight(
    client: TestClient,
    tmp_path: Path,
    stub_base_compile: Path,
) -> None:
    """Second base-mode POST while a PENDING run exists → 409."""

    db_path = tmp_path / "apply_api.db"
    _seed_job(db_path, VALID_HASH)

    first = client.post(
        f"/api/jobs/{VALID_HASH}/apply",
        json={"resume_mode": "base"},
    )
    assert first.status_code == 200

    second = client.post(
        f"/api/jobs/{VALID_HASH}/apply",
        json={"resume_mode": "base"},
    )

    assert second.status_code == 409
    assert second.json()["code"] == "APPLY_RUN_IN_FLIGHT"


def test_post_with_resume_mode_base_returns_422_on_compile_failure(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tectonic failure surfaces as 422 BASE_COMPILE_FAILED."""

    db_path = tmp_path / "apply_api.db"
    _seed_job(db_path, VALID_HASH)

    async def _fail_compile(**_kwargs: object) -> Path:
        raise ResumeCompileError("tectonic exploded")

    monkeypatch.setattr(
        apply_runs_router, "compile_base_resume_pdf", _fail_compile
    )

    response = client.post(
        f"/api/jobs/{VALID_HASH}/apply",
        json={"resume_mode": "base"},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "BASE_COMPILE_FAILED"
    assert "tectonic exploded" in body["details"]["compile_error"]


def test_post_with_resume_mode_base_returns_404_when_job_missing(
    client: TestClient,
    stub_base_compile: Path,
) -> None:
    """Base-mode against an unknown job → 404 JOB_NOT_FOUND."""

    response = client.post(
        f"/api/jobs/{VALID_HASH}/apply",
        json={"resume_mode": "base"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "JOB_NOT_FOUND"


def test_second_post_returns_409_apply_run_in_flight(
    client: TestClient,
    tmp_path: Path,
) -> None:
    """A second POST while a PENDING row exists returns APPLY_RUN_IN_FLIGHT."""

    db_path = tmp_path / "apply_api.db"
    _seed_job(db_path, VALID_HASH)
    _seed_review_run(db_path, VALID_HASH)

    first = client.post(f"/api/jobs/{VALID_HASH}/apply")
    assert first.status_code == 200

    second = client.post(f"/api/jobs/{VALID_HASH}/apply")

    assert second.status_code == 409
    body = second.json()
    assert body["code"] == "APPLY_RUN_IN_FLIGHT"
    assert isinstance(body["details"]["run_id"], int)
    assert body["details"]["status"] == "PENDING"


# ---------------------------------------------------------------------------
# GET /api/apply-runs/{id}
# ---------------------------------------------------------------------------


def test_get_returns_row_for_pending_run(
    client: TestClient,
    tmp_path: Path,
) -> None:
    """GET on a PENDING row returns the serialized row."""

    db_path = tmp_path / "apply_api.db"
    _seed_job(db_path, VALID_HASH)
    _seed_review_run(db_path, VALID_HASH)
    post_body = client.post(f"/api/jobs/{VALID_HASH}/apply").json()

    response = client.get(f"/api/apply-runs/{post_body['run_id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["apply_run"]["id"] == post_body["run_id"]
    assert body["apply_run"]["status"] == "PENDING"
    assert body["apply_run"]["job_hash"] == VALID_HASH


def test_get_returns_404_for_unknown_id(client: TestClient) -> None:
    """Unknown run ids produce APPLY_RUN_NOT_FOUND."""

    response = client.get("/api/apply-runs/9999999")

    assert response.status_code == 404
    assert response.json()["code"] == "APPLY_RUN_NOT_FOUND"


# ---------------------------------------------------------------------------
# DELETE /api/apply-runs/{id}
# ---------------------------------------------------------------------------


def test_delete_returns_204_and_subsequent_get_returns_404(
    client: TestClient,
    tmp_path: Path,
) -> None:
    """DELETE soft-deletes the row; subsequent GET returns 404."""

    db_path = tmp_path / "apply_api.db"
    _seed_job(db_path, VALID_HASH)
    _seed_review_run(db_path, VALID_HASH)
    post_body = client.post(f"/api/jobs/{VALID_HASH}/apply").json()
    run_id = post_body["run_id"]

    delete_response = client.delete(f"/api/apply-runs/{run_id}")
    assert delete_response.status_code == 204

    get_response = client.get(f"/api/apply-runs/{run_id}")
    assert get_response.status_code == 404
    assert get_response.json()["code"] == "APPLY_RUN_NOT_FOUND"


def test_delete_frees_slot_for_re_enqueue(
    client: TestClient,
    tmp_path: Path,
) -> None:
    """POST → DELETE → POST succeeds and produces a new run_id."""

    db_path = tmp_path / "apply_api.db"
    _seed_job(db_path, VALID_HASH)
    _seed_review_run(db_path, VALID_HASH)

    first_post = client.post(f"/api/jobs/{VALID_HASH}/apply").json()
    assert client.delete(f"/api/apply-runs/{first_post['run_id']}").status_code == 204

    second_post = client.post(f"/api/jobs/{VALID_HASH}/apply")

    assert second_post.status_code == 200
    assert second_post.json()["run_id"] != first_post["run_id"]


def test_delete_returns_404_for_unknown_id(client: TestClient) -> None:
    """Deleting a row that never existed → 404 APPLY_RUN_NOT_FOUND."""

    response = client.delete("/api/apply-runs/9999999")

    assert response.status_code == 404
    assert response.json()["code"] == "APPLY_RUN_NOT_FOUND"


def test_delete_returns_404_when_already_deleted(
    client: TestClient,
    tmp_path: Path,
) -> None:
    """Re-deleting an already soft-deleted row → APPLY_RUN_ALREADY_DELETED."""

    db_path = tmp_path / "apply_api.db"
    _seed_job(db_path, VALID_HASH)
    _seed_review_run(db_path, VALID_HASH)
    post_body = client.post(f"/api/jobs/{VALID_HASH}/apply").json()
    run_id = post_body["run_id"]

    assert client.delete(f"/api/apply-runs/{run_id}").status_code == 204

    response = client.delete(f"/api/apply-runs/{run_id}")

    assert response.status_code == 404
    assert response.json()["code"] == "APPLY_RUN_ALREADY_DELETED"
