"""Behavioral tests for ``src.agents.apply_finisher.browser_cli``.

The helper is the only place where the apply-finisher shells out to
the ``agent-browser`` binary. The finisher tool, the runner pre-flight,
and the worker CDP bootstrap all delegate here, so the test suite locks
down: success / error / timeout / launch-failure shapes, the
``--json`` auto-append rule, stdout truncation, and the empty-args
guard. ``asyncio.create_subprocess_exec`` is monkeypatched to avoid a
real subprocess.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from src.agents.apply_finisher import browser_cli


class _FakeProc:
    """Minimal stand-in for ``asyncio.subprocess.Process``.

    Attributes:
        returncode: Exit code surfaced after ``communicate`` resolves.
        _stdout: Bytes returned from the first ``communicate`` await.
        _stderr: Bytes returned from the first ``communicate`` await.
        _hang: When True, ``communicate`` never resolves so the caller
            triggers its ``asyncio.wait_for`` timeout path.
        _drain_stdout: Bytes returned by the post-kill drain.
        _drain_stderr: Bytes returned by the post-kill drain.
        kill_calls: Number of times ``kill`` was invoked.
    """

    def __init__(
        self,
        *,
        stdout: bytes = b"",
        stderr: bytes = b"",
        returncode: int = 0,
        hang: bool = False,
        drain_stdout: bytes = b"",
        drain_stderr: bytes = b"",
    ) -> None:
        """Configure the fake process behavior for one test."""

        self.returncode: int | None = returncode
        self._stdout = stdout
        self._stderr = stderr
        self._hang = hang
        self._drain_stdout = drain_stdout
        self._drain_stderr = drain_stderr
        self._first_call = True
        self.kill_calls = 0
        self.stdin_payloads: list[bytes | None] = []

    async def communicate(
        self, input: bytes | None = None
    ) -> tuple[bytes, bytes]:
        """Return stdout/stderr; hang forever on the first call when configured.

        Captures the optional ``input`` kwarg so tests covering the
        ``stdin_payload`` path can assert what was piped to stdin.
        """

        self.stdin_payloads.append(input)
        if self._first_call and self._hang:
            self._first_call = False
            await asyncio.sleep(60)
            return b"", b""
        if self._first_call:
            self._first_call = False
            return self._stdout, self._stderr
        return self._drain_stdout, self._drain_stderr

    def kill(self) -> None:
        """Record the SIGKILL invocation."""

        self.kill_calls += 1


def _install_fake_proc(
    monkeypatch: pytest.MonkeyPatch, proc: _FakeProc | Exception
) -> None:
    """Wire ``asyncio.create_subprocess_exec`` to a ``_FakeProc`` or raise.

    Args:
        monkeypatch: Pytest's monkeypatch fixture.
        proc: The proc double to return, or an exception to raise.
    """

    async def fake_exec(*args: Any, **kwargs: Any) -> _FakeProc:
        """Return the configured proc or raise the configured exception."""

        _ = (args, kwargs)
        if isinstance(proc, Exception):
            raise proc
        return proc

    monkeypatch.setattr(
        browser_cli.asyncio, "create_subprocess_exec", fake_exec
    )


@pytest.mark.asyncio
async def test_invoke_returns_ok_for_zero_exit_with_text_stdout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A zero-exit run with text stdout produces ``ok=True`` and the body."""

    _install_fake_proc(monkeypatch, _FakeProc(stdout=b"- textbox 'name'\n"))

    result = await browser_cli.invoke_agent_browser_cli(["snapshot", "-i", "-c"])

    assert result["ok"] is True
    assert result["exit_code"] == 0
    assert "textbox" in result["stdout"]
    assert "snapshot" in result["command"]
    assert "data" not in result


