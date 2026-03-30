"""Tests for tailor worker YAML baseline isolation.

Purpose:
    Validate that the per-run working copy approach ensures the canonical
    resume YAML is never modified by the pipeline, whether the run succeeds,
    fails, or the source YAML is unavailable.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio

from scripts.process_qualified_jobs import _tailor_once
from src.agents.resume_tailor_pi import TailorInvocationContract
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
# Test: YAML unchanged after successful pipeline run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_yaml_unchanged_after_successful_pipeline_run(
    db: DatabaseManager,
    tmp_path: Path,
) -> None:
    """Verify the original YAML is untouched after a successful pipeline run.

    Purpose:
        Validate that using a per-run working copy means the canonical YAML
        is never modified even when the pipeline writes tailored content.
    """

    job_hash = "a" * 32
    await _insert_qualified_job(db, job_hash)

    yaml_path = tmp_path / "resume_content.yaml"
    original_content = "name: Test User\nsummary: Original\n"
    yaml_path.write_text(original_content, encoding="utf-8")

    output_dir = tmp_path / "output"
    output_dir.mkdir()

    mock_result = MagicMock()
    mock_result.success = True
    mock_result.final_page_count = 1
    mock_result.failure_reason = None

    def fake_pipeline(*, invocation: TailorInvocationContract) -> MagicMock:
        """Write tailored content to the work copy path.

        Purpose:
            Simulate the real pipeline modifying the working YAML to confirm
            the canonical file is not the one being written.
        Arg(s):
            invocation: TailorInvocationContract with resume_yaml_path set
                to the per-run work copy.
        Output:
            Returns a mock TailorRunResult with success=True.
        """
        Path(invocation.resume_yaml_path).write_text(
            "name: TAILORED\n", encoding="utf-8"
        )
        return mock_result

    with patch(
        "scripts.process_qualified_jobs.run_resume_tailor_pipeline",
        side_effect=fake_pipeline,
    ):
        result = await _tailor_once(
            db=db,
            output_base_dir=output_dir,
            resume_yaml_path=yaml_path,
            max_retries=2,
            lease_seconds=7200,
            backoff_seconds=600,
            backoff_multiplier=2,
        )

    assert result == 1
    assert yaml_path.read_text(encoding="utf-8") == original_content


# ---------------------------------------------------------------------------
# Test: YAML unchanged after pipeline failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_yaml_unchanged_after_pipeline_failure(
    db: DatabaseManager,
    tmp_path: Path,
) -> None:
    """Verify the original YAML is untouched when the pipeline raises.

    Purpose:
        Validate that the per-run working copy approach protects the canonical
        YAML even when the pipeline crashes with an exception.
    """

    job_hash = "b" * 32
    await _insert_qualified_job(db, job_hash)

    yaml_path = tmp_path / "resume_content.yaml"
    original_content = "name: Test User\nsummary: Original\n"
    yaml_path.write_text(original_content, encoding="utf-8")

    output_dir = tmp_path / "output"
    output_dir.mkdir()

    def fake_pipeline(*, invocation: TailorInvocationContract) -> MagicMock:
        """Raise to simulate a pipeline crash.

        Purpose:
            Force the exception handler to verify the canonical YAML remains
            unmodified after recovery.
        Arg(s):
            invocation: Unused pipeline contract.
        Output:
            Raises RuntimeError unconditionally.
        """
        raise RuntimeError("pipeline crashed")

    with patch(
        "scripts.process_qualified_jobs.run_resume_tailor_pipeline",
        side_effect=fake_pipeline,
    ):
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
    assert yaml_path.read_text(encoding="utf-8") == original_content


# ---------------------------------------------------------------------------
# Test: YAML copy fails when source deleted — records failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_yaml_copy_fails_when_source_deleted_records_failure(
    db: DatabaseManager,
    tmp_path: Path,
) -> None:
    """Verify that a missing source YAML records a failure in the database.

    Purpose:
        Validate M-003: when the canonical YAML is absent at copy time,
        the worker records a failure and returns 0 without crashing.
    """

    job_hash = "c" * 32
    await _insert_qualified_job(db, job_hash)

    # Point to a YAML that does not exist.
    yaml_path = tmp_path / "deleted_resume.yaml"
    output_dir = tmp_path / "output"
    output_dir.mkdir()

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

    runs = await db.get_tailor_runs_for_job(job_hash)
    assert len(runs) == 1
    assert runs[0]["status"] == "FAILED"
    run_error = runs[0]["error"]
    assert isinstance(run_error, str)
    assert "yaml_copy_failed" in run_error


# ---------------------------------------------------------------------------
# Test: external modification of original YAML does not affect work copy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_yaml_externally_modified_does_not_affect_work_copy(
    db: DatabaseManager,
    tmp_path: Path,
) -> None:
    """Verify the pipeline receives its own work copy, not the live original.

    Purpose:
        Validate that after shutil.copy2 completes, any external modification
        to the canonical YAML does not affect the content the pipeline sees,
        because the pipeline operates on an isolated work copy.
    """

    job_hash = "d" * 32
    await _insert_qualified_job(db, job_hash)

    yaml_path = tmp_path / "resume_content.yaml"
    original_content = "name: Test User\nsummary: Original\n"
    yaml_path.write_text(original_content, encoding="utf-8")

    output_dir = tmp_path / "output"
    output_dir.mkdir()

    captured_work_content: list[str] = []

    mock_result = MagicMock()
    mock_result.success = True
    mock_result.final_page_count = 1
    mock_result.failure_reason = None

    def fake_pipeline(*, invocation: TailorInvocationContract) -> MagicMock:
        """Capture the content seen by the pipeline via work copy path.

        Purpose:
            Read the work copy content to verify it matches the original
            even after the canonical YAML has been externally modified.
        Arg(s):
            invocation: TailorInvocationContract with resume_yaml_path set
                to the per-run work copy.
        Output:
            Returns a mock TailorRunResult with success=True.
        """
        # Externally modify the original YAML after the copy was made.
        yaml_path.write_text("name: EXTERNALLY MODIFIED\n", encoding="utf-8")
        # Capture what the pipeline actually receives.
        work_content = Path(invocation.resume_yaml_path).read_text(encoding="utf-8")
        captured_work_content.append(work_content)
        return mock_result

    with patch(
        "scripts.process_qualified_jobs.run_resume_tailor_pipeline",
        side_effect=fake_pipeline,
    ):
        result = await _tailor_once(
            db=db,
            output_base_dir=output_dir,
            resume_yaml_path=yaml_path,
            max_retries=2,
            lease_seconds=7200,
            backoff_seconds=600,
            backoff_multiplier=2,
        )

    assert result == 1
    assert len(captured_work_content) == 1
    # The work copy must contain the original content, not the modified version.
    assert captured_work_content[0] == original_content
