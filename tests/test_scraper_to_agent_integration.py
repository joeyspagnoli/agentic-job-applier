"""Exercise deterministic scraper-to-gate integration workflows.

Purpose:
    Validate the producer/consumer handoff through SQLite plus retry and
    backlog semantics without requiring network access or live model calls.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

import main as discovery_main
from scripts import process_new_jobs
from src.agents.root_apply_decider import ApplyDecision, GateDebugInfo, GateRunResult
from src.database.db_manager import DatabaseManager
from src.models.job_posting import JobPosting


def _build_gate_result(decision: ApplyDecision) -> GateRunResult:
    """Build a deterministic gate run result for integration tests.

    Purpose:
        Keep persistence and queue tests independent from live model behavior by
        returning stable gate payloads.
    Args:
        decision: Gate decision to include in the fake result.
    Output:
        Returns a deterministic `GateRunResult` for test assertions.
    """

    return GateRunResult(
        decision=decision,
        debug=GateDebugInfo(
            confidence=0.95,
            explanation="Deterministic test result",
            preference_matches=["integration"],
            preference_conflicts=[],
        ),
        raw_response=f'{{"decision":"{decision.value}"}}',
        provider="test",
        model="test-model",
        parse_mode="json_recovered",
    )


@pytest.mark.asyncio
async def test_discovery_row_is_handed_to_gate_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify discovered NEW rows are consumed and persisted by the gate worker.

    Purpose:
        Prove end-to-end producer/consumer integration across discovery,
        database queueing, and gate status persistence.
    Args:
        monkeypatch: Pytest fixture used to patch fetchers and model execution.
    Output:
        Returns `None`; test passes when NEW transitions to QUALIFIED.
    """

    class FakeGreenhouseFetcher:
        """Return one deterministic internship posting without network access."""

        def __init__(self, company_name: str, greenhouse_id: str):
            """Capture constructor values to match production call signatures.

            Purpose:
                Keep this fake fetcher drop-in compatible with the orchestrator.
            Args:
                company_name: Company label from config.
                greenhouse_id: Greenhouse board identifier from config.
            Output:
                Returns `None` after storing constructor values.
            """

            self.company_name = company_name
            self.greenhouse_id = greenhouse_id

        async def __aenter__(self) -> "FakeGreenhouseFetcher":
            """Return this fake fetcher for async context manager compatibility.

            Purpose:
                Match the production Greenhouse fetcher context manager shape.
            Args:
                self: Fake fetcher instance.
            Output:
                Returns this instance.
            """

            return self

        async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            """Provide no-op async context exit for fake fetcher.

            Purpose:
                Keep context-manager behavior compatible with production code.
            Args:
                self: Fake fetcher instance.
                exc_type: Exception type if context failed.
                exc_val: Exception value if context failed.
                exc_tb: Exception traceback if context failed.
            Output:
                Returns `None`.
            """

            _ = (exc_type, exc_val, exc_tb)

        async def fetch_jobs(self) -> list[JobPosting]:
            """Return one deterministic internship posting.

            Purpose:
                Provide stable discovery output for integration handoff tests.
            Args:
                self: Fake fetcher instance.
            Output:
                Returns one normalized `JobPosting`.
            """

            return [
                JobPosting(
                    source="greenhouse_test",
                    source_url="https://example.com/jobs/alpha",
                    company="ExampleCo",
                    title="Software Engineering Intern",
                    location="Remote",
                    job_type="Internship",
                    description="Build backend systems and internal tooling.",
                    requirements="Pursuing a BS in CS.",
                )
            ]

    original_load_yaml = discovery_main.load_yaml

    def fake_load_yaml(path: str | Path) -> dict[str, Any]:
        """Return minimal discovery config while preserving other YAML loads.

        Purpose:
            Keep discovery deterministic and network-free in this integration
            test while allowing optional config reads to continue working.
        Args:
            path: YAML path requested by the orchestrator.
        Output:
            Returns controlled company config for discovery.
        """

        if Path(path).name == "companies.yaml":
            return {
                "greenhouse_companies": {"ExampleCo": {"greenhouse_id": "exampleco"}},
                "workday_companies": {},
                "job_boards": {},
            }
        return original_load_yaml(path)

    async def fake_run_decider_for_job(**_: object) -> GateRunResult:
        """Return deterministic APPLY decision for worker integration test.

        Purpose:
            Replace live model calls with deterministic gate output.
        Args:
            **_: Ignored keyword arguments from production call site.
        Output:
            Returns deterministic APPLY result.
        """

        return _build_gate_result(ApplyDecision.APPLY)

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "jobs.db"
        monkeypatch.setattr(discovery_main, "resolve_database_path", lambda: db_path)
        monkeypatch.setattr(discovery_main, "load_yaml", fake_load_yaml)
        monkeypatch.setattr(discovery_main, "GreenhouseFetcher", FakeGreenhouseFetcher)
        monkeypatch.setattr(process_new_jobs, "get_decider_model", lambda: object())
        monkeypatch.setattr(
            process_new_jobs, "build_root_agent", lambda model: object()
        )
        monkeypatch.setattr(
            process_new_jobs, "_run_decider_for_job", fake_run_decider_for_job
        )

        await discovery_main.run_job_discovery()

        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            await db.migrate_agent_schema()

            pending = await db.get_jobs_by_status("NEW", limit=10)
            assert len(pending) == 1
            assert pending[0]["status"] == "NEW"

            processed = await process_new_jobs.process_once(db=db, limit=10)
            stored_row = await db.get_job_by_hash(pending[0]["job_hash"])

    assert processed == 1
    assert stored_row is not None
    assert stored_row["status"] == "QUALIFIED"
    assert stored_row["agent_processed_at"] is not None


