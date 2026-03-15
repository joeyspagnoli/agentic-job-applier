"""Run opt-in live model end-to-end tests for handcrafted job postings.

Purpose:
    Validate real model integration through the database-backed worker flow
    using known good-fit and bad-fit postings when explicitly requested.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from scripts import process_new_jobs
from src.database.db_manager import DatabaseManager
from src.models.job_posting import JobPosting


@pytest.mark.asyncio
@pytest.mark.live_agent_e2e
async def test_live_model_good_and_bad_postings_end_to_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify live model processing persists opposite outcomes for handpicked jobs.

    Purpose:
        Confirm real model execution can process handcrafted good/bad postings
        through the full DB queue and worker persistence pipeline.
    Args:
        monkeypatch: Pytest fixture used to disable outbound notifications.
    Output:
        Returns `None`; test passes when both rows are processed with opposite
        final statuses and persisted `agent_result` payloads.
    """

    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY is required for live_agent_e2e tests")

    async def no_op_notify(*_: object, **__: object) -> None:
        """Suppress notification side effects during live tests.

        Purpose:
            Keep live tests focused on gate decision behavior instead of alerting.
        Args:
            *_: Ignored positional arguments.
            **__: Ignored keyword arguments.
        Output:
            Returns `None`.
        """

    monkeypatch.setattr(process_new_jobs, "_notify_terminal_failure", no_op_notify)
    monkeypatch.setattr(
        process_new_jobs,
        "_notify_worker_configuration_failure",
        no_op_notify,
    )

    good_fit_job = JobPosting(
        source="live_e2e",
        source_url="https://example.com/jobs/good-fit",
        company="Signal AI Labs",
        title="Machine Learning Engineering Internship",
        location="Remote (US)",
        job_type="Internship",
        description=(
            "Build backend ML services for production inference, evaluation, and "
            "developer tooling. Collaborate with ML platform engineers."
        ),
        requirements=(
            "Pursuing a BS in CS, strong Python skills, and interest in "
            "MLOps/cloud systems."
        ),
    )
    bad_fit_job = JobPosting(
        source="live_e2e",
        source_url="https://example.com/jobs/bad-fit",
        company="Ops Support Corp",
        title="IT Help Desk Specialist (Full-Time)",
        location="On-site",
        job_type="Full-time",
        description=(
            "Provide desktop support, reset passwords, and troubleshoot office "
            "printers for internal teams."
        ),
        requirements=(
            "3+ years in IT support, rotating shift work, and office presence."
        ),
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "jobs.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            await db.migrate_agent_schema()
            await db.insert_job(good_fit_job.to_db_dict())
            await db.insert_job(bad_fit_job.to_db_dict())

            processed = await process_new_jobs.process_once(
                db=db,
                limit=10,
                max_retries=1,
            )
            good_row = await db.get_job_by_hash(good_fit_job.job_hash)
            bad_row = await db.get_job_by_hash(bad_fit_job.job_hash)

    assert processed == 2
    assert good_row is not None
    assert bad_row is not None
    assert good_row["status"] in {"QUALIFIED", "FILTERED"}
    assert bad_row["status"] in {"QUALIFIED", "FILTERED"}
    assert good_row["status"] != bad_row["status"]
    assert good_row["agent_result"]
    assert bad_row["agent_result"]
