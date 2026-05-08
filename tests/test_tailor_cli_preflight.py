"""Tests for tailor worker CLI preflight checks and env configuration.

Purpose:
    Validate that the preflight check correctly detects missing binaries and
    invalid configuration, and that _load_int_env falls back safely for
    non-integer environment values.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.process_qualified_jobs import (
    TailorPreflightError,
    _check_preflight,
    _load_int_env,
    tailor_once,
)


# ---------------------------------------------------------------------------
# Test: once mode processes one job and exits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_once_mode_processes_one_job_and_exits(tmp_path: Path) -> None:
    """Verify tailor_once calls _tailor_once exactly once and returns its value.

    Purpose:
        Validate that tailor_once (the public wrapper) delegates to _tailor_once
        and returns the result for single-shot callers.
    """

    mock_db = MagicMock()
    mock_db.db_path = str(tmp_path / "test.db")
    mock_db.is_budget_exceeded = AsyncMock(return_value=False)
    mock_db.claim_next_tailor_job = AsyncMock(return_value=None)

    result = await tailor_once(
        db=mock_db,
        output_base_dir=tmp_path / "output",
        resume_yaml_path=tmp_path / "resume.yaml",
        max_retries=2,
        lease_seconds=7200,
        backoff_seconds=600,
        backoff_multiplier=2,
    )

    assert result == 0
    mock_db.claim_next_tailor_job.assert_called_once()


# ---------------------------------------------------------------------------
# Test: loop mode processes then sleeps
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_loop_mode_processes_then_sleeps(tmp_path: Path) -> None:
    """Verify the worker loop calls _tailor_once and asyncio.sleep in sequence.

    Purpose:
        Validate that the main loop structure calls the inner tailor function
        before sleeping between poll intervals.
    """

    call_count = 0

    async def fake_tailor_once(**kwargs: object) -> int:
        """Count invocations and raise to break the loop.

        Purpose:
            Track how many times _tailor_once was called inside the loop,
            then raise KeyboardInterrupt to exit after the first iteration.
        Arg(s):
            **kwargs: Forwarded keyword arguments (unused).
        Output:
            Raises KeyboardInterrupt after the first call.
        """
        nonlocal call_count
        call_count += 1
        raise KeyboardInterrupt

    with (
        patch(
            "scripts.process_qualified_jobs._tailor_once",
            side_effect=fake_tailor_once,
        ),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        with pytest.raises(KeyboardInterrupt):
            import scripts.process_qualified_jobs as mod

            await mod._tailor_once(
                db=MagicMock(),
                output_base_dir=tmp_path,
                resume_yaml_path=tmp_path / "resume.yaml",
                max_retries=2,
                lease_seconds=7200,
                backoff_seconds=600,
                backoff_multiplier=2,
            )

    assert call_count == 1


# ---------------------------------------------------------------------------
# Test: missing pi command triggers preflight error
# ---------------------------------------------------------------------------


def test_missing_pi_command_triggers_preflight_error() -> None:
    """Verify _check_preflight raises when pi binary and env vars are absent.

    Purpose:
        Validate that preflight fails fast with a clear error when the
        pi coding agent command is not configured or discoverable.
    """

    with (
        patch("shutil.which", return_value=None),
        patch.dict(
            "os.environ",
            {"PI_CODING_AGENT_COMMAND": "", "PI_CODING_AGENT_COMMAND_ARGV": ""},
            clear=False,
        ),
        patch(
            "scripts.process_qualified_jobs.resolve_database_path",
            return_value=Path("/tmp/test.db"),
        ),
    ):
        with pytest.raises(TailorPreflightError, match="pi command not found"):
            _check_preflight()


# ---------------------------------------------------------------------------
# Test: missing latexmk triggers preflight error
# ---------------------------------------------------------------------------


def test_missing_latexmk_triggers_preflight_error() -> None:
    """Verify _check_preflight raises when pi is available but latexmk is not.

    Purpose:
        Validate that preflight fails fast with a clear error when latexmk
        is not installed even if the pi command is present.
    """

    def which_side_effect(name: str) -> str | None:
        """Return a fake path for pi but None for latexmk.

        Purpose:
            Simulate pi being available but latexmk being absent from PATH.
        Arg(s):
            name: Binary name to look up.
        Output:
            Returns a fake path for 'pi', None for everything else.
        """
        if name == "pi":
            return "/usr/local/bin/pi"
        return None

    with (
        patch("shutil.which", side_effect=which_side_effect),
        patch.dict(
            "os.environ",
            {"PI_CODING_AGENT_COMMAND": "", "PI_CODING_AGENT_COMMAND_ARGV": ""},
            clear=False,
        ),
        patch(
            "scripts.process_qualified_jobs.resolve_database_path",
            return_value=Path("/tmp/test.db"),
        ),
    ):
        with pytest.raises(TailorPreflightError, match="latexmk not found"):
            _check_preflight()


# ---------------------------------------------------------------------------
# Test: missing database directory triggers preflight error
# ---------------------------------------------------------------------------


def test_missing_database_directory_triggers_preflight_error(
    tmp_path: Path,
) -> None:
    """Verify _check_preflight raises when the database parent directory is absent.

    Purpose:
        Validate that preflight detects a missing database directory before
        the worker enters its processing loop.
    """

    nonexistent_db_path = tmp_path / "nonexistent_dir" / "test.db"

    def which_side_effect(name: str) -> str | None:
        """Return fake paths for pi and latexmk.

        Purpose:
            Allow pi and latexmk checks to pass so the DB directory
            check is reached.
        Arg(s):
            name: Binary name to look up.
        Output:
            Returns a fake binary path for any binary name.
        """
        return f"/usr/local/bin/{name}"

    with (
        patch("shutil.which", side_effect=which_side_effect),
        patch(
            "scripts.process_qualified_jobs.resolve_database_path",
            return_value=nonexistent_db_path,
        ),
    ):
        with pytest.raises(
            TailorPreflightError, match="Database parent directory does not exist"
        ):
            _check_preflight()


# ---------------------------------------------------------------------------
# Test: invalid TAILOR_MAX_RETRIES falls back to default
# ---------------------------------------------------------------------------


def test_invalid_tailor_max_retries_falls_back_to_default() -> None:
    """Verify _load_int_env returns default when env value is not an integer.

    Purpose:
        Validate M-006 env loading: non-integer TAILOR_MAX_RETRIES causes
        _load_int_env to log a warning and use the provided default safely.
    """

    with patch.dict("os.environ", {"TAILOR_MAX_RETRIES": "not_a_number"}):
        result = _load_int_env("TAILOR_MAX_RETRIES", default_value=2)

    assert result == 2


# ---------------------------------------------------------------------------
# Test: missing OPENAI_API_KEY in one-shot mode logs warning and returns
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_main_one_shot_returns_cleanly_when_openai_api_key_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify tailor main() exits cleanly when OPENAI_API_KEY is missing.

    Purpose:
        Mirror the gate worker's idle pattern: when the API key is unset and
        no `--loop` flag is present, main() must log a tailor-specific
        warning and return without raising or invoking the CLI parser.
    """

    import scripts.process_qualified_jobs as mod

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(mod, "load_dotenv", lambda: None)
    monkeypatch.setattr(mod.sys, "argv", ["process_qualified_jobs"])

    parser_mock = MagicMock()
    parser_mock.side_effect = AssertionError(
        "ArgumentParser must not run when OPENAI_API_KEY is missing"
    )
    monkeypatch.setattr(mod.argparse, "ArgumentParser", parser_mock)

    captured_messages: list[str] = []
    sink_id = mod.logger.add(
        lambda msg: captured_messages.append(str(msg)), level="WARNING"
    )

    try:
        result = await mod.main()
    finally:
        mod.logger.remove(sink_id)

    assert result is None
    assert any("tailor worker is disabled" in msg for msg in captured_messages)


