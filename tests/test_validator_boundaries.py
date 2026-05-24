"""Boundary tests for `src.agents.resume_tailor.validator`.

Purpose:
    Cover Risk Areas #6 (compile-check skip path when `tectonic` is
    absent), #7 (external boundary calls — `tempfile.TemporaryDirectory`
    and `subprocess.run` in `_run_compile_check`), plus the helper math
    in `_line_number_of` and `_first_log_error_line`.

`tectonic` is not installed in the test environment, which makes the
skip path the natural default; the "tectonic-present, non-zero exit"
case is simulated via `monkeypatch` per the handoff's suggested approach.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

import src.agents.resume_tailor.validator as validator_module
from src.agents.resume_tailor.validator import (
    _first_log_error_line,
    _line_number_of,
    validate_resume_tex,
)


# ---------------------------------------------------------------------------
# Risk #6 — compile-check skip path
# ---------------------------------------------------------------------------


def test_compile_check_silently_skipped_when_tectonic_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Risk #6 — no tectonic on PATH must yield `ok=True` for a conforming `.tex`."""

    monkeypatch.setattr(
        "src.agents.resume_tailor.validator.shutil.which", lambda _: None
    )

    # Smallest possible conforming document (Jake's-family).
    tex = (
        "\\documentclass{article}\n"
        "\\newcommand{\\resumeItem}[1]{\\item #1}\n"
        "\\newcommand{\\resumeSubheading}[4]"
        "{\\item \\textbf{#1} \\hfill \\textbf{#2}\\\\#3\\hfill#4}\n"
        "\\begin{document}\n"
        "\\section{Experience}\n"
        "\\begin{itemize}\n"
        "  \\resumeSubheading{Engineer}{2024}{Acme}{Remote}\n"
        "    \\begin{itemize}\\resumeItem{Built X.}\\end{itemize}\n"
        "\\end{itemize}\n"
        "\\end{document}\n"
    )

    report = validate_resume_tex(tex, run_compile_check=True)

    assert report.ok is True
    assert report.errors == []
    # The manifest preview should still be populated since the static
    # checks ran and passed.
    assert report.manifest_preview is not None


# ---------------------------------------------------------------------------
# Risk #7 — tectonic present + non-zero exit, with and without a log file
# ---------------------------------------------------------------------------


def _simulate_tectonic(
    *,
    monkeypatch: pytest.MonkeyPatch,
    returncode: int,
    log_text: str | None,
    stderr_text: str = "",
) -> dict[str, list[Path]]:
    """Wire up monkeypatches that simulate a `tectonic` invocation.

    Purpose:
        Centralize the `shutil.which` + `subprocess.run` patch wiring so
        each compile-failure test only specifies the differing return
        code / log content. Captures any temp dirs created during the
        run so callers can assert on cleanup semantics if needed.
    Args:
        monkeypatch: Active pytest monkeypatch fixture.
        returncode: Exit code to report from the fake `subprocess.run`.
        log_text: When non-None, written as `resume.log` in the temp
            dir so the validator's "read the log" path engages.
        stderr_text: Fake stderr the validator falls back to when no
            log file exists.
    Output:
        Mutable mapping with key `dirs` listing all paths created.
    """

    monkeypatch.setattr(
        "src.agents.resume_tailor.validator.shutil.which",
        lambda _: "/fake/path/to/tectonic",
    )
    captured: dict[str, list[Path]] = {"dirs": []}

    class _FakeCompletedProcess:
        """Minimal duck-type stand-in for `subprocess.CompletedProcess`."""

        def __init__(self, returncode_: int, stderr_: str) -> None:
            self.returncode = returncode_
            self.stderr = stderr_
            self.stdout = ""

    def fake_run(args: list[str], **_kwargs: Any) -> _FakeCompletedProcess:
        """Pretend to invoke tectonic, optionally writing a log file."""

        # The validator passes `--outdir <temp_dir>` and `<tex_path>`
        # at the end of the arg list. Pull the outdir out so we can
        # drop a fake log there.
        outdir = Path(args[args.index("--outdir") + 1])
        captured["dirs"].append(outdir)
        if log_text is not None:
            (outdir / "resume.log").write_text(log_text, encoding="utf-8")
        return _FakeCompletedProcess(returncode, stderr_text)

    monkeypatch.setattr(
        "src.agents.resume_tailor.validator.subprocess.run", fake_run
    )
    return captured


