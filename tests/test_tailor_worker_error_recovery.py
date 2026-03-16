"""Tests for tailor worker error recovery in exception and I/O failure paths.

Purpose:
    Validate that the tailor worker correctly handles DB failures during
    error recovery, YAML copy failures, and record_tailor_failure failures.
    These tests cover the production crash paths identified in H-005, M-003.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest
import pytest_asyncio

from scripts.process_qualified_jobs import _tailor_once
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
    Arg(s):
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
    Arg(s):
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
# Test: DB failure during error recovery logs original error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_db_failure_during_error_recovery_logs_original_error(
    db: DatabaseManager,
    tmp_path: Path,
) -> None:
    """Verify DB failure during get_tailor_failure_count falls back to terminal.

    Purpose:
        Validate H-005: when the secondary DB query fails during exception
        recovery, the worker treats the failure as terminal and still calls
        record_tailor_failure without propagating a new exception.
    """

    job_hash = "a" * 32
    await _insert_qualified_job(db, job_hash)

    yaml_path = tmp_path / "resume_content.yaml"
    yaml_path.write_text("name: Test\n", encoding="utf-8")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    def fake_pipeline(*, invocation: object) -> MagicMock:
        """Raise to trigger the exception recovery path.

        Purpose:
            Simulate a pipeline crash to exercise the except handler.
        Arg(s):
            invocation: Unused pipeline contract.
        Output:
            Raises RuntimeError unconditionally.
        """
        raise RuntimeError("pipeline exploded")

    record_failure_calls: list[dict] = []
    original_record = db.record_tailor_failure

    async def tracking_record_failure(**kwargs: object) -> None:
        """Wrap record_tailor_failure to capture call arguments.

        Purpose:
            Intercept record_tailor_failure to assert it was called correctly
            even after get_tailor_failure_count raises.
        Arg(s):
            **kwargs: Forwarded keyword arguments for the real method.
        Output:
            Returns None after recording the call and delegating.
        """
        record_failure_calls.append(dict(kwargs))
        await original_record(**kwargs)  # type: ignore[arg-type]

    db.record_tailor_failure = tracking_record_failure  # type: ignore[method-assign]

    with patch.object(
        db,
        "get_tailor_failure_count",
        side_effect=aiosqlite.OperationalError("connection lost"),
    ), patch(
        "scripts.process_qualified_jobs.run_resume_tailor_pipeline",
        side_effect=fake_pipeline,
    ):
        result = await _tailor_once(
            db=db,
            output_base_dir=output_dir,
            resume_yaml_path=yaml_path,
            max_retries=3,
            lease_seconds=7200,
            backoff_seconds=600,
            backoff_multiplier=2,
        )

    assert result == 0
    assert len(record_failure_calls) == 1
    assert "pipeline exploded" in record_failure_calls[0]["error"]


# ---------------------------------------------------------------------------
# Test: YAML copy failure records failure and returns zero
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_yaml_copy_failure_records_failure_and_returns_zero(
    db: DatabaseManager,
    tmp_path: Path,
) -> None:
    """Verify a missing YAML source causes record_tailor_failure and returns 0.

    Purpose:
        Validate M-003: when shutil.copy2 raises OSError because the source
        YAML does not exist, the worker records failure and returns 0 without
        crashing.
    """

    job_hash = "b" * 32
    await _insert_qualified_job(db, job_hash)

    # Point to a YAML that does not exist.
    yaml_path = tmp_path / "nonexistent_resume.yaml"
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    record_failure_calls: list[dict] = []
    original_record = db.record_tailor_failure

    async def tracking_record_failure(**kwargs: object) -> None:
        """Intercept record_tailor_failure to capture arguments.

        Purpose:
            Verify the failure was recorded with the expected error prefix.
        Arg(s):
            **kwargs: Forwarded keyword arguments for the real method.
        Output:
            Returns None after recording the call and delegating.
        """
        record_failure_calls.append(dict(kwargs))
        await original_record(**kwargs)  # type: ignore[arg-type]

    db.record_tailor_failure = tracking_record_failure  # type: ignore[method-assign]

    result = await _tailor_once(
        db=db,
        output_base_dir=output_dir,
        resume_yaml_path=yaml_path,
        max_retries=3,
        lease_seconds=7200,
        backoff_seconds=600,
        backoff_multiplier=2,
    )

    assert result == 0
    assert len(record_failure_calls) == 1
    assert record_failure_calls[0]["error"].startswith("yaml_copy_failed:")


# ---------------------------------------------------------------------------
# Test: record_tailor_failure exception is logged gracefully
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_tailor_failure_exception_is_logged_gracefully(
    db: DatabaseManager,
    tmp_path: Path,
) -> None:
    """Verify record_tailor_failure raising does not propagate out of _tailor_once.

    Purpose:
        Validate H-005: if record_tailor_failure itself raises, _tailor_once
        must not re-raise and must still return 0 gracefully.
    """

    job_hash = "c" * 32
    await _insert_qualified_job(db, job_hash)

    yaml_path = tmp_path / "resume_content.yaml"
    yaml_path.write_text("name: Test\n", encoding="utf-8")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    def fake_pipeline(*, invocation: object) -> MagicMock:
        """Raise to trigger the exception recovery path.

        Purpose:
            Simulate a pipeline crash so _handle_tailor_failure is invoked.
        Arg(s):
            invocation: Unused pipeline contract.
        Output:
            Raises RuntimeError unconditionally.
        """
        raise RuntimeError("crash")

    with patch.object(
        db,
        "record_tailor_failure",
        side_effect=aiosqlite.OperationalError("db dead"),
    ), patch(
        "scripts.process_qualified_jobs.run_resume_tailor_pipeline",
        side_effect=fake_pipeline,
    ):
        result = await _tailor_once(
            db=db,
            output_base_dir=output_dir,
            resume_yaml_path=yaml_path,
            max_retries=3,
            lease_seconds=7200,
            backoff_seconds=600,
            backoff_multiplier=2,
        )

    assert result == 0


# ---------------------------------------------------------------------------
# Test: YAML copy failure with missing file records failure_reason
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_yaml_copy_failure_with_missing_file_records_failure(
    db: DatabaseManager,
    tmp_path: Path,
) -> None:
    """Verify the failure_reason contains 'yaml_copy_failed' when YAML is absent.

    Purpose:
        Validate M-003: the error stored in tailor_runs starts with
        'yaml_copy_failed:' so operators can identify YAML I/O issues.
    """

    job_hash = "d" * 32
    await _insert_qualified_job(db, job_hash)

    # YAML path does not exist — shutil.copy2 will raise FileNotFoundError.
    yaml_path = tmp_path / "missing.yaml"
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    result = await _tailor_once(
        db=db,
        output_base_dir=output_dir,
        resume_yaml_path=yaml_path,
        max_retries=3,
        lease_seconds=7200,
        backoff_seconds=600,
        backoff_multiplier=2,
    )

    assert result == 0

    runs = await db.get_tailor_runs_for_job(job_hash)
    assert len(runs) == 1
    assert runs[0]["status"] == "FAILED"
    assert runs[0]["error"].startswith("yaml_copy_failed:")
