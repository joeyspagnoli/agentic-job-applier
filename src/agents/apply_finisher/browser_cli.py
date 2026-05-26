"""Subprocess wrapper for the ``agent-browser`` CLI.

Single source of truth for spawning the ``agent-browser`` binary.
Three call sites consume it:

- The finisher's Pydantic AI ``agent_browser`` tool (``tools.py``)
  during the agent loop.
- The runner's pre-flight ``get url`` health check (``runner.py``)
  before the agent loop starts.
- The worker's one-time ``connect <CDP_URL>`` bootstrap
  (``apply_worker/browser.py``) before invoking ``run_finisher``.

All three need the same launch / timeout / output-truncation behavior,
so the implementation lives in one place. The function is
intentionally context-free (no Pydantic AI dependency, no
``RunContext``) so it can be called from anywhere on the async event
loop.
"""

from __future__ import annotations

import asyncio
import json
import shlex
from typing import Any

from loguru import logger

# Cap on captured stdout bytes. Snapshots of dense apply forms can hit
# 8-15KB; 60KB leaves headroom while preventing a pathological page
# from flooding the model's context window.
_MAX_STDOUT_BYTES: int = 60_000

# Cap on captured stderr bytes — errors are usually short.
_MAX_STDERR_BYTES: int = 4_000

# Exit codes the helper synthesizes (real binaries are >= 0).
_EXIT_CODE_TIMEOUT: int = -1
_EXIT_CODE_LAUNCH_FAILURE: int = -2

# Module-level lock serializing all agent-browser CLI invocations.
# Pydantic AI fires tool_calls concurrently when the model emits multiple
# in a single message turn; for browser interactions this is wrong —
# clicking 6 dropdowns in parallel only opens one listbox (the others
# fire on closed widgets and silently no-op). The lock forces strict
# sequential execution so the agent's reasoning matches reality.
_CLI_LOCK = asyncio.Lock()

# How long to wait for a killed process to drain its pipes after we
# fire SIGKILL on a timeout. Bounded so a wedged child can't keep us
# blocked indefinitely.
_KILL_DRAIN_TIMEOUT_SECONDS: float = 2.0