def test_compile_failure_with_log_file_surfaces_log_lines_in_violation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Risk #7 — when tectonic fails AND a log exists, the log content shows up."""

    fake_log = (
        "This is pdfTeX, Version 3.14159265\n"
        "! Undefined control sequence.\n"
        "l.42 \\missingmacro\n"
        "                  {arg}\n"
    )
    _simulate_tectonic(monkeypatch=monkeypatch, returncode=1, log_text=fake_log)

    tex = (
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "\\section{Experience}\n"
        "\\end{document}\n"
    )

    report = validate_resume_tex(tex, run_compile_check=True)

    assert report.ok is False
    assert len(report.errors) == 1
    error = report.errors[0]
    assert error.code == "CONTRACT_COMPILE_FAILED"
    # The log's `l.42` token is the user-meaningful failure line.
    assert error.line == 42
    assert "Undefined control sequence" in error.violation


def test_compile_failure_without_log_file_falls_back_to_stderr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Risk #7 — missing `resume.log` makes the validator surface stderr instead."""

    _simulate_tectonic(
        monkeypatch=monkeypatch,
        returncode=1,
        log_text=None,
        stderr_text="tectonic: fatal panic\nno log produced\n",
    )

    tex = (
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "\\section{Experience}\n"
        "\\end{document}\n"
    )

    report = validate_resume_tex(tex, run_compile_check=True)

    assert report.ok is False
    error = report.errors[0]
    assert error.code == "CONTRACT_COMPILE_FAILED"
    assert "fatal panic" in error.violation


def test_compile_failure_with_no_l_number_in_log_falls_back_to_line_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Risk #7 — log without `l.<N>` token reports line 1, never raises."""

    _simulate_tectonic(
        monkeypatch=monkeypatch,
        returncode=1,
        log_text="generic failure with no line marker",
    )

    tex = (
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "\\section{Experience}\n"
        "\\end{document}\n"
    )

    report = validate_resume_tex(tex, run_compile_check=True)

    assert report.errors[0].line == 1


def test_successful_compile_does_not_block_static_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Risk #7 — exit-code 0 from tectonic lets the validator continue."""

    _simulate_tectonic(monkeypatch=monkeypatch, returncode=0, log_text=None)

    tex = (
        "\\documentclass{article}\n"
        "\\newcommand{\\resumeItem}[1]{\\item #1}\n"
        "\\newcommand{\\resumeSubheading}[4]"
        "{\\item \\textbf{#1} \\hfill \\textbf{#2}\\\\#3\\hfill#4}\n"
        "\\begin{document}\n"
        "\\section{Experience}\n"
        "\\begin{itemize}\n"
        "  \\resumeSubheading{Engineer}{2024}{Acme}{Remote}\n"
        "    \\begin{itemize}\\resumeItem{Built X.}\\end{itemize}\n"
        "\\end{itemize}\n"
        "\\end{document}\n"
    )

    report = validate_resume_tex(tex, run_compile_check=True)

    assert report.ok is True


def test_compile_error_has_actionable_suggested_fix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every error must carry a non-empty `suggested_fix` — including compile failures."""

    _simulate_tectonic(
        monkeypatch=monkeypatch,
        returncode=1,
        log_text="l.5 something broke",
    )

    tex = "\\documentclass{article}\\begin{document}\\section{Experience}\\end{document}"

    report = validate_resume_tex(tex, run_compile_check=True)

    assert report.errors[0].suggested_fix.strip() != ""


def test_compile_log_is_trimmed_to_max_lines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Risk #7 — huge logs are trimmed so frontends don't choke."""

    # 500 log lines — well over MAX_COMPILE_LOG_LINES (200).
    fake_log = "\n".join(f"log line {n}" for n in range(500))
    _simulate_tectonic(monkeypatch=monkeypatch, returncode=1, log_text=fake_log)

    tex = "\\documentclass{article}\\begin{document}\\section{Experience}\\end{document}"

    report = validate_resume_tex(tex, run_compile_check=True)

    violation_log_portion = report.errors[0].violation
    # The 300th line should NOT be present (cap is 200).
    assert "log line 300" not in violation_log_portion
    # But early lines should appear so the user sees something useful.
    assert "log line 0" in violation_log_portion


def test_compile_check_invocation_uses_tectonic_command_pinned_in_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Risk #7 — the validator must invoke the pinned `TECTONIC_COMMAND` head."""

    monkeypatch.setattr(
        "src.agents.resume_tailor.validator.shutil.which",
        lambda _: "/fake/path/to/tectonic",
    )
    captured_args: list[list[str]] = []

    class _Fake:
        returncode = 0
        stderr = ""
        stdout = ""

    def fake_run(args: list[str], **_kwargs: Any) -> _Fake:
        captured_args.append(args)
        return _Fake()

    monkeypatch.setattr(
        "src.agents.resume_tailor.validator.subprocess.run", fake_run
    )

    tex = "\\documentclass{article}\\begin{document}\\section{Experience}\\end{document}"

    validate_resume_tex(tex, run_compile_check=True)

    assert len(captured_args) == 1
    invocation = captured_args[0]
    # The leading prefix is the pinned `TECTONIC_COMMAND` tuple, in order.
    assert invocation[: len(validator_module.TECTONIC_COMMAND)] == list(
        validator_module.TECTONIC_COMMAND
    )


