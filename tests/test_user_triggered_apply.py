"""End-to-end tests for the user-triggered apply path (Bug 4).

Three contracts are locked here:

1. ``enqueue_apply_run_for_job`` returns a merged row that
   ``_process_apply_row`` can consume directly — no second JOIN.
2. ``claim_next_apply_job`` never re-claims a PENDING row that already
   has a ``claim_token`` (so the autonomous loop cannot duplicate a
   user-triggered enqueue or its own in-flight rows).
3. ``POST /api/jobs/{hash}/apply`` returns 200 immediately and the
   spawned background task drives the apply row to a terminal state
   without the poll loop ticking.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from src.agents.apply_worker.schemas import (
    ApplyOutcome,
    ApplyRunResult,
    ATSPlatform,
)
from src.database.db_manager import DatabaseManager


JOB_HASH = "a" * 40  # 40 hex chars passes _validate_job_hash.


async def _seed_review_for_job(
    db: DatabaseManager,
    *,
    job_hash: str,
    tmp_path: Path,
) -> int:
    """Insert one SUCCESS review_run + parent job so apply enqueue works.

    Args:
        db: Connected database manager.
        job_hash: Job hash to seed.
        tmp_path: Pytest tmp dir for the fake PDF path.
    Returns:
        The review_run primary key.
    """

    conn = db._require_conn()
    await conn.execute(
        """
        INSERT INTO job_postings (
            job_hash, title, company, location, source_url, description,
            status, source
        )
        VALUES (?, 'Eng', 'TestCo', 'Remote', 'https://example.com', '',
                'QUALIFIED', 'TEST')
        ON CONFLICT(job_hash) DO NOTHING
        """,
        (job_hash,),
    )
    tailor_cursor = await conn.execute(
        "INSERT INTO tailor_runs (job_hash, status) VALUES (?, 'SUCCESS') RETURNING id",
        (job_hash,),
    )
    tailor_row = await tailor_cursor.fetchone()
    assert tailor_row is not None
    tailor_run_id = int(tailor_row["id"])

    pdf_path = tmp_path / "tailored.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 stub")
    review_id = await db.insert_pipeline_review_run(
        job_hash=job_hash,
        tailor_run_id=tailor_run_id,
        verdict="TAILORED",
        selected_yaml_path=None,
        selected_tex_path=None,
        selected_pdf_path=str(pdf_path),
        review_report_json=None,
        fallback_base_yaml_path=None,
        fallback_base_tex_path=None,
        fallback_base_pdf_path=None,
    )
    await conn.commit()
    return review_id


@pytest.mark.asyncio
async def test_enqueue_apply_run_returns_merged_row_with_claim_token(
    tmp_path: Path,
) -> None:
    """``enqueue_apply_run_for_job`` emits a worker-ready merged row.

    Purpose:
        Lock the Bug 4 contract — the row carries every key
        ``_process_apply_row`` reads, plus the new ``_apply_*``
        keys that prove a claim_token is set.
    """

    db_path = tmp_path / "jobs.db"
    async with DatabaseManager(str(db_path)) as db:
        await db.create_tables()
        await _seed_review_for_job(db, job_hash=JOB_HASH, tmp_path=tmp_path)

        merged = await db.enqueue_apply_run_for_job(job_hash=JOB_HASH)

    # Worker-ready keys.
    for required_key in (
        "job_hash",
        "source_url",
        "title",
        "company",
        "description",
        "review_run_id",
        "review_verdict",
        "selected_pdf_path",
        "_apply_run_id",
        "_apply_claim_token",
        "status",
    ):
        assert required_key in merged, f"missing key {required_key!r}"

    assert merged["job_hash"] == JOB_HASH
    assert merged["status"] == "PENDING"
    assert isinstance(merged["_apply_run_id"], int) and merged["_apply_run_id"] > 0
    assert (
        isinstance(merged["_apply_claim_token"], str)
        and len(merged["_apply_claim_token"]) == 64
    )


@pytest.mark.asyncio
async def test_claim_next_apply_job_skips_rows_with_claim_token(
    tmp_path: Path,
) -> None:
    """Bug 4: a user-enqueued PENDING row is never re-claimed.

    Purpose:
        The autonomous poll loop and the user-triggered endpoint share
        the same table. Without the ``claim_token IS NOT NULL``
        exclusion the loop would INSERT a duplicate row once the
        user-enqueued one slid past the lease window.
    """

    db_path = tmp_path / "jobs.db"
    async with DatabaseManager(str(db_path)) as db:
        await db.create_tables()
        await _seed_review_for_job(db, job_hash=JOB_HASH, tmp_path=tmp_path)

        merged = await db.enqueue_apply_run_for_job(job_hash=JOB_HASH)
        assert merged["_apply_run_id"] > 0

        claimed = await db.claim_next_apply_job(max_retries=2, lease_seconds=60)
        assert claimed is None, (
            "Bug 4 regression: claim_next_apply_job should NOT pick up "
            "a PENDING row that already has a claim_token."
        )


@pytest.mark.asyncio
async def test_process_apply_row_drives_user_enqueued_row_to_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The merged row from enqueue feeds straight into ``_process_apply_row``.

    Purpose:
        Prove the shared body works for the user-triggered path. We
        bypass the real browser by stubbing ``apply_to_job`` with a
        success ``ApplyRunResult`` so the test runs deterministically.
    """

    import src.workers.apply as process_apply_jobs

    async def _stub_apply_to_job(**_kwargs: object) -> ApplyRunResult:
        return ApplyRunResult(
            success=True,
            outcome=ApplyOutcome.SUBMITTED,
            confidence_score=0.95,
            confidence_report=None,
            resume_pdf_path=None,
            resume_source="TAILORED",
            screenshot_path=str(tmp_path / "screenshot.png"),
            dom_snapshot_path=str(tmp_path / "dom.html"),
            unresolved_fields=[],
            ats_platform=ATSPlatform.GREENHOUSE,
            page_url="https://example.com/apply",
            finisher_diagnostics=None,
            deferred_questions=[],
        )

    monkeypatch.setattr(process_apply_jobs, "apply_to_job", _stub_apply_to_job)

    db_path = tmp_path / "jobs.db"
    async with DatabaseManager(str(db_path)) as db:
        await db.create_tables()
        await _seed_review_for_job(db, job_hash=JOB_HASH, tmp_path=tmp_path)

        merged = await db.enqueue_apply_run_for_job(job_hash=JOB_HASH)
        result_count = await process_apply_jobs._process_apply_row(
            db=db,
            output_base_dir=tmp_path,
            cdp_url="http://localhost:9222",
            claimed_row=merged,
            max_retries=2,
            backoff_seconds=10,
            backoff_multiplier=2,
            dry_run=False,
        )
        assert result_count == 1

        # Row should be SUCCESS with the outcome we returned.
        row = await db.get_apply_run(int(merged["_apply_run_id"]))
        assert row is not None
        assert row["status"] == "SUCCESS"
        assert row["outcome"] == ApplyOutcome.SUBMITTED.value


