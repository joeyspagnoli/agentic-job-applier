"""Validate budget enforcement guards and worker claim behavior.

Purpose:
    Ensure exhausted budgets block new queue claims across all workers while
    preserving in-flight stage completion semantics.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from scripts import process_apply_jobs
from scripts import process_new_jobs
from scripts import process_qualified_jobs
from scripts import process_reviewed_resumes
from src.database.db_manager import DatabaseManager
from src.utils.cost_tracking import PIPELINE_STAGE_GATE
from src.utils.cost_tracking import check_budget_before_claim


@pytest_asyncio.fixture
async def budget_db(tmp_path: Path) -> AsyncGenerator[DatabaseManager, None]:
    """Create an isolated database prepared for cost and budget assertions.

    Purpose:
        Provide deterministic budget/cost tables for each test without shared
        state between test cases.
    Args:
        tmp_path: Pytest temporary-directory fixture.
    Output:
        Yields a connected `DatabaseManager` instance.
    """

    manager = DatabaseManager(str(tmp_path / "budget.db"))
    await manager.connect()
    await manager.create_tables()
    await manager.migrate_cost_schema()
    yield manager
    await manager.close()


async def _record_spend(db: DatabaseManager, amount_usd: float) -> None:
    """Record one cost event in the current month for budget rollups.

    Purpose:
        Keep test setup concise when seeding monthly spend totals.
    Args:
        db: Connected database manager used to persist the event.
        amount_usd: Positive spend amount to insert.
    Output:
        Returns `None` after recording one spend event.
    """

    await db.record_cost_event(
        stage=PIPELINE_STAGE_GATE,
        cost_usd=amount_usd,
        job_hash="a" * 32,
        run_id=f"budget-seed-{amount_usd}",
        metadata_json=None,
    )


async def _insert_qualified_job(db: DatabaseManager, job_hash: str) -> None:
    """Insert one minimal QUALIFIED job row for tailor-worker tests.

    Purpose:
        Provide a claimable job fixture for end-to-end worker budget checks.
    Args:
        db: Connected database manager used for insertion.
        job_hash: Stable unique hash for the seeded job row.
    Output:
        Returns `None` after inserting and committing.
    """

    conn = db._require_conn()
    await conn.execute(
        """
        INSERT INTO job_postings (
            job_hash, source, source_url, company, title, status
        ) VALUES (?, 'test', 'https://example.com/jobs/1', 'TestCo', 'Engineer', 'QUALIFIED')
        """,
        (job_hash,),
    )
    await conn.commit()


@pytest.mark.asyncio
async def test_is_budget_exceeded_false_when_under_budget(
    budget_db: DatabaseManager,
) -> None:
    """Verify budget is not exceeded when monthly spend is below limit.

    Purpose:
        Protect the non-terminal budget path used by all worker claim guards.
    Args:
        budget_db: Connected migrated database fixture.
    Output:
        Returns `None`; test passes when exceeded flag is `False`.
    """

    await budget_db.set_budget_settings(monthly_budget_usd=100.0)
    await _record_spend(budget_db, 50.0)
    assert await budget_db.is_budget_exceeded() is False


@pytest.mark.asyncio
async def test_is_budget_exceeded_true_at_exact_budget(
    budget_db: DatabaseManager,
) -> None:
    """Verify budget is exceeded when spend exactly matches monthly limit.

    Purpose:
        Enforce the "no new claims at zero remaining budget" rule.
    Args:
        budget_db: Connected migrated database fixture.
    Output:
        Returns `None`; test passes when exceeded flag is `True`.
    """

    await budget_db.set_budget_settings(monthly_budget_usd=100.0)
    await _record_spend(budget_db, 100.0)
    assert await budget_db.is_budget_exceeded() is True


@pytest.mark.asyncio
async def test_is_budget_exceeded_true_when_over_budget(
    budget_db: DatabaseManager,
) -> None:
    """Verify budget is exceeded when spend is greater than monthly limit.

    Purpose:
        Protect over-budget worker blocking behavior.
    Args:
        budget_db: Connected migrated database fixture.
    Output:
        Returns `None`; test passes when exceeded flag is `True`.
    """

    await budget_db.set_budget_settings(monthly_budget_usd=100.0)
    await _record_spend(budget_db, 150.0)
    assert await budget_db.is_budget_exceeded() is True


@pytest.mark.asyncio
async def test_is_budget_exceeded_true_when_budget_is_zero(
    budget_db: DatabaseManager,
) -> None:
    """Verify zero monthly budget is treated as budget exhausted.

    Purpose:
        Respect explicit operator intent when monthly budget is set to zero.
    Args:
        budget_db: Connected migrated database fixture.
    Output:
        Returns `None`; test passes when exceeded flag is `True`.
    """

    await budget_db.set_budget_settings(monthly_budget_usd=0.0)
    assert await budget_db.is_budget_exceeded() is True


@pytest.mark.asyncio
async def test_is_budget_exceeded_false_with_large_budget_small_spend(
    budget_db: DatabaseManager,
) -> None:
    """Verify large remaining budget keeps the exceeded flag false.

    Purpose:
        Confirm budget checks remain permissive under healthy budget headroom.
    Args:
        budget_db: Connected migrated database fixture.
    Output:
        Returns `None`; test passes when exceeded flag is `False`.
    """

    await budget_db.set_budget_settings(monthly_budget_usd=10_000.0)
    await _record_spend(budget_db, 0.50)
    assert await budget_db.is_budget_exceeded() is False


@pytest.mark.asyncio
async def test_is_budget_exceeded_false_with_no_spend_events(
    budget_db: DatabaseManager,
) -> None:
    """Verify untouched monthly budgets are not flagged as exceeded.

    Purpose:
        Protect fresh-environment startup behavior before any stage runs.
    Args:
        budget_db: Connected migrated database fixture.
    Output:
        Returns `None`; test passes when exceeded flag is `False`.
    """

    await budget_db.set_budget_settings(monthly_budget_usd=100.0)
    assert await budget_db.is_budget_exceeded() is False


@pytest.mark.asyncio
async def test_budget_reads_do_not_insert_default_budget_row(
    budget_db: DatabaseManager,
) -> None:
    """Verify read-only budget calls do not write default settings rows.

    Purpose:
        Protect the side-effect-free read contract so claim guards avoid
        unnecessary SQLite writes and lock pressure.
    Args:
        budget_db: Connected migrated database fixture.
    Output:
        Returns `None`; test passes when read paths leave row count unchanged.
    """

    conn = budget_db._require_conn()
    before_cursor = await conn.execute(
        "SELECT COUNT(*) AS row_count FROM budget_settings"
    )
    before_row = await before_cursor.fetchone()
    before_count = int(before_row["row_count"]) if before_row else 0

    snapshot = await budget_db.get_budget_settings()
    exceeded = await budget_db.is_budget_exceeded()

    after_cursor = await conn.execute(
        "SELECT COUNT(*) AS row_count FROM budget_settings"
    )
    after_row = await after_cursor.fetchone()
    after_count = int(after_row["row_count"]) if after_row else 0

    monthly_budget = snapshot["monthly_budget_usd"]
    assert isinstance(monthly_budget, (int, float))
    assert monthly_budget >= 0.0
    assert exceeded is False
    assert after_count == before_count


@pytest.mark.asyncio
async def test_check_budget_before_claim_returns_false_when_exceeded(
    budget_db: DatabaseManager,
) -> None:
    """Verify claim guard blocks new work when budget is exhausted.

    Purpose:
        Assert guard helper semantics used by all worker queue-claim entrypoints.
    Args:
        budget_db: Connected migrated database fixture.
    Output:
        Returns `None`; test passes when helper returns `False`.
    """

    await budget_db.set_budget_settings(monthly_budget_usd=0.0)
    assert (
        await check_budget_before_claim(db=budget_db, stage=PIPELINE_STAGE_GATE)
        is False
    )


@pytest.mark.asyncio
async def test_check_budget_before_claim_returns_true_when_under_budget(
    budget_db: DatabaseManager,
) -> None:
    """Verify claim guard allows work when budget has positive remaining value.

    Purpose:
        Assert helper does not block healthy-stage claim attempts.
    Args:
        budget_db: Connected migrated database fixture.
    Output:
        Returns `None`; test passes when helper returns `True`.
    """

    await budget_db.set_budget_settings(monthly_budget_usd=100.0)
    await _record_spend(budget_db, 25.0)
    assert (
        await check_budget_before_claim(db=budget_db, stage=PIPELINE_STAGE_GATE) is True
    )


@pytest.mark.asyncio
async def test_gate_worker_skips_pending_query_when_budget_exceeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify gate worker exits before pending-job query when budget is exhausted.

    Purpose:
        Confirm budget guard sits before queue reads in the gate worker.
    Args:
        monkeypatch: Fixture used to stub model-loading dependencies.
    Output:
        Returns `None`; test passes when pending query is never called.
    """

    class FakeGateDb:
        """Provide minimal DB API shape required by `_process_once`.

        Purpose:
            Allow assertion that pending query is never reached when blocked.
        Args:
            None.
        Output:
            Returns a fake DB object with async method stubs.
        """

        def __init__(self) -> None:
            self.get_jobs_pending_agent_processing = AsyncMock(return_value=[])

        async def is_budget_exceeded(self) -> bool:
            """Return exceeded status for guard-path testing.

            Purpose:
                Force the budget guard to block worker queue reads.
            Args:
                None.
            Output:
                Returns `True`.
            """

            return True

    monkeypatch.setattr(process_new_jobs, "get_decider_model", lambda: object())
    monkeypatch.setattr(process_new_jobs, "build_root_agent", lambda model: object())

    fake_db = FakeGateDb()
    processed = await process_new_jobs._process_once(
        db=fake_db,  # type: ignore[arg-type]  # FakeGateDb satisfies the duck-type contract
        limit=5,
    )

    assert processed == 0
    fake_db.get_jobs_pending_agent_processing.assert_not_called()


