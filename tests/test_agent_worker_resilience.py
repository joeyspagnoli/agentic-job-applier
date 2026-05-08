"""Cover agent worker status mapping and polling-loop resilience."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

import pytest

from scripts import process_new_jobs
from src.agents.root_apply_decider import ApplyDecision
from src.database.db_manager import DatabaseManager


def test_map_status_maps_skip_to_filtered() -> None:
    """Verify SKIP decisions map to FILTERED workflow status.

    Purpose:
        Protect the persisted status mapping contract for skip decisions.
    Args:
        None.
    Output:
        Returns `None`; the test passes when SKIP maps to FILTERED.
    """

    assert process_new_jobs._map_status(ApplyDecision.SKIP) == "FILTERED"


def test_map_status_maps_apply_to_qualified() -> None:
    """Verify APPLY decisions map to QUALIFIED workflow status.

    Purpose:
        Protect the persisted status mapping contract for apply decisions.
    Args:
        None.
    Output:
        Returns `None`; the test passes when APPLY maps to QUALIFIED.
    """

    assert process_new_jobs._map_status(ApplyDecision.APPLY) == "QUALIFIED"


@pytest.mark.asyncio
async def test_process_once_skips_rows_missing_job_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify rows without job_hash are skipped without side effects.

    Purpose:
        Ensure malformed rows do not invoke the decider path and do not crash
        the batch cycle.
    Args:
        monkeypatch: Pytest fixture used to patch model and DB interactions.
    Output:
        Returns `None`; the test passes when processing count is zero.
    """

    class FakeDb:
        """Provide the pending-job API shape required by `_process_once`."""

        async def is_budget_exceeded(self) -> bool:
            """Return non-exceeded budget state for this malformed-row test.

            Purpose:
                Keep this test focused on missing-hash handling rather than
                budget-guard branching.
            Args:
                self: Fake DB instance.
            Output:
                Returns `False`.
            """

            return False

        async def get_jobs_pending_agent_processing(self, limit: int) -> list[dict[str, object]]:
            """Return one malformed row that lacks a usable hash.

            Purpose:
                Trigger the missing-hash branch in `_process_once`.
            Args:
                self: Fake DB instance.
                limit: Requested batch size.
            Output:
                Returns one malformed pending-job row.
            """

            assert limit == 5
            return [{"job_hash": None, "title": "Broken Row"}]

        async def mark_job_agent_failed(self, job_hash: str, error: str) -> None:
            """Fail the test if a missing-hash row is marked failed.

            Purpose:
                Guard against incorrect failure writes for malformed rows.
            Args:
                self: Fake DB instance.
                job_hash: Job hash value from the call site.
                error: Failure text from the call site.
            Output:
                Raises `AssertionError`.
            """

            raise AssertionError("missing-hash rows must be skipped, not marked failed")

        async def record_agent_decision(
            self, *, job_hash: str, agent_result: str, status: str
        ) -> None:
            """Fail the test if a missing-hash row reaches decision persistence.

            Purpose:
                Guard against processing malformed rows through normal path.
            Args:
                self: Fake DB instance.
                job_hash: Job hash value from the call site.
                agent_result: Serialized result payload.
                status: Persisted workflow status.
            Output:
                Raises `AssertionError`.
            """

            raise AssertionError("missing-hash rows must not record decisions")

    async def should_not_run_decider(**_: object) -> None:
        """Fail the test if decider execution is attempted.

        Purpose:
            Ensure malformed rows are filtered before decider execution.
        Args:
            **_: Ignored keyword arguments.
        Output:
            Raises `AssertionError`.
        """

        raise AssertionError("decider should not run for missing-hash rows")

    monkeypatch.setattr(process_new_jobs, "get_decider_model", lambda: object())
    monkeypatch.setattr(process_new_jobs, "build_root_agent", lambda model: object())
    monkeypatch.setattr(
        process_new_jobs, "_run_decider_for_job", should_not_run_decider
    )

    processed = await process_new_jobs._process_once(db=FakeDb(), limit=5)  # type: ignore[arg-type]
    assert processed == 0


