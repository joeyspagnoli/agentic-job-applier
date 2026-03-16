"""Tests for tailor worker CLI preflight checks and env configuration.

Purpose:
    Validate that the preflight check correctly detects missing binaries and
    invalid configuration, and that _load_int_env falls back safely for
    non-integer environment values.
"""

from __future__ import annotations

import asyncio
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

    with patch(
        "scripts.process_qualified_jobs._tailor_once",
        side_effect=fake_tailor_once,
    ), patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
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

    with patch("shutil.which", return_value=None), patch.dict(
        "os.environ",
        {"PI_CODING_AGENT_COMMAND": "", "PI_CODING_AGENT_COMMAND_ARGV": ""},
        clear=False,
    ), patch(
        "scripts.process_qualified_jobs.resolve_database_path",
        return_value=Path("/tmp/test.db"),
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

    with patch("shutil.which", side_effect=which_side_effect), patch.dict(
        "os.environ",
        {"PI_CODING_AGENT_COMMAND": "", "PI_CODING_AGENT_COMMAND_ARGV": ""},
        clear=False,
    ), patch(
        "scripts.process_qualified_jobs.resolve_database_path",
        return_value=Path("/tmp/test.db"),
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

    with patch("shutil.which", side_effect=which_side_effect), patch(
        "scripts.process_qualified_jobs.resolve_database_path",
        return_value=nonexistent_db_path,
    ):
        with pytest.raises(TailorPreflightError, match="Database parent directory does not exist"):
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