@pytest.mark.asyncio
async def test_tailor_worker_skips_claim_when_budget_exceeded(
    tmp_path: Path,
) -> None:
    """Verify tailor worker exits before claim when budget is exhausted.

    Purpose:
        Confirm tailor queue claims are blocked by budget guard.
    Args:
        tmp_path: Temporary directory fixture for placeholder path arguments.
    Output:
        Returns `None`; test passes when claim method is not called.
    """

    class FakeTailorDb:
        """Provide minimal DB API shape required by `_tailor_once`.

        Purpose:
            Allow claim-call assertions for budget-guard behavior.
        Args:
            None.
        Output:
            Returns fake DB object with async method stubs.
        """

        def __init__(self) -> None:
            self.claim_next_tailor_job = AsyncMock(return_value=None)

        async def is_budget_exceeded(self) -> bool:
            """Return exceeded status for guard-path testing.

            Purpose:
                Force budget guard to short-circuit before claim.
            Args:
                None.
            Output:
                Returns `True`.
            """

            return True

    fake_db = FakeTailorDb()
    processed = await process_qualified_jobs._tailor_once(
        db=fake_db,  # type: ignore[arg-type]  # FakeTailorDb satisfies the duck-type contract
        output_base_dir=tmp_path / "output",
        resume_yaml_path=tmp_path / "resume.yaml",
        max_retries=2,
        lease_seconds=30,
        backoff_seconds=5,
        backoff_multiplier=2,
        pi_model=None,
    )

    assert processed == 0
    fake_db.claim_next_tailor_job.assert_not_called()


