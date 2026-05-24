"""Timeout-path tests for `src.agents.resume_tailor.compiler`.

Purpose:
    The Phase 1-4 handoff calls out timeout enforcement as the one
    compiler branch the existing `test_compiler_tectonic.py` doesn't
    cover: a deliberately-slow tectonic invocation must raise
    `ResumeCompileError` rather than hang. Tested by simulating
    `subprocess.TimeoutExpired` via monkeypatch — the actual binary
    isn't on PATH in this environment.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from src.agents.resume_tailor.compiler import (
    ResumeCompileError,
    compile_resume_tex,
)


def _write_minimal_tex(tmp_path: Path) -> Path:
    """Write the smallest valid `.tex` source for the compiler to consume.

    Purpose:
        Keep each test focused on the timeout path — file content is
        irrelevant because the patched `subprocess.run` never executes
        the binary against it.
    Args:
        tmp_path: pytest-provided per-test temp dir.
    Output:
        Path to the written `.tex` file.
    """

    source_path = tmp_path / "resume.tex"
    source_path.write_text(
        "\\documentclass{article}\\begin{document}\\end{document}",
        encoding="utf-8",
    )
    return source_path


def test_tectonic_timeout_raises_resume_compile_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A `subprocess.TimeoutExpired` from tectonic surfaces as `ResumeCompileError`."""

    monkeypatch.delenv("RESUME_COMPILER", raising=False)
    monkeypatch.setattr(
        "src.agents.resume_tailor.compiler.shutil.which",
        lambda _cmd: "/fake/path/to/tectonic",
    )

    def _slow_run(_args: list[str], **_kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired(cmd="tectonic", timeout=1)

    monkeypatch.setattr(
        "src.agents.resume_tailor.compiler.subprocess.run", _slow_run
    )

    source_path = _write_minimal_tex(tmp_path)

    with pytest.raises(ResumeCompileError, match="timed out"):
        compile_resume_tex(tex_path=source_path, timeout_seconds=1)


def test_tectonic_timeout_error_message_includes_seconds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The timeout error message must surface the configured seconds value."""

    monkeypatch.delenv("RESUME_COMPILER", raising=False)
    monkeypatch.setattr(
        "src.agents.resume_tailor.compiler.shutil.which",
        lambda _cmd: "/fake/path/to/tectonic",
    )

    def _slow_run(_args: list[str], **_kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired(cmd="tectonic", timeout=42)

    monkeypatch.setattr(
        "src.agents.resume_tailor.compiler.subprocess.run", _slow_run
    )

    source_path = _write_minimal_tex(tmp_path)

    with pytest.raises(ResumeCompileError, match="42 seconds"):
        compile_resume_tex(tex_path=source_path, timeout_seconds=42)


def test_latexmk_timeout_also_raises_resume_compile_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The legacy latexmk branch must also surface timeouts as `ResumeCompileError`."""

    monkeypatch.setenv("RESUME_COMPILER", "latexmk")

    def _slow_run(_args: list[str], **_kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired(cmd="latexmk", timeout=1)

    monkeypatch.setattr(
        "src.agents.resume_tailor.compiler.subprocess.run", _slow_run
    )

    source_path = _write_minimal_tex(tmp_path)

    with pytest.raises(ResumeCompileError, match="latexmk timed out"):
        compile_resume_tex(tex_path=source_path, timeout_seconds=1)
