"""Tests for the worker's ``_ensure_agent_browser_session`` helper.

The helper is the single point where the apply worker attaches the
agent-browser daemon to host Chrome before invoking the finisher.
Behavior under test:

- A successful ``connect`` returns ``(True, "")``.
- A missing binary surfaces a clear failure message so the caller
  can log + downgrade to RUNTIME_ERROR without retrying.
- The helper calls the shared CLI wrapper with exactly the
  ``["connect", <cdp_url>]`` argv.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.agents.apply_worker import browser as worker_browser


@pytest.mark.asyncio
async def test_session_bootstrap_returns_ok_on_successful_connect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A zero-exit connect produces ``(True, "")``."""

    captured: dict[str, Any] = {}

    async def fake_invoke(
        args: list[str],
        *,
        expect_json: bool = False,
        timeout_seconds: float = 20.0,
    ) -> dict[str, Any]:
        """Record the argv and return a canned success payload."""

        captured["args"] = list(args)
        return {
            "ok": True,
            "command": "agent-browser " + " ".join(args),
            "stdout": "connected",
            "stderr": "",
            "exit_code": 0,
        }

    monkeypatch.setattr(
        worker_browser, "invoke_agent_browser_cli", fake_invoke
    )

    ok, message = await worker_browser._ensure_agent_browser_session(
        "http://localhost:9222"
    )

    assert (ok, message) == (True, "")
    assert captured["args"] == ["connect", "http://localhost:9222"]


@pytest.mark.asyncio
async def test_session_bootstrap_surfaces_missing_binary_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing binary returns ``(False, message)`` with the helper's error."""

    async def fake_invoke(*_: Any, **__: Any) -> dict[str, Any]:
        """Return the launch-failure shape the shared helper emits."""

        return {
            "ok": False,
            "command": "agent-browser connect http://localhost:9222",
            "stdout": "",
            "stderr": "",
            "exit_code": -2,
            "error": "agent-browser CLI not on PATH — image is missing the binary",
        }

    monkeypatch.setattr(
        worker_browser, "invoke_agent_browser_cli", fake_invoke
    )

    ok, message = await worker_browser._ensure_agent_browser_session(
        "http://localhost:9222"
    )

    assert ok is False
    assert "not on PATH" in message
    assert message.startswith("agent-browser connect failed:")


@pytest.mark.asyncio
async def test_session_bootstrap_uses_stderr_when_no_error_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ``error`` is absent, the helper falls back to stderr text."""

    async def fake_invoke(*_: Any, **__: Any) -> dict[str, Any]:
        """Return a generic-failure shape lacking the ``error`` field."""

        return {
            "ok": False,
            "command": "agent-browser connect http://localhost:9222",
            "stdout": "",
            "stderr": "could not reach Chrome",
            "exit_code": 1,
        }

    monkeypatch.setattr(
        worker_browser, "invoke_agent_browser_cli", fake_invoke
    )

    _, message = await worker_browser._ensure_agent_browser_session(
        "http://localhost:9222"
    )

    assert "could not reach Chrome" in message