@pytest.mark.asyncio
async def test_invoke_parses_json_when_expect_json_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``expect_json=True`` parses stdout into the ``data`` field."""

    payload = {"url": "https://example.com/apply"}
    _install_fake_proc(
        monkeypatch, _FakeProc(stdout=json.dumps(payload).encode("utf-8"))
    )

    result = await browser_cli.invoke_agent_browser_cli(
        ["get", "url"], expect_json=True
    )

    assert result["ok"] is True
    assert result["data"] == payload


@pytest.mark.asyncio
async def test_invoke_does_not_double_append_json_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--json`` is appended once even if the caller already supplied it."""

    captured: dict[str, tuple[str, ...]] = {}

    async def fake_exec(*args: str, **kwargs: Any) -> _FakeProc:
        """Capture argv tail for assertion."""

        _ = kwargs
        captured["argv"] = args
        return _FakeProc(stdout=b"{}")

    monkeypatch.setattr(
        browser_cli.asyncio, "create_subprocess_exec", fake_exec
    )

    await browser_cli.invoke_agent_browser_cli(
        ["get", "url", "--json"], expect_json=True
    )

    assert captured["argv"].count("--json") == 1


@pytest.mark.asyncio
async def test_invoke_marks_failure_on_json_parse_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid JSON with ``expect_json`` flips ``ok`` to False with an error."""

    _install_fake_proc(monkeypatch, _FakeProc(stdout=b"not json"))

    result = await browser_cli.invoke_agent_browser_cli(
        ["snapshot"], expect_json=True
    )

    assert result["ok"] is False
    assert "JSON parse failure" in result["error"]


@pytest.mark.asyncio
async def test_invoke_returns_failure_for_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nonzero exit produces ``ok=False`` with the captured stderr."""

    _install_fake_proc(
        monkeypatch,
        _FakeProc(
            stderr=b"element not found", returncode=1
        ),
    )

    result = await browser_cli.invoke_agent_browser_cli(["click", "@e5"])

    assert result["ok"] is False
    assert result["exit_code"] == 1
    assert "element not found" in result["stderr"]


@pytest.mark.asyncio
async def test_invoke_returns_launch_failure_when_binary_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing binary surfaces ``-2`` with an actionable error string."""

    _install_fake_proc(monkeypatch, FileNotFoundError())

    result = await browser_cli.invoke_agent_browser_cli(["snapshot"])

    assert result["ok"] is False
    assert result["exit_code"] == -2
    assert "not on PATH" in result["error"]


@pytest.mark.asyncio
async def test_invoke_returns_failure_when_args_is_empty() -> None:
    """An empty args list is rejected without spawning a subprocess."""

    result = await browser_cli.invoke_agent_browser_cli([])

    assert result["ok"] is False
    assert result["exit_code"] == -2
    assert "args is empty" in result["error"]


@pytest.mark.asyncio
async def test_invoke_kills_and_drains_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A hanging process is killed and the post-kill drain is captured."""

    fake = _FakeProc(hang=True, drain_stdout=b"partial", drain_stderr=b"err")
    _install_fake_proc(monkeypatch, fake)

    result = await browser_cli.invoke_agent_browser_cli(
        ["wait", "10000"], timeout_seconds=0.05
    )

    assert result["ok"] is False
    assert result["exit_code"] == -1
    assert result["error"].startswith("timeout after")
    assert fake.kill_calls == 1


@pytest.mark.asyncio
async def test_invoke_truncates_overlong_stdout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stdout above the cap is truncated to the cap byte length."""

    blob = b"x" * (browser_cli._MAX_STDOUT_BYTES + 5_000)
    _install_fake_proc(monkeypatch, _FakeProc(stdout=blob))

    result = await browser_cli.invoke_agent_browser_cli(["snapshot"])

    assert len(result["stdout"]) == browser_cli._MAX_STDOUT_BYTES


@pytest.mark.asyncio
async def test_invoke_pipes_stdin_payload_when_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``stdin_payload`` is encoded and passed to subprocess.communicate."""

    fake = _FakeProc(stdout=b"[]")
    _install_fake_proc(monkeypatch, fake)

    payload = '[["get","url"]]'
    result = await browser_cli.invoke_agent_browser_cli(
        ["batch", "--json"], stdin_payload=payload
    )

    assert result["ok"] is True
    assert fake.stdin_payloads == [payload.encode("utf-8")]


@pytest.mark.asyncio
async def test_invoke_omits_stdin_when_no_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without ``stdin_payload`` no bytes are piped to the subprocess."""

    fake = _FakeProc(stdout=b"")
    _install_fake_proc(monkeypatch, fake)

    await browser_cli.invoke_agent_browser_cli(["get", "url"])

    assert fake.stdin_payloads == [None]
