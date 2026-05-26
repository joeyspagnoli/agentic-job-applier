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
import shutil
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


def test_post_with_apply_after_persists_column(
    client: TestClient,
    tmp_path: Path,
) -> None:
    """Body `{apply_after: true}` writes `apply_after_completion = 1`."""

    db_path = tmp_path / "tailor_api.db"
    _seed_qualified_job(db_path, VALID_HASH)

    response = client.post(
        f"/api/jobs/{VALID_HASH}/tailor",
        json={"apply_after": True},
    )

    assert response.status_code == 202
    run_id = response.json()["tailor_run_id"]

    async def _read_flag() -> int:
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            row = await db.get_tailor_run(run_id)
            assert row is not None
            raw_value = row["apply_after_completion"]
            if raw_value is None:
                return 0
            converted: int = int(raw_value)  # type: ignore[call-overload]
            return converted

    assert asyncio.run(_read_flag()) == 1


def test_post_without_apply_after_defaults_to_zero(
    client: TestClient,
    tmp_path: Path,
) -> None:
    """Omitted body keeps `apply_after_completion = 0`."""

    db_path = tmp_path / "tailor_api.db"
    _seed_qualified_job(db_path, VALID_HASH)

    response = client.post(f"/api/jobs/{VALID_HASH}/tailor")

    assert response.status_code == 202
    run_id = response.json()["tailor_run_id"]

    async def _read_flag() -> int:
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            row = await db.get_tailor_run(run_id)
            assert row is not None
            raw_value = row["apply_after_completion"]
            if raw_value is None:
                return 0
            converted: int = int(raw_value)  # type: ignore[call-overload]
            return converted

    assert asyncio.run(_read_flag()) == 0