@pytest.mark.asyncio
async def test_review_worker_skips_claim_when_budget_exceeded(
    tmp_path: Path,
) -> None:
    """Verify review worker exits before claim when budget is exhausted.

    Purpose:
        Confirm review queue claims are blocked by budget guard.
    Args:
        tmp_path: Temporary directory fixture for placeholder path arguments.
    Output:
        Returns `None`; test passes when claim method is not called.
    """

    class FakeReviewDb:
        """Provide minimal DB API shape required by `_review_once`.

        Purpose:
            Allow claim-call assertions for budget-guard behavior.
        Args:
            None.
        Output:
            Returns fake DB object with async method stubs.
        """

        def __init__(self) -> None:
            self.claim_next_review_job = AsyncMock(return_value=None)

        async def is_budget_exceeded(self) -> bool:
            """Return exceeded status for guard-path testing.

            Purpose:
                Force budget guard to short-circuit before claim.
            Args:
                None.
            Output:
                Returns `True`.
            """

            return True

    fake_db = FakeReviewDb()
    processed = await process_reviewed_resumes._review_once(
        db=fake_db,  # type: ignore[arg-type]  # FakeReviewDb satisfies the duck-type contract
        output_base_dir=tmp_path / "output",
        base_yaml_path=tmp_path / "base.yaml",
        base_tex_path=tmp_path / "base.tex",
        base_pdf_path=tmp_path / "base.pdf",
        max_retries=2,
        lease_seconds=30,
        backoff_seconds=5,
        backoff_multiplier=2,
        pi_model=None,
    )

    assert processed == 0
    fake_db.claim_next_review_job.assert_not_called()


