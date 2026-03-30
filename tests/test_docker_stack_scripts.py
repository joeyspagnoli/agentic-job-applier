"""Verify host lifecycle scripts target the expected docker compose commands.

Purpose:
    Keep non-technical start/stop/restart entry points aligned with the
    canonical compose lifecycle behavior used by the dashboard endpoints.
"""

from __future__ import annotations

from pathlib import Path


def _read_script_text(script_name: str) -> str:
    """Read one lifecycle script from `scripts/docker`.

    Purpose:
        Centralize script-path resolution for lifecycle script contract tests.
    Args:
        script_name: File name under `scripts/docker`.
    Output:
        Returns script text as UTF-8.
    """

    script_path = Path("scripts") / "docker" / script_name
    return script_path.read_text(encoding="utf-8")


def test_start_stack_script_uses_compose_up_detached() -> None:
    """Verify start script starts the stack with detached compose up.

    Purpose:
        Ensure host-level startup uses the canonical non-interactive command.
    Args:
        None.
    Output:
        Returns `None`; test passes when script includes expected command.
    """

    script_text = _read_script_text("start_stack.sh")

    assert "set -euo pipefail" in script_text
    assert "docker compose up -d" in script_text


def test_stop_stack_script_uses_non_destructive_compose_down() -> None:
    """Verify stop script uses non-destructive compose down.

    Purpose:
        Prevent regressions that would accidentally remove volumes during stop.
    Args:
        None.
    Output:
        Returns `None`; test passes when script includes expected command.
    """

    script_text = _read_script_text("stop_stack.sh")

    assert "set -euo pipefail" in script_text
    assert "docker compose down" in script_text
    assert "docker compose down -v" not in script_text


def test_restart_stack_script_runs_down_then_up() -> None:
    """Verify restart script runs compose down followed by detached up.

    Purpose:
        Ensure restart behavior remains equivalent to stop then start.
    Args:
        None.
    Output:
        Returns `None`; test passes when restart script includes both commands.
    """

    script_text = _read_script_text("restart_stack.sh")

    assert "set -euo pipefail" in script_text
    assert "docker compose down" in script_text
    assert "docker compose up -d" in script_text
