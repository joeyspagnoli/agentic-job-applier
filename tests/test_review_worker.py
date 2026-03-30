"""Tests for review worker database methods and claim lifecycle.

Purpose:
    Validate review_runs migration, claim logic, success/failure recording,
    stale-run cleanup, and retry behavior for post-tailor review stage.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio

from src.database.db_manager import ClaimOwnershipError
from src.database.db_manager import DatabaseManager


@pytest_asyncio.fixture
async def db(tmp_path: Path) -> AsyncGenerator[DatabaseManager, None]:
    """Create temporary database with migrated tailor and review schemas.

    Purpose:
        Provide isolated DB manager fixture for review-worker lifecycle tests.
    Args:
        tmp_path: Pytest temporary directory fixture.
    Output:
        Yields connected `DatabaseManager` and closes connection afterward.
    """

    database_path = str(tmp_path / "test.db")
    manager = DatabaseManager(database_path)
    await manager.connect()
    await manager.create_tables()
    await manager.migrate_agent_schema()
    await manager.migrate_tailor_schema()
    await manager.migrate_review_schema()
    yield manager
    await manager.close()


async def _insert_successful_tailor_job(
    db: DatabaseManager,
    *,
    job_hash: str,
    tailor_run_id: int = 1,
) -> None:
    """Insert a QUALIFIED job row and matching SUCCESS tailor run.

    Purpose:
        Build deterministic review-claim test data in one helper.
    Args:
        db: Connected DB manager.
        job_hash: Job hash used for inserted rows.
        tailor_run_id: Explicit tailor run ID for predictable assertions.
    Output:
        Returns `None` after data insertion.
    """

    conn = db._require_conn()
    await conn.execute(
        """
        INSERT INTO job_postings (
            job_hash, source, source_url, company, title, status
        ) VALUES (?, 'test', 'https://example.com', 'TestCo', 'Engineer', 'QUALIFIED')
        """,
        (job_hash,),
    )
    await conn.execute(
        """
        INSERT INTO tailor_runs (
            id, job_hash, status, artifact_yaml_path, artifact_tex_path, artifact_pdf_path
        ) VALUES (?, ?, 'SUCCESS', ?, ?, ?)
        """,
        (
            tailor_run_id,
            job_hash,
            f"/tmp/{job_hash}.yaml",
            f"/tmp/{job_hash}.tex",
            f"/tmp/{job_hash}.pdf",
        ),
    )
    await conn.commit()


@pytest.mark.asyncio
async def test_migrate_review_schema_is_idempotent(db: DatabaseManager) -> None:
    """Verify repeated review schema migration calls remain safe.

    Purpose:
        Ensure startup migration can run repeatedly without errors.
    Args:
        db: Migrated DB fixture.
    Output:
        Returns `None`; test passes when table remains present.
    """

    await db.migrate_review_schema()
    await db.migrate_review_schema()

    conn = db._require_conn()
    cursor = await conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='review_runs'"
    )
    row = await cursor.fetchone()
    assert row is not None


@pytest.mark.asyncio
async def test_claim_next_review_job_returns_none_when_no_tailor_success(
    db: DatabaseManager,
) -> None:
    """Verify claim returns None when no eligible tailor success exists.

    Purpose:
        Ensure review worker can idle safely when queue is empty.
    Args:
        db: Migrated DB fixture.
    Output:
        Returns `None`; test passes when claim returns None.
    """

    claimed = await db.claim_next_review_job(max_retries=2)
    assert claimed is None


@pytest.mark.asyncio
async def test_claim_next_review_job_claims_successful_tailor_run(
    db: DatabaseManager,
) -> None:
    """Verify claim returns row for successful tailor candidate.

    Purpose:
        Validate atomic review claim contract for eligible tailor success rows.
    Args:
        db: Migrated DB fixture.
    Output:
        Returns `None`; test passes when claim contains review metadata keys.
    """

    await _insert_successful_tailor_job(db, job_hash="a" * 32, tailor_run_id=5)

    claimed = await db.claim_next_review_job(max_retries=2)

    assert claimed is not None
    assert claimed["job_hash"] == "a" * 32
    assert claimed["tailor_run_id"] == 5
    review_run_id = claimed["_review_run_id"]
    assert isinstance(review_run_id, int)
    assert review_run_id > 0
    assert isinstance(claimed["_review_claim_token"], str)
    assert claimed["_review_claim_token"] != ""


@pytest.mark.asyncio
async def test_record_review_success_excludes_tailor_run_from_future_claims(
    db: DatabaseManager,
) -> None:
    """Verify SUCCESS review prevents duplicate future claims.

    Purpose:
        Ensure completed review runs are not re-claimed by worker.
    Args:
        db: Migrated DB fixture.
    Output:
        Returns `None`; test passes when second claim returns None.
    """

    await _insert_successful_tailor_job(db, job_hash="b" * 32, tailor_run_id=8)
    claimed = await db.claim_next_review_job(max_retries=2)
    assert claimed is not None
    review_run_id_raw = claimed["_review_run_id"]
    review_claim_token_raw = claimed["_review_claim_token"]
    assert isinstance(review_run_id_raw, int)
    assert isinstance(review_claim_token_raw, str)

    await db.record_review_success(
        run_id=review_run_id_raw,
        claim_token=review_claim_token_raw,
        verdict="BASE",
        selected_yaml_path="/tmp/base.yaml",
        selected_tex_path="/tmp/base.tex",
        selected_pdf_path="/tmp/base.pdf",
        review_report_json='{"verdict":"BASE"}',
        agent_stdout="stdout",
        agent_stderr="",
    )

    next_claim = await db.claim_next_review_job(max_retries=2)
    assert next_claim is None


@pytest.mark.asyncio
async def test_review_failure_retry_allows_reclaim_after_schedule(
    db: DatabaseManager,
) -> None:
    """Verify FAILED review run can be reclaimed after retry window.

    Purpose:
        Validate retry scheduling behavior for transient runtime failures.
    Args:
        db: Migrated DB fixture.
    Output:
        Returns `None`; test passes when reclaim occurs after past retry time.
    """

    await _insert_successful_tailor_job(db, job_hash="c" * 32, tailor_run_id=9)
    claimed = await db.claim_next_review_job(max_retries=3)
    assert claimed is not None
    review_run_id_raw = claimed["_review_run_id"]
    review_claim_token_raw = claimed["_review_claim_token"]
    assert isinstance(review_run_id_raw, int)
    assert isinstance(review_claim_token_raw, str)

    await db.record_review_failure(
        run_id=review_run_id_raw,
        claim_token=review_claim_token_raw,
        error="runtime_timeout",
        next_retry_at="2000-01-01 00:00:00",
        agent_stdout="",
        agent_stderr="timeout",
        fallback_base_yaml_path="/tmp/base.yaml",
        fallback_base_tex_path="/tmp/base.tex",
        fallback_base_pdf_path="/tmp/base.pdf",
    )

    reclaimed = await db.claim_next_review_job(max_retries=3)
    assert reclaimed is not None
    assert reclaimed["tailor_run_id"] == 9


@pytest.mark.asyncio
async def test_record_review_success_rejects_invalid_claim_token(
    db: DatabaseManager,
) -> None:
    """Verify review success writes require the active claim token.

    Purpose:
        Regress H-004 by ensuring stale workers cannot finalize review rows
        after losing ownership of the pending claim.
    Args:
        db: Migrated DB fixture.
    Output:
        Returns `None`; test passes when mismatched token raises ownership error.
    """

    await _insert_successful_tailor_job(db, job_hash="e" * 32, tailor_run_id=11)
    claimed = await db.claim_next_review_job(max_retries=2)
    assert claimed is not None
    review_run_id_raw = claimed["_review_run_id"]
    assert isinstance(review_run_id_raw, int)

    with pytest.raises(ClaimOwnershipError):
        await db.record_review_success(
            run_id=review_run_id_raw,
            claim_token="invalid-token",
            verdict="BASE",
            selected_yaml_path="/tmp/base.yaml",
            selected_tex_path="/tmp/base.tex",
            selected_pdf_path="/tmp/base.pdf",
            review_report_json='{"verdict":"BASE"}',
            agent_stdout="stdout",
            agent_stderr="",
        )


@pytest.mark.asyncio
async def test_record_review_failure_rejects_invalid_claim_token(
    db: DatabaseManager,
) -> None:
    """Verify review failure writes require the active claim token.

    Purpose:
        Regress H-004 by preventing stale workers from writing FAILED rows for
        claims they no longer own.
    Args:
        db: Migrated DB fixture.
    Output:
        Returns `None`; test passes when mismatched token raises ownership error.
    """

    await _insert_successful_tailor_job(db, job_hash="f" * 32, tailor_run_id=12)
    claimed = await db.claim_next_review_job(max_retries=2)
    assert claimed is not None
    review_run_id_raw = claimed["_review_run_id"]
    assert isinstance(review_run_id_raw, int)

    with pytest.raises(ClaimOwnershipError):
        await db.record_review_failure(
            run_id=review_run_id_raw,
            claim_token="invalid-token",
            error="runtime_timeout",
            next_retry_at="2000-01-01 00:00:00",
            agent_stdout="",
            agent_stderr="timeout",
            fallback_base_yaml_path="/tmp/base.yaml",
            fallback_base_tex_path="/tmp/base.tex",
            fallback_base_pdf_path="/tmp/base.pdf",
        )


@pytest.mark.asyncio
async def test_mark_stale_review_runs_failed_recovers_claimability(
    db: DatabaseManager,
) -> None:
    """Verify stale PENDING review rows are converted to FAILED.

    Purpose:
        Validate startup crash-recovery behavior for review worker claims.
    Args:
        db: Migrated DB fixture.
    Output:
        Returns `None`; test passes when stale row cleanup enables reclaim.
    """

    await _insert_successful_tailor_job(db, job_hash="d" * 32, tailor_run_id=10)
    claimed = await db.claim_next_review_job(max_retries=2)
    assert claimed is not None

    conn = db._require_conn()
    await conn.execute(
        "UPDATE review_runs SET started_at = datetime('now', '-9999 seconds') WHERE id = ?",
        (claimed["_review_run_id"],),
    )
    await conn.commit()

    stale_count = await db.mark_stale_review_runs_failed(lease_seconds=100)
    assert stale_count == 1

    reclaimed = await db.claim_next_review_job(max_retries=2)
    assert reclaimed is not None
    assert reclaimed["tailor_run_id"] == 10