def test_compile_check_uses_subprocess_timeout_to_bound_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Risk #7 — `subprocess.run` is invoked with a timeout to avoid hangs."""

    monkeypatch.setattr(
        "src.agents.resume_tailor.validator.shutil.which",
        lambda _: "/fake/path/to/tectonic",
    )
    seen_kwargs: dict[str, object] = {}

    class _Fake:
        returncode = 0
        stderr = ""
        stdout = ""

    def fake_run(_args: list[str], **kwargs: Any) -> _Fake:
        seen_kwargs.update(kwargs)
        return _Fake()

    monkeypatch.setattr(
        "src.agents.resume_tailor.validator.subprocess.run", fake_run
    )

    tex = "\\documentclass{article}\\begin{document}\\section{Experience}\\end{document}"

    validate_resume_tex(tex, run_compile_check=True)

    assert "timeout" in seen_kwargs
    assert isinstance(seen_kwargs["timeout"], int)
    assert seen_kwargs["timeout"] > 0


def test_compile_check_propagates_subprocess_timeout_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Risk #7 — a `TimeoutExpired` should NOT be swallowed silently.

    The current implementation lets the exception propagate (the caller
    decides how to surface it). This test pins that behavior so a
    future "swallow + treat as failure" change has to be deliberate.
    """

    monkeypatch.setattr(
        "src.agents.resume_tailor.validator.shutil.which",
        lambda _: "/fake/path/to/tectonic",
    )

    def fake_run(_args: list[str], **_kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired(cmd="tectonic", timeout=1)

    monkeypatch.setattr(
        "src.agents.resume_tailor.validator.subprocess.run", fake_run
    )

    tex = "\\documentclass{article}\\begin{document}\\section{Experience}\\end{document}"

    with pytest.raises(subprocess.TimeoutExpired):
        validate_resume_tex(tex, run_compile_check=True)


# ---------------------------------------------------------------------------
# `_first_log_error_line` — log parser unit tests
# ---------------------------------------------------------------------------


def test_first_log_error_line_extracts_first_l_marker() -> None:
    """The first `l.<N>` token in a log is the user-meaningful line."""

    log = "noise\n! Undefined.\nl.42 \\macro\nl.99 second\n"

    line = _first_log_error_line(log)

    assert line == 42


def test_first_log_error_line_returns_one_when_no_marker_present() -> None:
    """No `l.<N>` token → fall back to line 1, never raise."""

    log = "tectonic crashed in some opaque way"

    line = _first_log_error_line(log)

    assert line == 1


def test_first_log_error_line_handles_empty_string() -> None:
    """Empty log defaults to line 1."""

    assert _first_log_error_line("") == 1


# ---------------------------------------------------------------------------
# `_line_number_of` — 1-indexed line math
# ---------------------------------------------------------------------------


def test_line_number_of_returns_one_for_position_zero() -> None:
    """Position 0 lives on line 1."""

    assert _line_number_of("hello", 0) == 1


def test_line_number_of_returns_one_for_negative_position() -> None:
    """Negative offsets clamp to line 1, never raise."""

    assert _line_number_of("hello", -5) == 1


def test_line_number_of_clamps_position_past_end_of_text() -> None:
    """Offsets past `len(tex_text)` clamp to the final line."""

    text = "line1\nline2\nline3"
    final_line = text.count("\n") + 1

    assert _line_number_of(text, 9_999) == final_line


def test_line_number_of_increments_at_each_newline() -> None:
    """Each `\\n` bumps the reported line number by exactly one."""

    text = "a\nb\nc\nd"

    # Position of `d` should be line 4.
    line_of_d = _line_number_of(text, text.index("d"))

    assert line_of_d == 4


def test_line_number_of_position_on_newline_belongs_to_following_line() -> None:
    """The newline byte itself is the boundary — anything past it bumps lines."""

    text = "alpha\nbeta"
    newline_index = text.index("\n")

    # The newline is on line 1 (count of `\n` before that position is 0).
    assert _line_number_of(text, newline_index) == 1
    # The first byte AFTER the newline is on line 2.
    assert _line_number_of(text, newline_index + 1) == 2