async def _capture_killed_output(
    proc: asyncio.subprocess.Process,
) -> tuple[bytes, bytes]:
    """Drain a killed subprocess' stdout/stderr without hanging.

    Purpose:
        ``proc.kill()`` followed by ``proc.wait()`` does not consume
        buffered pipe data, so a wedged child can hold file descriptors
        open. Re-running ``communicate`` with a short ceiling drains
        the pipes; if it ever exceeds that ceiling we accept empty
        output rather than block the caller.
    Args:
        proc: The subprocess we just SIGKILLed.
    Returns:
        ``(stdout, stderr)`` byte tuples captured during draining;
        either may be empty on a hard hang.
    """

    try:
        return await asyncio.wait_for(
            proc.communicate(), timeout=_KILL_DRAIN_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        return b"", b""


def _build_args(args: list[str], expect_json: bool) -> list[str]:
    """Apply the ``--json`` auto-append rule.

    Purpose:
        When the caller wants JSON parsing, append ``--json`` to argv
        unless the caller already passed it. agent-browser accepts
        ``--json`` as a global flag anywhere in argv.
    Args:
        args: CLI argv tail (no leading executable).
        expect_json: When True, ensures ``--json`` is present.
    Returns:
        Possibly-extended copy of ``args``.
    """

    full = list(args)
    if expect_json and "--json" not in full:
        full.append("--json")
    return full


def _format_display(args: list[str]) -> str:
    """Render argv as a shell-quoted string for log lines.

    Args:
        args: CLI argv tail without the executable name.
    Returns:
        ``agent-browser <args...>`` with each arg shell-quoted, safe
        to paste into a terminal for debugging.
    """

    return "agent-browser " + " ".join(shlex.quote(a) for a in args)


async def invoke_agent_browser_cli(
    args: list[str],
    *,
    expect_json: bool = False,
    timeout_seconds: float = 20.0,
    stdin_payload: str | None = None,
) -> dict[str, Any]:
    """Run an ``agent-browser`` CLI command and return a structured dict.

    Purpose:
        Single helper the finisher tool, runner pre-flight, and worker
        bootstrap all delegate to. Wraps ``asyncio.create_subprocess_exec``
        with timeout, output truncation, optional JSON parsing, and a
        structured-failure shape so callers never have to ``try/except``
        around subprocess primitives.
    Args:
        args: CLI argv tail, e.g. ``["snapshot", "-i", "-c"]``. The
            ``agent-browser`` executable is prepended automatically.
            Never include it in ``args``.
        expect_json: When True, appends ``--json`` to argv (if absent)
            and parses stdout as JSON into the ``data`` field. On parse
            failure ``ok`` becomes False and ``error`` describes why.
        timeout_seconds: Hard wall-clock cap. Defaults to 20s.
        stdin_payload: Optional UTF-8 string piped to the subprocess'
            stdin. Used by ``batch`` invocations that pass a JSON array
            of commands via stdin to sidestep shell-quoting on
            user-controlled filter strings.
    Returns:
        Dict with keys:
          - ``ok`` (bool): True iff exit_code == 0 and (when applicable)
            JSON parsed successfully.
          - ``command`` (str): Shell-quoted argv for log readability.
          - ``stdout`` (str): Captured stdout, truncated to
            ``_MAX_STDOUT_BYTES``.
          - ``stderr`` (str): Captured stderr, truncated to
            ``_MAX_STDERR_BYTES``.
          - ``exit_code`` (int): Process exit code; ``-1`` on timeout,
            ``-2`` on launch failure (binary missing).
          - ``data`` (Any, optional): Parsed JSON when ``expect_json``.
          - ``error`` (str, optional): Human-readable failure summary.
    """

    if not args:
        return {
            "ok": False,
            "command": "agent-browser",
            "stdout": "",
            "stderr": "",
            "exit_code": _EXIT_CODE_LAUNCH_FAILURE,
            "error": "args is empty — pass at least one subcommand",
        }

    full_args = _build_args(args, expect_json)
    display = _format_display(full_args)

    async with _CLI_LOCK:
        return await _invoke_locked(
            full_args, display, expect_json, timeout_seconds, stdin_payload
        )


async def _invoke_locked(
    full_args: list[str],
    display: str,
    expect_json: bool,
    timeout_seconds: float,
    stdin_payload: str | None,
) -> dict[str, Any]:
    """Run the CLI subprocess inside the global serialization lock.

    Split out from :func:`invoke_agent_browser_cli` so the lock-acquire is the
    only thing the public entry point does on the happy path — keeps the lock
    body short and the function readable.
    """

    logger.debug("agent_browser exec: {}", display)

    try:
        proc = await asyncio.create_subprocess_exec(
            "agent-browser",
            *full_args,
            stdin=asyncio.subprocess.PIPE if stdin_payload is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        logger.error("agent-browser binary missing on PATH ({})", display)
        return {
            "ok": False,
            "command": display,
            "stdout": "",
            "stderr": "",
            "exit_code": _EXIT_CODE_LAUNCH_FAILURE,
            "error": (
                "agent-browser CLI not on PATH — image is missing the "
                "binary; rebuild with the agent-browser COPY step."
            ),
        }

    stdin_bytes = (
        stdin_payload.encode("utf-8") if stdin_payload is not None else None
    )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(input=stdin_bytes), timeout=timeout_seconds
        )
    except asyncio.TimeoutError:
        proc.kill()
        stdout_bytes, stderr_bytes = await _capture_killed_output(proc)
        logger.warning(
            "agent_browser timeout after {}s: {}", timeout_seconds, display
        )
        return {
            "ok": False,
            "command": display,
            "stdout": stdout_bytes.decode("utf-8", errors="replace")[
                :_MAX_STDOUT_BYTES
            ],
            "stderr": stderr_bytes.decode("utf-8", errors="replace")[
                :_MAX_STDERR_BYTES
            ]
            or f"timeout after {timeout_seconds}s",
            "exit_code": _EXIT_CODE_TIMEOUT,
            "error": f"timeout after {timeout_seconds}s",
        }

    stdout = stdout_bytes.decode("utf-8", errors="replace")[:_MAX_STDOUT_BYTES]
    stderr = stderr_bytes.decode("utf-8", errors="replace")[:_MAX_STDERR_BYTES]
    exit_code = proc.returncode or 0
    logger.debug(
        "agent_browser done: exit={} stdout_bytes={} stderr_bytes={}",
        exit_code,
        len(stdout),
        len(stderr),
    )

    result: dict[str, Any] = {
        "ok": exit_code == 0,
        "command": display,
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
    }

    if expect_json and exit_code == 0:
        try:
            result["data"] = json.loads(stdout) if stdout.strip() else None
        except json.JSONDecodeError as exc:
            result["ok"] = False
            result["error"] = f"JSON parse failure: {exc}"

    return result


__all__ = ["invoke_agent_browser_cli"]