@pytest.mark.asyncio
async def test_worker_retries_transient_failures_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify transient decider failures are retried before final success.

    Purpose:
        Protect retry-state-machine behavior: schedule retries, keep row NEW,
        then persist a successful decision when a later attempt succeeds.
    Args:
        monkeypatch: Pytest fixture used to patch model execution path.
    Output:
        Returns `None`; test passes when retry metadata progresses correctly.
    """

    call_counter = {"runs": 0}

    async def flaky_decider(**_: object) -> GateRunResult:
        """Raise twice, then return a deterministic APPLY result.

        Purpose:
            Simulate transient provider failures before eventual success.
        Args:
            **_: Ignored keyword arguments from production call site.
        Output:
            Raises twice, then returns APPLY decision payload.
        """

        call_counter["runs"] += 1
        if call_counter["runs"] < 3:
            raise RuntimeError("transient provider error")
        return _build_gate_result(ApplyDecision.APPLY)

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "jobs.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            await db.migrate_agent_schema()
            job = JobPosting(
                source="test",
                source_url="https://example.com/jobs/retry",
                company="RetryCo",
                title="ML Intern",
                description="Test retry path",
            )
            await db.insert_job(job.to_db_dict())

            monkeypatch.setattr(process_new_jobs, "get_decider_model", lambda: object())
            monkeypatch.setattr(
                process_new_jobs, "build_root_agent", lambda model: object()
            )
            monkeypatch.setattr(process_new_jobs, "_run_decider_for_job", flaky_decider)
            monkeypatch.setattr(
                process_new_jobs,
                "_calculate_next_retry_at",
                lambda **_: "2000-01-01 00:00:00",
            )

            first_processed = await process_new_jobs.process_once(
                db=db,
                limit=10,
                max_retries=3,
            )
            first_row = await db.get_job_by_hash(job.job_hash)

            second_processed = await process_new_jobs.process_once(
                db=db,
                limit=10,
                max_retries=3,
            )
            second_row = await db.get_job_by_hash(job.job_hash)

            third_processed = await process_new_jobs.process_once(
                db=db,
                limit=10,
                max_retries=3,
            )
            final_row = await db.get_job_by_hash(job.job_hash)

    assert first_processed == 0
    assert second_processed == 0
    assert third_processed == 1
    assert first_row is not None
    assert second_row is not None
    assert final_row is not None
    assert first_row["agent_retry_count"] == 1
    assert second_row["agent_retry_count"] == 2
    assert final_row["status"] == "QUALIFIED"
    assert final_row["agent_retry_count"] == 0
    assert final_row["agent_failed_at"] is None


@pytest.mark.asyncio
async def test_worker_terminal_failure_sends_single_notification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify terminal failures are marked once and emit one ntfy alert.

    Purpose:
        Ensure bounded retries transition to terminal state and notification
        while preventing repeated alerts for the same failed row.
    Args:
        monkeypatch: Pytest fixture used to patch model execution and notifier.
    Output:
        Returns `None`; test passes when one alert is emitted at terminal state.
    """

    notifications: list[str] = []

    async def always_failing_decider(**_: object) -> GateRunResult:
        """Raise deterministic exception for each gate invocation.

        Purpose:
            Drive terminal-failure path after configured retry limit.
        Args:
            **_: Ignored keyword arguments from production call site.
        Output:
            Raises `RuntimeError` for every invocation.
        """

        raise RuntimeError("permanent parser failure")

    async def fake_terminal_notify(**kwargs: Any) -> None:
        """Capture terminal-notification payloads for assertions.

        Purpose:
            Verify terminal alert behavior without issuing outbound network calls.
        Args:
            **kwargs: Notification payload fields from call site.
        Output:
            Returns `None` after recording the captured notification.
        """

        notifications.append(str(kwargs.get("job_hash")))

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "jobs.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            await db.migrate_agent_schema()
            job = JobPosting(
                source="test",
                source_url="https://example.com/jobs/terminal",
                company="TerminalCo",
                title="Internship",
                description="Always failing path",
            )
            await db.insert_job(job.to_db_dict())

            monkeypatch.setattr(process_new_jobs, "get_decider_model", lambda: object())
            monkeypatch.setattr(
                process_new_jobs, "build_root_agent", lambda model: object()
            )
            monkeypatch.setattr(
                process_new_jobs,
                "_run_decider_for_job",
                always_failing_decider,
            )
            monkeypatch.setattr(
                process_new_jobs,
                "_calculate_next_retry_at",
                lambda **_: "2000-01-01 00:00:00",
            )
            monkeypatch.setattr(
                process_new_jobs,
                "_notify_terminal_failure",
                fake_terminal_notify,
            )

            await process_new_jobs.process_once(db=db, limit=10, max_retries=3)
            await process_new_jobs.process_once(db=db, limit=10, max_retries=3)
            await process_new_jobs.process_once(db=db, limit=10, max_retries=3)
            terminal_row = await db.get_job_by_hash(job.job_hash)

            # Terminally failed rows should no longer be fetched from NEW backlog.
            post_terminal_processed = await process_new_jobs.process_once(
                db=db,
                limit=10,
                max_retries=3,
            )

    assert terminal_row is not None
    assert terminal_row["agent_failed_at"] is not None
    assert post_terminal_processed == 0
    assert notifications == [job.job_hash]


