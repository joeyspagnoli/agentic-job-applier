"""Tests for tailor worker database methods and YAML baseline restore.

Purpose:
    Validate the tailor_runs schema migration, atomic claim logic, success
    and failure recording, stale-run cleanup, and YAML baseline restore
    behavior used by the autonomous tailor worker.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio

from src.database.db_manager import DatabaseManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db(tmp_path: Path) -> AsyncGenerator[DatabaseManager, None]:
    """Create a temporary database with base tables and tailor schema.

    Purpose:
        Provide a clean, isolated database for each test case with both
        the core schema and the tailor_runs table already migrated.
    Args:
        tmp_path: Pytest temporary directory fixture.
    Output:
        Yields a connected DatabaseManager instance.
    """

    db_path = str(tmp_path / "test.db")
    manager = DatabaseManager(db_path)
    await manager.connect()
    await manager.create_tables()
    await manager.migrate_agent_schema()
    await manager.migrate_tailor_schema()
    yield manager
    await manager.close()


async def _insert_qualified_job(db: DatabaseManager, job_hash: str) -> None:
    """Insert a minimal QUALIFIED job row for testing.

    Purpose:
        Provide a reusable helper that creates a job row in the state
        the tailor worker expects to claim from.
    Args:
        db: Connected database manager.
        job_hash: Unique hash for the test job.
    Output:
        Returns `None` after inserting and committing.
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
    await conn.commit()


# ---------------------------------------------------------------------------
# Schema migration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_migrate_tailor_schema_is_idempotent(db: DatabaseManager) -> None:
    """Verify that calling migrate_tailor_schema twice does not error.

    Purpose:
        Ensure the migration is safe for repeated startup execution.
    """

    await db.migrate_tailor_schema()
    await db.migrate_tailor_schema()

    conn = db._require_conn()
    cursor = await conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='tailor_runs'"
    )
    row = await cursor.fetchone()
    assert row is not None


# ---------------------------------------------------------------------------
# Claim logic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claim_returns_none_when_no_qualified_jobs(db: DatabaseManager) -> None:
    """Verify claim returns None when no QUALIFIED jobs exist.

    Purpose:
        Ensure the worker sleeps gracefully when there is nothing to do.
    """

    result = await db.claim_next_tailor_job(max_retries=2)
    assert result is None


@pytest.mark.asyncio
async def test_claim_returns_job_after_inserting_qualified(db: DatabaseManager) -> None:
    """Verify claim returns a job dict after inserting a QUALIFIED row.

    Purpose:
        Validate the happy-path claim flow end to end.
    """

    await _insert_qualified_job(db, "hash_abc")
    result = await db.claim_next_tailor_job(max_retries=2)

    assert result is not None
    assert result["job_hash"] == "hash_abc"
    assert "_tailor_run_id" in result
    run_id = result["_tailor_run_id"]
    assert isinstance(run_id, int)
    assert run_id > 0


@pytest.mark.asyncio
async def test_double_claim_same_lease_returns_none(db: DatabaseManager) -> None:
    """Verify claiming the same job twice within one lease returns None.

    Purpose:
        Validate the atomic claim prevents double-processing.
    """

    await _insert_qualified_job(db, "hash_double")
    first = await db.claim_next_tailor_job(max_retries=2)
    assert first is not None

    second = await db.claim_next_tailor_job(max_retries=2)
    assert second is None


# ---------------------------------------------------------------------------
# Success recording
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_success_excludes_from_future_claims(
    db: DatabaseManager,
) -> None:
    """Verify a SUCCESS run makes the job ineligible for future claims.

    Purpose:
        Ensure jobs are not re-tailored after a successful pipeline run.
    """

    await _insert_qualified_job(db, "hash_success")
    claimed = await db.claim_next_tailor_job(max_retries=2)
    assert claimed is not None
    assert isinstance(claimed["_tailor_run_id"], int)

    await db.record_tailor_success(
        run_id=claimed["_tailor_run_id"],
        artifact_yaml_path="/tmp/out.yaml",
        artifact_tex_path="/tmp/out.tex",
        artifact_pdf_path="/tmp/out.pdf",
        page_count=1,
    )

    next_claim = await db.claim_next_tailor_job(max_retries=2)
    assert next_claim is None


# ---------------------------------------------------------------------------
# Failure recording and retry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_failure_allows_retry_after_next_retry_at(
    db: DatabaseManager,
) -> None:
    """Verify a FAILED run allows re-claim after next_retry_at passes.

    Purpose:
        Validate the retry scheduling contract.
    """

    await _insert_qualified_job(db, "hash_retry")
    claimed = await db.claim_next_tailor_job(max_retries=3)
    assert claimed is not None
    assert isinstance(claimed["_tailor_run_id"], int)

    # Record failure with a retry time in the past so re-claim is immediate.
    await db.record_tailor_failure(
        run_id=claimed["_tailor_run_id"],
        error="test failure",
        next_retry_at="2000-01-01 00:00:00",
    )

    retry_claim = await db.claim_next_tailor_job(max_retries=3)
    assert retry_claim is not None
    assert retry_claim["job_hash"] == "hash_retry"


