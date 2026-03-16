"""Tests for tailor worker input validation.

Purpose:
    Validate that job_hash values are sanitized before filesystem operations
    to prevent path traversal attacks, and that max_retries validation guards
    the claim entry point.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import patch

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
    """Insert a minimal QUALIFIED job row using a safe hash for DB insertion.

    Purpose:
        Create a reclaimable job row so claim_next_tailor_job returns a result
        whose job_hash can be patched for validation testing.
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
# Test: path traversal job_hash is rejected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_path_traversal_job_hash_rejected(
    db: DatabaseManager,
    tmp_path: Path,
) -> None:
    """Verify a path-traversal job_hash is rejected before any FS operation.

    Purpose:
        Validate C-001: a job_hash containing '../' path separators is caught
        by _validate_job_hash before the output directory is created, and no
        directory outside output_base_dir is written.
    """

    safe_hash = "a" * 32
    await _insert_qualified_job(db, safe_hash)

    yaml_path = tmp_path / "resume_content.yaml"
    yaml_path.write_text("name: Test\n", encoding="utf-8")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    evil_hash = "../../etc/cron.d/evil"
    evil_job = {
        "job_hash": evil_hash,
        "_tailor_run_id": 99,
        "_tailor_claim_token": "tok",
    }

    with patch.object(db, "claim_next_tailor_job", return_value=evil_job), patch.object(
        db, "record_tailor_failure"
    ) as mock_record:
        result = await _tailor_once(
            db=db,
            output_base_dir=output_dir,
            resume_yaml_path=yaml_path,
            max_retries=2,
            lease_seconds=7200,
            backoff_seconds=600,
            backoff_multiplier=2,
        )

    assert result == 0
    mock_record.assert_called_once()
    # Confirm no directory traversal occurred outside output_dir.
    traversal_target = tmp_path / "etc" / "cron.d" / "evil"
    assert not traversal_target.exists()


# ---------------------------------------------------------------------------
# Test: job_hash with null bytes is rejected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_job_hash_with_null_bytes_rejected(
    db: DatabaseManager,
    tmp_path: Path,
) -> None:
    """Verify a job_hash containing null bytes is rejected.

    Purpose:
        Validate C-001: null bytes in a hash value are rejected by
        _validate_job_hash before any filesystem operation occurs.
    """

    safe_hash = "b" * 32
    await _insert_qualified_job(db, safe_hash)

    yaml_path = tmp_path / "resume_content.yaml"
    yaml_path.write_text("name: Test\n", encoding="utf-8")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    null_byte_job = {
        "job_hash": "abc\x00def",
        "_tailor_run_id": 100,
        "_tailor_claim_token": "tok",
    }

    with patch.object(db, "claim_next_tailor_job", return_value=null_byte_job), patch.object(
        db, "record_tailor_failure"
    ) as mock_record:
        result = await _tailor_once(
            db=db,
            output_base_dir=output_dir,
            resume_yaml_path=yaml_path,
            max_retries=2,
            lease_seconds=7200,
            backoff_seconds=600,
            backoff_multiplier=2,
        )

    assert result == 0
    mock_record.assert_called_once()


# ---------------------------------------------------------------------------
# Test: job_hash with spaces is rejected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_job_hash_with_spaces_rejected(
    db: DatabaseManager,
    tmp_path: Path,
) -> None:
    """Verify a job_hash containing spaces is rejected.

    Purpose:
        Validate C-001: spaces in a hash value are rejected by
        _validate_job_hash before any filesystem operation occurs.
    """

    safe_hash = "c" * 32
    await _insert_qualified_job(db, safe_hash)

    yaml_path = tmp_path / "resume_content.yaml"
    yaml_path.write_text("name: Test\n", encoding="utf-8")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    spaced_job = {
        "job_hash": "abc def",
        "_tailor_run_id": 101,
        "_tailor_claim_token": "tok",
    }

    with patch.object(db, "claim_next_tailor_job", return_value=spaced_job), patch.object(
        db, "record_tailor_failure"
    ) as mock_record:
        result = await _tailor_once(
            db=db,
            output_base_dir=output_dir,
            resume_yaml_path=yaml_path,
            max_retries=2,
            lease_seconds=7200,
            backoff_seconds=600,
            backoff_multiplier=2,
        )

    assert result == 0
    mock_record.assert_called_once()


# ---------------------------------------------------------------------------
# Test: max_retries=0 raises ValueError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_max_retries_zero_raises_value_error(db: DatabaseManager) -> None:
    """Verify claim_next_tailor_job raises ValueError when max_retries=0.

    Purpose:
        Validate M-007: the guard at the start of claim_next_tailor_job
        rejects zero as a nonsensical retry limit.
    """

    with pytest.raises(ValueError, match="max_retries must be at least 1"):
        await db.claim_next_tailor_job(max_retries=0)


# ---------------------------------------------------------------------------
# Test: max_retries=-1 raises ValueError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_max_retries_negative_raises_value_error(db: DatabaseManager) -> None:
    """Verify claim_next_tailor_job raises ValueError when max_retries=-1.

    Purpose:
        Validate M-007: the guard at the start of claim_next_tailor_job
        rejects negative values as nonsensical retry limits.
    """

    with pytest.raises(ValueError, match="max_retries must be at least 1"):
        await db.claim_next_tailor_job(max_retries=-1)
