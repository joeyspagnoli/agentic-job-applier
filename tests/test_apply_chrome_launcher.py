"""Validate display-specific Xvfb startup checks in Chrome launcher script.

Purpose:
    Guard against regressions where the launcher only checks global Xvfb
    process existence and skips required display initialization.
"""

from __future__ import annotations

from pathlib import Path


def test_start_chrome_launcher_checks_target_display_socket_and_process() -> None:
    """Verify launcher validates the requested X display before skipping Xvfb.

    Purpose:
        Regress M-002 by asserting the script checks both display-specific
        process arguments and the expected X11 socket path.
    Args:
        None.
    Output:
        Returns `None`; test passes when both checks are present in script text.
    """

    script_path = Path("deploy/start-chrome-cdp.sh")
    script_text = script_path.read_text(encoding="utf-8")

    assert "DISPLAY_NUMBER=\"${DISPLAY#:}\"" in script_text
    assert "DISPLAY_SOCKET=\"/tmp/.X11-unix/X${DISPLAY_NUMBER}\"" in script_text
    assert "pgrep -af \"Xvfb[[:space:]]+${DISPLAY}([[:space:]]|$)\"" in script_text
    assert "[ ! -S \"${DISPLAY_SOCKET}\" ]" in script_text