@pytest.mark.asyncio
async def test_process_once_skips_batch_when_model_is_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify model configuration failures raise dedicated configuration errors.

    Purpose:
        Ensure missing model credentials fail fast before any pending-row query
        and surface a dedicated error type for caller-level alert handling.
    Args:
        monkeypatch: Pytest fixture used to force model configuration failure.
    Output:
        Returns `None`; the test passes when model setup raises expected error.
    """

    class UnusedDb:
        """Fail fast if pending-job reads are attempted in skip path."""

        async def is_budget_exceeded(self) -> bool:
            """Return non-exceeded state when model setup should fail first.

            Purpose:
                Preserve this test's focus on model-configuration errors.
            Args:
                self: Fake DB instance.
            Output:
                Returns `False`.
            """

            return False

        async def get_jobs_pending_agent_processing(self, limit: int) -> list[dict[str, object]]:
            """Raise if called during model-not-configured path.

            Purpose:
                Guarantee `_process_once` exits before touching DB query path.
            Args:
                self: Fake DB instance.
                limit: Requested batch size.
            Output:
                Raises `AssertionError`.
            """

            _ = limit
            raise AssertionError("DB query should not run when model is unavailable")

    monkeypatch.setattr(
        process_new_jobs,
        "get_decider_model",
        lambda: (_ for _ in ()).throw(RuntimeError("missing API key")),
    )

    with pytest.raises(process_new_jobs.ModelConfigurationError):
        await process_new_jobs._process_once(db=UnusedDb(), limit=10)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_main_loop_continues_after_process_cycle_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify loop mode survives per-cycle exceptions and continues polling.

    Purpose:
        Ensure one unhandled exception from `_process_once` does not terminate
        loop mode, preserving background worker resilience.
    Args:
        monkeypatch: Pytest fixture used to control args and loop behavior.
    Output:
        Returns `None`; the test passes when loop continues to a second cycle.
    """

    class EndLoop(Exception):
        """Stop the infinite loop deterministically in tests."""

    calls = {"process": 0, "sleep": 0}

    async def fake_process_once(
        *,
        db: DatabaseManager,
        limit: int,
        max_retries: int = 3,
        backoff_seconds: int = 300,
        backoff_multiplier: int = 3,
    ) -> int:
        """Raise once, then succeed once.

        Purpose:
            Exercise both exception and success branches inside loop mode.
        Args:
            db: Connected DB manager created by the script.
            limit: Batch limit from parsed args.
        Output:
            Raises once, then returns a processed count.
        """

        _ = db
        assert limit == 3
        _ = (max_retries, backoff_seconds, backoff_multiplier)
        calls["process"] += 1
        if calls["process"] == 1:
            raise RuntimeError("transient failure")
        return 2

    async def fake_sleep(_: int) -> None:
        """Advance loop iterations and stop after the second cycle.

        Purpose:
            Keep the loop test bounded while still allowing multiple cycles.
        Args:
            _: Poll interval seconds.
        Output:
            Raises `EndLoop` after two sleeps.
        """

        calls["sleep"] += 1
        if calls["sleep"] >= 2:
            raise EndLoop("done")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "jobs.db"
        monkeypatch.setenv("OPENAI_API_KEY", "test")
        monkeypatch.setattr(process_new_jobs, "load_dotenv", lambda: None)
        monkeypatch.setattr(
            argparse.ArgumentParser,
            "parse_args",
            lambda self: argparse.Namespace(loop=True, once=False, limit=3),
        )
        monkeypatch.setenv("AGENT_POLL_INTERVAL_SECONDS", "1")
        monkeypatch.setattr(process_new_jobs, "resolve_database_path", lambda: db_path)
        monkeypatch.setattr(process_new_jobs, "_process_once", fake_process_once)
        monkeypatch.setattr(process_new_jobs.asyncio, "sleep", fake_sleep)

        with pytest.raises(EndLoop):
            await process_new_jobs.main()

    assert calls["process"] == 2
    assert calls["sleep"] == 2


@pytest.mark.asyncio
async def test_main_once_flag_overrides_loop_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify `--once` forces single-run behavior even if `--loop` is present.

    Purpose:
        Enforce explicit one-shot mode semantics for CLI callers and tests.
    Args:
        monkeypatch: Pytest fixture used to control args and processing stubs.
    Output:
        Returns `None`; the test passes when only one cycle runs.
    """

    calls = {"process": 0}

    async def fake_process_once(
        *,
        db: DatabaseManager,
        limit: int,
        max_retries: int = 3,
        backoff_seconds: int = 300,
        backoff_multiplier: int = 3,
    ) -> int:
        """Record a single call for one-shot mode verification.

        Purpose:
            Confirm main exits after one batch when one-shot mode is selected.
        Args:
            db: Connected DB manager created by the script.
            limit: Batch limit from parsed args.
        Output:
            Returns a deterministic processed count.
        """

        _ = db
        assert limit == 1
        _ = (max_retries, backoff_seconds, backoff_multiplier)
        calls["process"] += 1
        return 1

    async def fail_sleep(_: int) -> None:
        """Fail the test if loop sleep is reached.

        Purpose:
            Ensure one-shot mode never enters polling sleep.
        Args:
            _: Poll interval seconds.
        Output:
            Raises `AssertionError`.
        """

        raise AssertionError("sleep should not run in one-shot mode")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "jobs.db"
        monkeypatch.setenv("OPENAI_API_KEY", "test")
        monkeypatch.setattr(process_new_jobs, "load_dotenv", lambda: None)
        monkeypatch.setattr(
            argparse.ArgumentParser,
            "parse_args",
            lambda self: argparse.Namespace(loop=True, once=True, limit=1),
        )
        monkeypatch.setattr(process_new_jobs, "resolve_database_path", lambda: db_path)
        monkeypatch.setattr(process_new_jobs, "_process_once", fake_process_once)
        monkeypatch.setattr(process_new_jobs.asyncio, "sleep", fail_sleep)

        await process_new_jobs.main()

    assert calls["process"] == 1
