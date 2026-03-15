"""Validate one-shot pipeline exit semantics and signaling behavior."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from scripts import run_pipeline_once as pipeline_script
from scripts.process_new_jobs import ModelConfigurationError


@pytest.mark.asyncio
async def test_run_pipeline_once_returns_processed_count_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify one-shot pipeline returns processed gate count on success.

    Purpose:
        Ensure orchestration callers can rely on the returned processed count
        for success reporting and follow-up automation.
    Args:
        monkeypatch: Pytest fixture used to stub discovery, DB, and gate calls.
    Output:
        Returns `None`; test passes when processed count is returned unchanged.
    """

    calls = {"discovery": 0, "process_once": 0}

    class FakeDatabaseManager:
        """Provide a lightweight async DB context for pipeline tests."""

        def __init__(self, db_path: str) -> None:
            """Store the db path for constructor parity.

            Purpose:
                Keep the fake manager signature aligned with production code.
            Args:
                self: Fake DB manager instance.
                db_path: SQLite path passed by the script.
            Output:
                Returns `None`.
            """

            self.db_path = db_path

        async def __aenter__(self) -> "FakeDatabaseManager":
            """Return this manager from async context entry.

            Purpose:
                Match the production async context-manager contract.
            Args:
                self: Fake DB manager instance.
            Output:
                Returns `self`.
            """

            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
            """Provide no-op async context exit behavior.

            Purpose:
                Keep context-manager cleanup parity in tests.
            Args:
                self: Fake DB manager instance.
                exc_type: Exception type raised in context, if any.
                exc_val: Exception value raised in context, if any.
                exc_tb: Exception traceback raised in context, if any.
            Output:
                Returns `None`.
            """

            _ = (exc_type, exc_val, exc_tb)

        async def create_tables(self) -> None:
            """Track schema bootstrap invocation.

            Purpose:
                Assert script performs expected startup sequence before work.
            Args:
                self: Fake DB manager instance.
            Output:
                Returns `None`.
            """

        async def migrate_agent_schema(self) -> None:
            """Track agent-migration invocation.

            Purpose:
                Assert script performs expected startup sequence before work.
            Args:
                self: Fake DB manager instance.
            Output:
                Returns `None`.
            """

    async def fake_discovery() -> None:
        """Count discovery invocation for orchestration assertions.

        Purpose:
            Replace live discovery so the test remains deterministic.
        Args:
            None.
        Output:
            Returns `None`.
        """

        calls["discovery"] += 1

    async def fake_process_once(**kwargs: object) -> int:
        """Return a deterministic processed count from gate batch.

        Purpose:
            Simulate successful gate processing for one-shot orchestration.
        Args:
            **kwargs: Keyword arguments from production call site.
        Output:
            Returns a deterministic processed row count.
        """

        assert kwargs["limit"] == 7
        calls["process_once"] += 1
        return 3

    monkeypatch.setattr(pipeline_script, "run_job_discovery", fake_discovery)
    monkeypatch.setattr(pipeline_script, "DatabaseManager", FakeDatabaseManager)
    monkeypatch.setattr(
        pipeline_script, "resolve_database_path", lambda: Path("jobs.db")
    )
    monkeypatch.setattr(pipeline_script, "process_once", fake_process_once)

    processed = await pipeline_script.run_pipeline_once(limit=7)

    assert processed == 3
    assert calls["discovery"] == 1
    assert calls["process_once"] == 1


@pytest.mark.asyncio
async def test_main_returns_non_zero_on_model_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify one-shot CLI exits non-zero when model config is invalid.

    Purpose:
        Prevent false-green scheduler runs when gate model configuration fails.
    Args:
        monkeypatch: Pytest fixture used to stub args and pipeline execution.
    Output:
        Returns `None`; test passes when `main()` returns exit code `1`.
    """

    error_messages: list[str] = []
    monkeypatch.setattr(pipeline_script, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        argparse.ArgumentParser,
        "parse_args",
        lambda self: argparse.Namespace(limit=5),
    )

    async def fail_pipeline(*, limit: int) -> int:
        """Raise deterministic configuration failure for main-path tests.

        Purpose:
            Trigger the CLI failure branch without running live dependencies.
        Args:
            limit: CLI-provided batch limit.
        Output:
            Raises `ModelConfigurationError`.
        """

        assert limit == 5
        raise ModelConfigurationError("missing model key")

    monkeypatch.setattr(pipeline_script, "run_pipeline_once", fail_pipeline)
    monkeypatch.setattr(
        pipeline_script.logger,
        "error",
        lambda message, *args: error_messages.append(message.format(*args)),
    )

    exit_code = await pipeline_script.main()

    assert exit_code == 1
    assert any("missing model key" in message for message in error_messages)


@pytest.mark.asyncio
async def test_main_logs_processed_count_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify one-shot CLI logs processed count and returns zero on success.

    Purpose:
        Ensure successful pipeline runs emit an explicit processed-count log for
        operators and return a shell-success exit code.
    Args:
        monkeypatch: Pytest fixture used to stub args and pipeline execution.
    Output:
        Returns `None`; test passes when success log includes processed count.
    """

    info_messages: list[str] = []
    monkeypatch.setattr(pipeline_script, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        argparse.ArgumentParser,
        "parse_args",
        lambda self: argparse.Namespace(limit=9),
    )

    async def succeed_pipeline(*, limit: int) -> int:
        """Return deterministic processed count for success-path tests.

        Purpose:
            Exercise success signaling without invoking external systems.
        Args:
            limit: CLI-provided batch limit.
        Output:
            Returns a deterministic processed row count.
        """

        assert limit == 9
        return 4

    monkeypatch.setattr(pipeline_script, "run_pipeline_once", succeed_pipeline)
    monkeypatch.setattr(
        pipeline_script.logger,
        "info",
        lambda message, *args: info_messages.append(message.format(*args)),
    )

    exit_code = await pipeline_script.main()

    assert exit_code == 0
    assert any("processed 4 jobs" in message for message in info_messages)