def test_pipeline_completion_with_apply_after_enqueues_apply_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_run_pipeline_background` with apply_after=True enqueues apply on success.

    Bypasses the HTTP fixture entirely (which noops the BackgroundTask)
    so the real `_run_pipeline_background` path is exercised end-to-end.
    """

    from types import SimpleNamespace

    db_path = tmp_path / "tailor_api.db"
    _seed_qualified_job(db_path, VALID_HASH)
    monkeypatch.setattr(api_main, "resolve_database_path", lambda: db_path)

    async def _stub_pipeline(
        *,
        db: object,
        tailor_run_id: int,
        job_hash: str,
        base_resume_tex_path: object,
        candidate_profile_yaml_path: object,
        output_dir: object,
    ) -> object:
        async with DatabaseManager(str(db_path)) as inner_db:
            await inner_db.create_tables()
            inner_conn = inner_db._require_conn()
            await inner_conn.execute(
                "UPDATE tailor_runs SET status='SUCCESS', "
                "completed_at=CURRENT_TIMESTAMP WHERE id = ?",
                (tailor_run_id,),
            )
            review_cursor = await inner_conn.execute(
                "INSERT INTO review_runs ("
                "job_hash, tailor_run_id, status, verdict, "
                "fallback_base_pdf_path, completed_at) "
                "VALUES (?, ?, 'SUCCESS', 'BASE', '/tmp/fake.pdf', "
                "CURRENT_TIMESTAMP) RETURNING id",
                (job_hash, tailor_run_id),
            )
            review_row = await review_cursor.fetchone()
            await inner_conn.commit()
            assert review_row is not None
        return SimpleNamespace(success=True, review_run_id=int(review_row["id"]))

    spawned_calls: list[dict[str, object]] = []

    async def _capture_spawn(**kwargs: object) -> None:
        spawned_calls.append(kwargs)

    monkeypatch.setattr(
        tailor_runs_router, "run_tailor_review_pipeline", _stub_pipeline
    )
    monkeypatch.setattr(
        "api.routers.apply_runs._spawn_user_apply_task", _capture_spawn
    )

    async def _seed_tailor_row() -> int:
        async with DatabaseManager(str(db_path)) as inner_db:
            await inner_db.create_tables()
            claim = await inner_db.insert_user_triggered_tailor_run(
                job_hash=VALID_HASH, apply_after_completion=True
            )
            assert claim is not None
            return claim["id"]

    tailor_run_id = asyncio.run(_seed_tailor_row())

    asyncio.run(
        tailor_runs_router._run_pipeline_background(
            db_path=str(db_path),
            tailor_run_id=tailor_run_id,
            job_hash=VALID_HASH,
            output_dir=tmp_path / "out",
            apply_after=True,
        )
    )

    async def _read_apply_rows() -> list[tuple[int, str]]:
        async with DatabaseManager(str(db_path)) as inner_db:
            await inner_db.create_tables()
            conn = inner_db._require_conn()
            cursor = await conn.execute(
                "SELECT id, status FROM apply_runs WHERE job_hash = ?",
                (VALID_HASH,),
            )
            rows = await cursor.fetchall()
            return [(int(row["id"]), str(row["status"])) for row in rows]

    rows = asyncio.run(_read_apply_rows())
    assert len(rows) == 1
    assert rows[0][1] == "PENDING"
    assert len(spawned_calls) == 1


def test_pipeline_failure_with_apply_after_does_not_enqueue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed pipeline result is observed and no apply row is created."""

    from types import SimpleNamespace

    db_path = tmp_path / "tailor_api.db"
    _seed_qualified_job(db_path, VALID_HASH)
    monkeypatch.setattr(api_main, "resolve_database_path", lambda: db_path)

    async def _stub_failed_pipeline(**_kwargs: object) -> object:
        return SimpleNamespace(success=False, review_run_id=None)

    monkeypatch.setattr(
        tailor_runs_router, "run_tailor_review_pipeline", _stub_failed_pipeline
    )

    spawned_calls: list[dict[str, object]] = []

    async def _capture_spawn(**kwargs: object) -> None:
        spawned_calls.append(kwargs)

    monkeypatch.setattr(
        "api.routers.apply_runs._spawn_user_apply_task", _capture_spawn
    )

    async def _seed_tailor_row() -> int:
        async with DatabaseManager(str(db_path)) as inner_db:
            await inner_db.create_tables()
            claim = await inner_db.insert_user_triggered_tailor_run(
                job_hash=VALID_HASH, apply_after_completion=True
            )
            assert claim is not None
            return claim["id"]

    tailor_run_id = asyncio.run(_seed_tailor_row())

    asyncio.run(
        tailor_runs_router._run_pipeline_background(
            db_path=str(db_path),
            tailor_run_id=tailor_run_id,
            job_hash=VALID_HASH,
            output_dir=tmp_path / "out",
            apply_after=True,
        )
    )

    async def _count_apply_rows() -> int:
        async with DatabaseManager(str(db_path)) as inner_db:
            await inner_db.create_tables()
            conn = inner_db._require_conn()
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM apply_runs WHERE job_hash = ?",
                (VALID_HASH,),
            )
            row = await cursor.fetchone()
            assert row is not None
            return int(row[0])

    assert asyncio.run(_count_apply_rows()) == 0
    assert spawned_calls == []


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


# ---------------------------------------------------------------------------
# POST /api/tailor-runs/{id}/retry — atomic delete + re-enqueue.
# ---------------------------------------------------------------------------


def _mark_run_failed(db_path: Path, run_id: int) -> None:
    """Transition the given run to FAILED so retry-eligibility kicks in."""

    async def _fail() -> None:
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            await db.record_tailor_failure(
                run_id=run_id, error="boom", next_retry_at=None
            )

    asyncio.run(_fail())


def test_retry_returns_404_for_unknown_id(client: TestClient) -> None:
    """Retrying a row that never existed surfaces TAILOR_RUN_NOT_FOUND."""

    response = client.post("/api/tailor-runs/99999/retry")

    assert response.status_code == 404
    assert response.json()["code"] == "TAILOR_RUN_NOT_FOUND"


def test_retry_returns_404_when_already_deleted(
    client: TestClient,
    tmp_path: Path,
) -> None:
    """Retrying an already soft-deleted row → TAILOR_RUN_ALREADY_DELETED."""

    db_path = tmp_path / "tailor_api.db"
    _seed_qualified_job(db_path, VALID_HASH)
    post = client.post(f"/api/jobs/{VALID_HASH}/tailor").json()
    assert client.delete(f"/api/tailor-runs/{post['tailor_run_id']}").status_code == 204

    response = client.post(f"/api/tailor-runs/{post['tailor_run_id']}/retry")

    assert response.status_code == 404
    assert response.json()["code"] == "TAILOR_RUN_ALREADY_DELETED"


def test_retry_in_opt_in_mode_inserts_fresh_pending_row(
    client: TestClient,
    tmp_path: Path,
) -> None:
    """opt_in retry: 202 envelope with retry_via=user and a new run id."""

    db_path = tmp_path / "tailor_api.db"
    _seed_qualified_job(db_path, VALID_HASH)
    first = client.post(f"/api/jobs/{VALID_HASH}/tailor").json()
    _mark_run_failed(db_path, first["tailor_run_id"])

    response = client.post(f"/api/tailor-runs/{first['tailor_run_id']}/retry")

    assert response.status_code == 202
    body = response.json()
    assert body["ok"] is True
    assert body["retry_via"] == "user"
    assert body["status"] == "PENDING"
    assert body["job_hash"] == VALID_HASH
    assert isinstance(body["tailor_run_id"], int)
    assert body["tailor_run_id"] != first["tailor_run_id"]


def test_retry_in_opt_in_mode_soft_deletes_the_original_row(
    client: TestClient,
    tmp_path: Path,
) -> None:
    """The pre-existing row is soft-deleted before the new one is created."""

    db_path = tmp_path / "tailor_api.db"
    _seed_qualified_job(db_path, VALID_HASH)
    first = client.post(f"/api/jobs/{VALID_HASH}/tailor").json()
    _mark_run_failed(db_path, first["tailor_run_id"])

    retry_response = client.post(f"/api/tailor-runs/{first['tailor_run_id']}/retry")
    assert retry_response.status_code == 202

    # Re-deleting the original surfaces ALREADY_DELETED only when the
    # retry path actually performed the soft-delete.
    follow_up = client.delete(f"/api/tailor-runs/{first['tailor_run_id']}")
    assert follow_up.status_code == 404
    assert follow_up.json()["code"] == "TAILOR_RUN_ALREADY_DELETED"


def test_retry_in_both_mode_inserts_fresh_pending_row(
    client: TestClient,
    tmp_path: Path,
) -> None:
    """`both` mode behaves like opt_in for retry (user-triggered branch)."""

    db_path = tmp_path / "tailor_api.db"
    _seed_qualified_job(db_path, VALID_HASH)
    first = client.post(f"/api/jobs/{VALID_HASH}/tailor").json()
    _mark_run_failed(db_path, first["tailor_run_id"])
    _set_tailor_mode(db_path, "both")

    response = client.post(f"/api/tailor-runs/{first['tailor_run_id']}/retry")

    assert response.status_code == 202
    body = response.json()
    assert body["retry_via"] == "user"
    assert body["status"] == "PENDING"
    assert body["job_hash"] == VALID_HASH


def test_retry_in_autonomous_mode_returns_worker_envelope(
    client: TestClient,
    tmp_path: Path,
) -> None:
    """autonomous retry returns retry_via=worker and no new tailor_run_id."""

    db_path = tmp_path / "tailor_api.db"
    _seed_qualified_job(db_path, VALID_HASH)
    first = client.post(f"/api/jobs/{VALID_HASH}/tailor").json()
    _mark_run_failed(db_path, first["tailor_run_id"])
    _set_tailor_mode(db_path, "autonomous")

    response = client.post(f"/api/tailor-runs/{first['tailor_run_id']}/retry")

    assert response.status_code == 202
    body = response.json()
    assert body["ok"] is True
    assert body["retry_via"] == "worker"
    assert body["deleted_run_id"] == first["tailor_run_id"]
    assert body["job_hash"] == VALID_HASH
    assert "tailor_run_id" not in body


def test_retry_in_autonomous_mode_does_not_create_a_new_row(
    client: TestClient,
    tmp_path: Path,
) -> None:
    """The autonomous branch must not insert a fresh PENDING tailor_run."""

    db_path = tmp_path / "tailor_api.db"
    _seed_qualified_job(db_path, VALID_HASH)
    first = client.post(f"/api/jobs/{VALID_HASH}/tailor").json()
    _mark_run_failed(db_path, first["tailor_run_id"])
    _set_tailor_mode(db_path, "autonomous")

    client.post(f"/api/tailor-runs/{first['tailor_run_id']}/retry")

    async def _count() -> int:
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            conn = db._require_conn()
            cursor = await conn.execute(
                "SELECT COUNT(*) AS c FROM tailor_runs WHERE deleted_at IS NULL"
            )
            row = await cursor.fetchone()
            assert row is not None
            return int(row["c"])

    active_rows = asyncio.run(_count())
    assert active_rows == 0


def _force_job_status_qualified(db_path: Path, job_hash: str) -> None:
    """Set the seeded job's status to QUALIFIED so the worker can claim it."""

    async def _update() -> None:
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            conn = db._require_conn()
            await conn.execute(
                "UPDATE job_postings SET status = 'QUALIFIED' WHERE job_hash = ?",
                (job_hash,),
            )
            await conn.commit()

    asyncio.run(_update())


def test_retry_in_autonomous_mode_makes_job_claimable_again(
    client: TestClient,
    tmp_path: Path,
) -> None:
    """The soft-delete alone re-opens the job for the worker's next poll.

    Purpose:
        Locks the integration contract called out in the issue body: in
        autonomous mode the soft-delete IS the retry — `claim_next_tailor_job`
        must succeed against the same job after the retry, even with
        max_retries=1, because the FAILED row no longer counts.
    """

    db_path = tmp_path / "tailor_api.db"
    _seed_qualified_job(db_path, VALID_HASH)
    first = client.post(f"/api/jobs/{VALID_HASH}/tailor").json()
    _mark_run_failed(db_path, first["tailor_run_id"])
    _force_job_status_qualified(db_path, VALID_HASH)
    _set_tailor_mode(db_path, "autonomous")

    async def _claim_before() -> object:
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            return await db.claim_next_tailor_job(max_retries=1)

    pre_retry_claim = asyncio.run(_claim_before())
    assert pre_retry_claim is None

    retry_response = client.post(f"/api/tailor-runs/{first['tailor_run_id']}/retry")
    assert retry_response.status_code == 202

    async def _claim_after() -> object:
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            return await db.claim_next_tailor_job(max_retries=1)

    post_retry_claim = asyncio.run(_claim_after())
    assert post_retry_claim is not None


def test_retry_returns_409_when_budget_exceeded(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """opt_in retry honors the monthly budget guard."""

    db_path = tmp_path / "tailor_api.db"
    _seed_qualified_job(db_path, VALID_HASH)
    first = client.post(f"/api/jobs/{VALID_HASH}/tailor").json()
    _mark_run_failed(db_path, first["tailor_run_id"])

    async def _exceeded(self: object) -> bool:
        return True

    monkeypatch.setattr(
        "src.database._mixins.costs.CostsMixin.is_budget_exceeded",
        _exceeded,
    )

    response = client.post(f"/api/tailor-runs/{first['tailor_run_id']}/retry")

    assert response.status_code == 409
    assert response.json()["code"] == "BUDGET_EXCEEDED"


def test_retry_budget_check_skipped_in_autonomous_mode(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Autonomous retry bypasses the user-path budget guard.

    Purpose:
        Budget enforcement is a property of the user-triggered branch.
        Autonomous retries are a worker-claim concern handled elsewhere;
        the endpoint must not 409 on budget when retry_via=worker.
    """

    db_path = tmp_path / "tailor_api.db"
    _seed_qualified_job(db_path, VALID_HASH)
    first = client.post(f"/api/jobs/{VALID_HASH}/tailor").json()
    _mark_run_failed(db_path, first["tailor_run_id"])
    _set_tailor_mode(db_path, "autonomous")

    async def _exceeded(self: object) -> bool:
        return True

    monkeypatch.setattr(
        "src.database._mixins.costs.CostsMixin.is_budget_exceeded",
        _exceeded,
    )

    response = client.post(f"/api/tailor-runs/{first['tailor_run_id']}/retry")

    assert response.status_code == 202
    assert response.json()["retry_via"] == "worker"


def test_retry_in_opt_in_mode_schedules_background_pipeline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The user-triggered branch hands the new run to the BackgroundTask."""

    db_path = tmp_path / "tailor_api.db"
    monkeypatch.setattr(api_main, "resolve_database_path", lambda: db_path)

    scheduled: list[dict[str, object]] = []

    async def _capture_background(**kwargs: object) -> None:
        scheduled.append(kwargs)

    monkeypatch.setattr(
        tailor_runs_router,
        "_run_pipeline_background",
        _capture_background,
    )

    test_client = TestClient(api_main.app)
    _seed_qualified_job(db_path, VALID_HASH)
    first = test_client.post(f"/api/jobs/{VALID_HASH}/tailor").json()
    _mark_run_failed(db_path, first["tailor_run_id"])
    scheduled.clear()  # drop the original POST's scheduling event.

    retry_response = test_client.post(
        f"/api/tailor-runs/{first['tailor_run_id']}/retry"
    )
    assert retry_response.status_code == 202

    new_run_id = retry_response.json()["tailor_run_id"]
    assert len(scheduled) == 1
    assert scheduled[0]["tailor_run_id"] == new_run_id
    assert scheduled[0]["job_hash"] == VALID_HASH


def test_retry_in_autonomous_mode_does_not_schedule_background_pipeline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Autonomous retry must not queue the user-path pipeline task."""

    db_path = tmp_path / "tailor_api.db"
    monkeypatch.setattr(api_main, "resolve_database_path", lambda: db_path)

    scheduled: list[dict[str, object]] = []

    async def _capture_background(**kwargs: object) -> None:
        scheduled.append(kwargs)

    monkeypatch.setattr(
        tailor_runs_router,
        "_run_pipeline_background",
        _capture_background,
    )

    test_client = TestClient(api_main.app)
    _seed_qualified_job(db_path, VALID_HASH)
    first = test_client.post(f"/api/jobs/{VALID_HASH}/tailor").json()
    _mark_run_failed(db_path, first["tailor_run_id"])
    _set_tailor_mode(db_path, "autonomous")
    scheduled.clear()  # drop the original POST's scheduling event.

    retry_response = test_client.post(
        f"/api/tailor-runs/{first['tailor_run_id']}/retry"
    )
    assert retry_response.status_code == 202
    assert scheduled == []


def test_retry_cleans_up_artifact_directory(
    client: TestClient,
    tmp_path: Path,
) -> None:
    """A retry on a SUCCESS row removes the on-disk artifact directory."""

    db_path = tmp_path / "tailor_api.db"
    _seed_qualified_job(db_path, VALID_HASH)
    first = client.post(f"/api/jobs/{VALID_HASH}/tailor").json()

    artifact_dir = tmp_path / "artifacts" / VALID_HASH
    artifact_dir.mkdir(parents=True)
    pdf_path = artifact_dir / "resume.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 dummy")

    async def _mark_success() -> None:
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            await db.record_tailor_success(
                run_id=first["tailor_run_id"],
                artifact_yaml_path=str(artifact_dir / "r.yaml"),
                artifact_tex_path=str(artifact_dir / "r.tex"),
                artifact_pdf_path=str(pdf_path),
                page_count=1,
            )

    asyncio.run(_mark_success())
    assert artifact_dir.exists()

    response = client.post(f"/api/tailor-runs/{first['tailor_run_id']}/retry")
    assert response.status_code == 202
    assert not artifact_dir.exists()


def test_retry_swallows_artifact_cleanup_errors(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Filesystem failures during cleanup must not break the HTTP response."""

    db_path = tmp_path / "tailor_api.db"
    _seed_qualified_job(db_path, VALID_HASH)
    first = client.post(f"/api/jobs/{VALID_HASH}/tailor").json()

    artifact_dir = tmp_path / "broken" / VALID_HASH
    artifact_dir.mkdir(parents=True)

    async def _mark_success() -> None:
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            await db.record_tailor_success(
                run_id=first["tailor_run_id"],
                artifact_yaml_path=str(artifact_dir / "r.yaml"),
                artifact_tex_path=str(artifact_dir / "r.tex"),
                artifact_pdf_path=str(artifact_dir / "r.pdf"),
                page_count=1,
            )

    asyncio.run(_mark_success())

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk on fire")

    monkeypatch.setattr(shutil, "rmtree", _boom)

    response = client.post(f"/api/tailor-runs/{first['tailor_run_id']}/retry")

    assert response.status_code == 202
    assert response.json()["retry_via"] == "user"