@pytest.mark.asyncio
async def test_worker_respects_batch_limit_and_drains_backlog_incrementally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify worker processes full backlog incrementally according to limit.

    Purpose:
        Protect queue-drain behavior by ensuring only `limit` rows are processed
        per cycle while remaining NEW rows stay pending for subsequent cycles.
    Args:
        monkeypatch: Pytest fixture used to patch model execution path.
    Output:
        Returns `None`; test passes when backlog drains in bounded batches.
    """

    async def deterministic_decider(**_: object) -> GateRunResult:
        """Return deterministic APPLY decisions for every pending row.

        Purpose:
            Keep backlog-limit assertions focused on queue logic.
        Args:
            **_: Ignored keyword arguments from production call site.
        Output:
            Returns deterministic APPLY gate result.
        """

        return _build_gate_result(ApplyDecision.APPLY)

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "jobs.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            await db.migrate_agent_schema()

            for index in range(3):
                job = JobPosting(
                    source="test",
                    source_url=f"https://example.com/jobs/backlog-{index}",
                    company="BacklogCo",
                    title=f"Internship {index}",
                    description="Backlog row",
                )
                await db.insert_job(job.to_db_dict())

            monkeypatch.setattr(process_new_jobs, "get_decider_model", lambda: object())
            monkeypatch.setattr(
                process_new_jobs, "build_root_agent", lambda model: object()
            )
            monkeypatch.setattr(
                process_new_jobs,
                "_run_decider_for_job",
                deterministic_decider,
            )

            first_processed = await process_new_jobs.process_once(db=db, limit=2)
            new_rows_after_first = await db.get_jobs_by_status("NEW", limit=10)
            qualified_rows_after_first = await db.get_jobs_by_status(
                "QUALIFIED", limit=10
            )

            second_processed = await process_new_jobs.process_once(db=db, limit=2)
            new_rows_after_second = await db.get_jobs_by_status("NEW", limit=10)
            qualified_rows_after_second = await db.get_jobs_by_status(
                "QUALIFIED",
                limit=10,
            )

    assert first_processed == 2
    assert len(new_rows_after_first) == 1
    assert len(qualified_rows_after_first) == 2
    assert second_processed == 1
    assert len(new_rows_after_second) == 0
    assert len(qualified_rows_after_second) == 3
