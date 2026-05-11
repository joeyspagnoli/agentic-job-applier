"""Tests for the resume-tailor worker daemon's automation-mode gating.

Purpose:
    Validate the per-cycle contract documented in the handoff: the stale
    sweep runs unconditionally, the claim only fires in `autonomous` /
    `both`, and a budget block prevents claims even when the mode allows.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio

from scripts import process_qualified_jobs as worker_module
from src.database._mixins.system_settings import TAILOR_MODE_KEY
from src.database.db_manager import DatabaseManager
from src.models.job_posting import JobPosting


@pytest_asyncio.fixture
async def db(tmp_path: Path) -> AsyncGenerator[DatabaseManager, None]:
    """Provide a fully migrated DB."""

    manager = DatabaseManager(str(tmp_path / "worker.db"))
    await manager.connect()
    await manager.create_tables()
    yield manager
    await manager.close()


async def _seed_qualified_job(db: DatabaseManager, *, job_hash: str) -> None:
    """Insert one QUALIFIED-status job row for the worker to claim."""

    posting = JobPosting(
        source="manual",
        source_url="https://example.com/" + job_hash,
        company="WorkerCo",
        title="Engineer",
        description="desc",
    )
    row = posting.to_db_dict()
    row["job_hash"] = job_hash
    await db.insert_job(row)

    conn = db._require_conn()
    await conn.execute(
        "UPDATE job_postings SET status = 'QUALIFIED' WHERE job_hash = ?",
        (job_hash,),
    )
    await conn.commit()


def _patch_pipeline(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Replace `run_tailor_review_pipeline` with a recorder; return its log."""

    invocations: list[dict[str, Any]] = []

    async def _stub(**kwargs: Any) -> Any:
        invocations.append(kwargs)

        class _Result:
            success = True
            verdict = "TAILORED"
            error = None
            selected_pdf_path = "/tmp/x.pdf"

        return _Result()

    monkeypatch.setattr(worker_module, "run_tailor_review_pipeline", _stub)
    return invocations


@pytest.mark.asyncio
async def test_opt_in_mode_skips_claim_but_runs_stale_sweep(
    db: DatabaseManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`opt_in` returns 0 immediately after the stale sweep — no claim."""

    invocations = _patch_pipeline(monkeypatch)
    await db.set_automation_mode(TAILOR_MODE_KEY, "opt_in")
    await _seed_qualified_job(db, job_hash="aa" * 20)

    stale_calls: list[int] = []
    original = db.mark_stale_tailor_runs_failed

    async def _wrapper(*, lease_seconds: int = 7200) -> int:
        stale_calls.append(lease_seconds)
        return await original(lease_seconds=lease_seconds)

    monkeypatch.setattr(db, "mark_stale_tailor_runs_failed", _wrapper)

    processed = await worker_module.tailor_once(
        db=db,
        output_base_dir=tmp_path / "out",
        resume_yaml_path=tmp_path / "resume.yaml",
        candidate_profile_yaml_path=tmp_path / "profile.yaml",
        max_retries=2,
        lease_seconds=120,
    )

    assert processed == 0
    assert stale_calls == [120]
    assert invocations == []


@pytest.mark.asyncio
async def test_autonomous_mode_claims_and_invokes_pipeline(
    db: DatabaseManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`autonomous` mode claims one job and invokes the pipeline exactly once."""

    invocations = _patch_pipeline(monkeypatch)
    await db.set_automation_mode(TAILOR_MODE_KEY, "autonomous")
    await _seed_qualified_job(db, job_hash="bb" * 20)

    processed = await worker_module.tailor_once(
        db=db,
        output_base_dir=tmp_path / "out",
        resume_yaml_path=tmp_path / "resume.yaml",
        candidate_profile_yaml_path=tmp_path / "profile.yaml",
        max_retries=2,
        lease_seconds=120,
    )

    assert processed == 1
    assert len(invocations) == 1
    assert invocations[0]["job_hash"] == "bb" * 20


@pytest.mark.asyncio
async def test_both_mode_also_claims(
    db: DatabaseManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`both` is treated the same as `autonomous` for the worker."""

    invocations = _patch_pipeline(monkeypatch)
    await db.set_automation_mode(TAILOR_MODE_KEY, "both")
    await _seed_qualified_job(db, job_hash="cc" * 20)

    processed = await worker_module.tailor_once(
        db=db,
        output_base_dir=tmp_path / "out",
        resume_yaml_path=tmp_path / "resume.yaml",
        candidate_profile_yaml_path=tmp_path / "profile.yaml",
        max_retries=2,
        lease_seconds=120,
    )

    assert processed == 1
    assert len(invocations) == 1


@pytest.mark.asyncio
async def test_mode_flip_observed_on_next_cycle(
    db: DatabaseManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mode changes between cycles take effect without restart."""

    invocations = _patch_pipeline(monkeypatch)
    await db.set_automation_mode(TAILOR_MODE_KEY, "autonomous")
    await _seed_qualified_job(db, job_hash="dd" * 20)
    await _seed_qualified_job(db, job_hash="ee" * 20)

    first = await worker_module.tailor_once(
        db=db,
        output_base_dir=tmp_path / "out",
        resume_yaml_path=tmp_path / "resume.yaml",
        candidate_profile_yaml_path=tmp_path / "profile.yaml",
        max_retries=2,
        lease_seconds=120,
    )
    assert first == 1

    await db.set_automation_mode(TAILOR_MODE_KEY, "opt_in")
    second = await worker_module.tailor_once(
        db=db,
        output_base_dir=tmp_path / "out",
        resume_yaml_path=tmp_path / "resume.yaml",
        candidate_profile_yaml_path=tmp_path / "profile.yaml",
        max_retries=2,
        lease_seconds=120,
    )

    assert second == 0
    assert len(invocations) == 1


@pytest.mark.asyncio
async def test_budget_exceeded_blocks_claim_in_autonomous_mode(
    db: DatabaseManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A budget block returns 0 before any pipeline invocation."""

    invocations = _patch_pipeline(monkeypatch)
    await db.set_automation_mode(TAILOR_MODE_KEY, "autonomous")
    await _seed_qualified_job(db, job_hash="ff" * 20)

    async def _exceeded(self: object) -> bool:
        return True

    monkeypatch.setattr(
        "src.database._mixins.costs.CostsMixin.is_budget_exceeded",
        _exceeded,
    )

    processed = await worker_module.tailor_once(
        db=db,
        output_base_dir=tmp_path / "out",
        resume_yaml_path=tmp_path / "resume.yaml",
        candidate_profile_yaml_path=tmp_path / "profile.yaml",
        max_retries=2,
        lease_seconds=120,
    )

    assert processed == 0
    assert invocations == []


@pytest.mark.asyncio
async def test_unknown_mode_is_treated_as_opt_in(
    db: DatabaseManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An invalid stored mode does not crash; worker treats it as opt-in."""

    invocations = _patch_pipeline(monkeypatch)
    # `set_automation_mode` rejects invalid input, so write the raw value
    # to simulate corruption.
    await db.set_system_setting(TAILOR_MODE_KEY, "junk_value")
    await _seed_qualified_job(db, job_hash="00" * 20)

    processed = await worker_module.tailor_once(
        db=db,
        output_base_dir=tmp_path / "out",
        resume_yaml_path=tmp_path / "resume.yaml",
        candidate_profile_yaml_path=tmp_path / "profile.yaml",
        max_retries=2,
        lease_seconds=120,
    )

    assert processed == 0
    assert invocations == []