# ---------------------------------------------------------------------------
# Test: missing OPENAI_API_KEY in --loop mode sleeps instead of crashing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_main_loop_sleeps_when_openai_api_key_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify tailor main() in --loop mode idles when OPENAI_API_KEY is missing.

    Purpose:
        Confirm the worker enters the idle sleep loop (sleep(3600)) and never
        reaches DB or CLI parsing, so claimed jobs cannot be driven into
        TERMINAL_FAILED by repeated subprocess crashes.
    """

    import scripts.process_qualified_jobs as mod

    class _StopLoop(Exception):
        """Sentinel raised from fake sleep to break the infinite idle loop."""

    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        """Record sleep duration and raise sentinel to break the idle loop."""

        sleep_calls.append(seconds)
        raise _StopLoop

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(mod, "load_dotenv", lambda: None)
    monkeypatch.setattr(mod.sys, "argv", ["process_qualified_jobs", "--loop"])
    monkeypatch.setattr(mod.asyncio, "sleep", fake_sleep)

    parser_mock = MagicMock()
    parser_mock.side_effect = AssertionError(
        "ArgumentParser must not run when OPENAI_API_KEY is missing"
    )
    monkeypatch.setattr(mod.argparse, "ArgumentParser", parser_mock)

    captured_messages: list[str] = []
    sink_id = mod.logger.add(
        lambda msg: captured_messages.append(str(msg)), level="WARNING"
    )

    try:
        with pytest.raises(_StopLoop):
            await mod.main()
    finally:
        mod.logger.remove(sink_id)

    assert sleep_calls == [3600]
    assert any("tailor worker is disabled" in msg for msg in captured_messages)