@pytest.mark.asyncio
async def test_apply_worker_skips_claim_when_budget_exceeded(
    tmp_path: Path,
) -> None:
    """Verify apply worker exits before claim when budget is exhausted.

    Purpose:
        Confirm apply queue claims are blocked by budget guard.
    Args:
        tmp_path: Temporary directory fixture for placeholder path arguments.
    Output:
        Returns `None`; test passes when claim method is not called.
    """

    class FakeApplyDb:
        """Provide minimal DB API shape required by `_apply_once`.

        Purpose:
            Allow claim-call assertions for budget-guard behavior.
        Args:
            None.
        Output:
            Returns fake DB object with async method stubs.
        """

        def __init__(self) -> None:
            self.claim_next_apply_job = AsyncMock(return_value=None)

        async def is_budget_exceeded(self) -> bool:
            """Return exceeded status for guard-path testing.

            Purpose:
                Force budget guard to short-circuit before claim.
            Args:
                None.
            Output:
                Returns `True`.
            """

            return True

    fake_db = FakeApplyDb()
    processed = await process_apply_jobs._apply_once(
        db=fake_db,  # type: ignore[arg-type]  # FakeApplyDb satisfies the duck-type contract
        output_base_dir=tmp_path / "output",
        cdp_url="http://localhost:9222",
        max_retries=2,
        lease_seconds=30,
        backoff_seconds=5,
        backoff_multiplier=2,
        dry_run=True,
    )

    assert processed == 0
    fake_db.claim_next_apply_job.assert_not_called()


@pytest.mark.asyncio
async def test_claimed_tailor_stage_finishes_even_when_cost_pushes_over_budget(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify a claimed stage run completes even if it exceeds budget.

    Purpose:
        Enforce the rule that budget checks occur before claim only, allowing
        in-flight work to finish even when completion costs exhaust budget.
    Args:
        monkeypatch: Fixture used to control stage cost and tailor runtime.
        tmp_path: Temporary directory fixture for DB and artifact paths.
    Output:
        Returns `None`; test passes when run succeeds and budget becomes exceeded.
    """

    db = DatabaseManager(str(tmp_path / "pipeline.db"))
    await db.connect()
    await db.create_tables()
    await db.migrate_agent_schema()
    await db.migrate_tailor_schema()
    await db.migrate_cost_schema()

    try:
        await db.set_budget_settings(monthly_budget_usd=1.0)
        await _insert_qualified_job(db, "a" * 32)

        base_yaml = tmp_path / "resume_content.yaml"
        base_yaml.write_text("name: Test User\n", encoding="utf-8")

        output_dir = tmp_path / "tailored"
        output_dir.mkdir(parents=True, exist_ok=True)

        monkeypatch.setenv("COST_RATE_TAILOR_USD", "2.0")
        monkeypatch.setattr(
            process_qualified_jobs,
            "run_resume_tailor_pipeline",
            lambda *, invocation: SimpleNamespace(
                success=True,
                final_page_count=1,
                failure_reason=None,
            ),
        )

        processed = await process_qualified_jobs._tailor_once(
            db=db,
            output_base_dir=output_dir,
            resume_yaml_path=base_yaml,
            max_retries=2,
            lease_seconds=30,
            backoff_seconds=5,
            backoff_multiplier=2,
            pi_model=None,
        )

        assert processed == 1
        assert await db.is_budget_exceeded() is True
    finally:
        await db.close()