@pytest.mark.asyncio
async def test_post_apply_endpoint_spawns_background_task(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``POST /api/jobs/{hash}/apply`` kicks off the task before returning.

    Purpose:
        Bug 4 integration guard — the endpoint must `asyncio.create_task`
        the apply flow so the dashboard sees state change in <90 s
        without the poll loop ticking. We replace `_spawn_user_apply_task`
        with a stub that flips the row to SUCCESS to keep the test fast
        and deterministic.
    """

    from api.routers import apply_runs as apply_runs_router
    from api import main as api_main

    db_path = tmp_path / "jobs.db"
    monkeypatch.setattr(api_main, "resolve_database_path", lambda: db_path)

    async with DatabaseManager(str(db_path)) as db:
        await db.create_tables()
        await _seed_review_for_job(db, job_hash=JOB_HASH, tmp_path=tmp_path)

    task_completed = asyncio.Event()
    captured_run_id: list[int] = []

    async def _stub_spawn(
        *,
        db_path: str,
        merged_row: dict[str, Any],
    ) -> None:
        """Flip the row to SUCCESS so the test can observe the transition."""

        run_id = int(merged_row["_apply_run_id"])
        captured_run_id.append(run_id)
        async with DatabaseManager(db_path) as inner_db:
            await inner_db.create_tables()
            await inner_db.record_apply_success(
                run_id=run_id,
                claim_token=str(merged_row["_apply_claim_token"]),
                outcome=ApplyOutcome.SUBMITTED.value,
                resume_pdf_path=str(merged_row["selected_pdf_path"]),
                resume_source="TAILORED",
                confidence_score=0.9,
                confidence_report_json=None,
                screenshot_path=None,
                dom_snapshot_path=None,
                unresolved_fields_json=None,
                simplify_autofill_detected=True,
                ats_platform=ATSPlatform.GREENHOUSE.value,
                page_url="https://example.com/apply",
            )
        task_completed.set()

    monkeypatch.setattr(apply_runs_router, "_spawn_user_apply_task", _stub_spawn)

    response = await apply_runs_router.enqueue_apply_run(job_hash=JOB_HASH)
    assert response["status"] == "PENDING"
    assert response["ok"] is True
    assert response["apply_run_id"] == response["run_id"]
    assert response["job_hash"] == JOB_HASH

    # Let the spawned task run; bounded wait so a regression on the
    # spawn path fails fast instead of hanging the suite.
    await asyncio.wait_for(task_completed.wait(), timeout=3.0)
    run_id_value = response["run_id"]
    assert isinstance(run_id_value, int)
    assert captured_run_id == [run_id_value]

    # Final state is SUCCESS, observable via the same GET endpoint
    # the dashboard polls.
    get_response = await apply_runs_router.get_apply_run(run_id=run_id_value)
    assert get_response["ok"] is True
    apply_payload = get_response["apply_run"]
    assert isinstance(apply_payload, dict)
    assert apply_payload["status"] == "SUCCESS"
    assert apply_payload["outcome"] == ApplyOutcome.SUBMITTED.value