@pytest.mark.asyncio
async def test_max_retries_excludes_job(db: DatabaseManager) -> None:
    """Verify a job is excluded after max_retries FAILED runs.

    Purpose:
        Ensure the worker stops claiming terminally failed jobs.
    """

    max_retries = 2
    await _insert_qualified_job(db, "hash_terminal")

    for attempt in range(max_retries):
        claimed = await db.claim_next_tailor_job(max_retries=max_retries)
        assert claimed is not None, f"Expected claim on attempt {attempt}"
        assert isinstance(claimed["_tailor_run_id"], int)
        await db.record_tailor_failure(
            run_id=claimed["_tailor_run_id"],
            error=f"failure {attempt}",
            next_retry_at="2000-01-01 00:00:00",
        )

    # Now the job should be excluded.
    excluded = await db.claim_next_tailor_job(max_retries=max_retries)
    assert excluded is None


# ---------------------------------------------------------------------------
# Stale run cleanup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_stale_converts_old_pending_to_failed(
    db: DatabaseManager,
) -> None:
    """Verify stale PENDING runs are converted to FAILED on startup.

    Purpose:
        Validate crash recovery behavior.
    """

    await _insert_qualified_job(db, "hash_stale")
    claimed = await db.claim_next_tailor_job(max_retries=2)
    assert claimed is not None
    assert isinstance(claimed["_tailor_run_id"], int)

    # Backdate the started_at to make it stale.
    conn = db._require_conn()
    await conn.execute(
        "UPDATE tailor_runs SET started_at = datetime('now', '-9999 seconds') WHERE id = ?",
        (claimed["_tailor_run_id"],),
    )
    await conn.commit()

    stale_count = await db.mark_stale_tailor_runs_failed(lease_seconds=100)
    assert stale_count == 1

    # The job should now be reclaimable.
    reclaimed = await db.claim_next_tailor_job(max_retries=2)
    assert reclaimed is not None
    assert reclaimed["job_hash"] == "hash_stale"


# ---------------------------------------------------------------------------
# Reset failure state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_failure_state_allows_requeue(db: DatabaseManager) -> None:
    """Verify reset_tailor_failure_state makes a job reclaimable.

    Purpose:
        Validate the operator-facing requeue action.
    """

    await _insert_qualified_job(db, "hash_reset")

    # Exhaust retries.
    for _ in range(2):
        claimed = await db.claim_next_tailor_job(max_retries=2)
        assert claimed is not None
        assert isinstance(claimed["_tailor_run_id"], int)
        await db.record_tailor_failure(
            run_id=claimed["_tailor_run_id"],
            error="test",
            next_retry_at="2000-01-01 00:00:00",
        )

    excluded = await db.claim_next_tailor_job(max_retries=2)
    assert excluded is None

    # Reset and verify reclaimable.
    await db.reset_tailor_failure_state(job_hash="hash_reset")
    reclaimed = await db.claim_next_tailor_job(max_retries=2)
    assert reclaimed is not None
    assert reclaimed["job_hash"] == "hash_reset"


# ---------------------------------------------------------------------------
# YAML baseline restore
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_yaml_baseline_restored_after_tailor_once(
    db: DatabaseManager,
    tmp_path: Path,
) -> None:
    """Verify original YAML is untouched after _tailor_once with per-run temp copy.

    Purpose:
        Ensure the canonical resume YAML is never modified by the pipeline
        because the worker copies it to a per-run working file before invoking.
    """

    from scripts.process_qualified_jobs import _tailor_once

    await _insert_qualified_job(db, "a" * 32)

    # Create a test YAML file.
    yaml_path = tmp_path / "resume_content.yaml"
    original_content = "name: Test User\nsummary: Original baseline content\n"
    yaml_path.write_text(original_content, encoding="utf-8")

    output_dir = tmp_path / "output"
    output_dir.mkdir()

    # Mock the pipeline to simulate writing to the work copy, not the original.
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.final_page_count = 1
    mock_result.failure_reason = None

    from src.agents.resume_tailor_pi import TailorInvocationContract

    def fake_pipeline(*, invocation: TailorInvocationContract) -> MagicMock:
        """Simulate pipeline writing to the work copy, not the original.

        Purpose:
            Write tailored content to the invocation's work YAML to verify
            the original file is untouched when using per-run temp copies.
        Args:
            invocation: TailorInvocationContract with resume_yaml_path set
                to the per-run work copy.
        Output:
            Returns a mock TailorRunResult with success=True.
        """

        # Write to the work copy (what the real pipeline would do).
        Path(invocation.resume_yaml_path).write_text(
            "name: TAILORED CONTENT\n", encoding="utf-8"
        )
        return mock_result

    with patch(
        "scripts.process_qualified_jobs.run_resume_tailor_pipeline",
        side_effect=fake_pipeline,
    ):
        processed = await _tailor_once(
            db=db,
            output_base_dir=output_dir,
            resume_yaml_path=yaml_path,
            max_retries=2,
            lease_seconds=7200,
            backoff_seconds=600,
            backoff_multiplier=2,
        )

    assert processed == 1
    restored_content = yaml_path.read_text(encoding="utf-8")
    assert restored_content == original_content
