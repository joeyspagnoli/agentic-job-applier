"""Behavior tests for tectonic-flavored `compile_resume_tex`.

Purpose:
    Cover the env-var dispatch (`RESUME_COMPILER`), timeout resolution
    (`TECTONIC_TIMEOUT_SECONDS`), error-line extraction, and the
    happy-path compile against the synthetic minimal fixture.

The end-to-end compile tests are skipped when `tectonic` isn't on
PATH so the suite stays runnable on a workstation without the binary.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from src.agents.resume_tailor.compiler import (
    DEFAULT_TECTONIC_TIMEOUT_SECONDS,
    ResumeCompileError,
    _extract_first_error_line,
    _resolve_compiler,
    _resolve_tectonic_timeout,
    compile_resume_tex,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "resumes"


def test_resolve_compiler_defaults_to_tectonic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RESUME_COMPILER", raising=False)

    assert _resolve_compiler() == "tectonic"


def test_resolve_compiler_honors_latexmk_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESUME_COMPILER", "latexmk")

    assert _resolve_compiler() == "latexmk"


def test_resolve_compiler_ignores_unknown_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESUME_COMPILER", "xelatex")

    assert _resolve_compiler() == "tectonic"


def test_resolve_compiler_is_case_insensitive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESUME_COMPILER", "LATEXMK")

    assert _resolve_compiler() == "latexmk"


def test_resolve_tectonic_timeout_defaults_to_240(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TECTONIC_TIMEOUT_SECONDS", raising=False)

    assert _resolve_tectonic_timeout() == DEFAULT_TECTONIC_TIMEOUT_SECONDS


def test_resolve_tectonic_timeout_reads_positive_env_int(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TECTONIC_TIMEOUT_SECONDS", "600")

    assert _resolve_tectonic_timeout() == 600


def test_resolve_tectonic_timeout_falls_back_on_invalid_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TECTONIC_TIMEOUT_SECONDS", "not-a-number")

    assert _resolve_tectonic_timeout() == DEFAULT_TECTONIC_TIMEOUT_SECONDS


def test_resolve_tectonic_timeout_falls_back_on_non_positive_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TECTONIC_TIMEOUT_SECONDS", "0")

    assert _resolve_tectonic_timeout() == DEFAULT_TECTONIC_TIMEOUT_SECONDS


def test_extract_first_error_line_returns_bang_preamble() -> None:
    log = "Some preamble noise.\n! Undefined control sequence.\nl.42 ...\nmore"

    result = _extract_first_error_line(log)

    assert "Undefined control sequence" in result
    assert "l.42" in result


def test_extract_first_error_line_falls_back_to_first_nonempty_line() -> None:
    log = "\n\nsomething happened\n"

    result = _extract_first_error_line(log)

    assert result == "something happened"


def test_extract_first_error_line_handles_empty_log() -> None:
    assert _extract_first_error_line("") == "(empty log)"


def test_extract_first_error_line_truncates_long_summaries() -> None:
    long_log = "\n! " + ("x" * 800)

    result = _extract_first_error_line(long_log)

    assert len(result) <= 400


def test_compile_resume_tex_raises_when_source_missing(tmp_path: Path) -> None:
    nonexistent = tmp_path / "does-not-exist.tex"

    with pytest.raises(ResumeCompileError, match="not found"):
        compile_resume_tex(tex_path=nonexistent)


def test_compile_resume_tex_raises_when_tectonic_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RESUME_COMPILER", raising=False)
    # Force `_compile_with_tectonic` to take the "tectonic missing" branch.
    monkeypatch.setattr(
        "src.agents.resume_tailor.compiler.shutil.which",
        lambda cmd: None,
    )
    fake_tex = tmp_path / "resume.tex"
    fake_tex.write_text("\\documentclass{article}\\begin{document}\\end{document}")

    with pytest.raises(ResumeCompileError, match="tectonic is not available"):
        compile_resume_tex(tex_path=fake_tex)


@pytest.mark.skipif(
    shutil.which("tectonic") is None,
    reason="tectonic not installed; end-to-end compile check skipped",
)
def test_synthetic_minimal_compiles_under_tectonic(tmp_path: Path) -> None:
    # Copy the fixture into tmp_path so tectonic's outdir doesn't
    # pollute the repo's fixtures dir.
    source = FIXTURES_DIR / "synthetic_minimal.tex"
    target = tmp_path / "synthetic_minimal.tex"
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    pdf_path = compile_resume_tex(tex_path=target)

    assert pdf_path.exists()
    assert pdf_path.suffix == ".pdf"


@pytest.mark.skipif(
    shutil.which("tectonic") is None,
    reason="tectonic not installed; end-to-end compile check skipped",
)
def test_compile_fail_fixture_raises_with_actionable_error(tmp_path: Path) -> None:
    source = FIXTURES_DIR / "synthetic_failures" / "compile_fail.tex"
    target = tmp_path / "compile_fail.tex"
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    with pytest.raises(ResumeCompileError, match="non-zero"):
        compile_resume_tex(tex_path=target)


def test_compile_resume_tex_routes_to_latexmk_when_env_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESUME_COMPILER", "latexmk")
    # Force the latexmk branch to fail fast with the "missing" error.
    fake_tex = tmp_path / "resume.tex"
    fake_tex.write_text("\\documentclass{article}\\begin{document}\\end{document}")

    if shutil.which("latexmk") is None:
        with pytest.raises(ResumeCompileError, match="latexmk is not available"):
            compile_resume_tex(tex_path=fake_tex)
    else:
        # When latexmk is installed, the call should at least make it
        # past the "missing" branch — exit success or failure is fine
        # for this dispatch test.
        try:
            compile_resume_tex(tex_path=fake_tex)
        except ResumeCompileError:
            pass


def test_compile_failure_message_includes_log_first_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Simulate tectonic exiting non-zero with a log file present.
    import subprocess as subprocess_module

    fake_tex = tmp_path / "resume.tex"
    fake_tex.write_text("\\documentclass{article}\\begin{document}\\end{document}")
    log_path = tmp_path / "resume.log"
    log_path.write_text("\n! Missing $ inserted.\nl.5 ...\n")

    monkeypatch.delenv("RESUME_COMPILER", raising=False)
    monkeypatch.setattr(
        "src.agents.resume_tailor.compiler.shutil.which",
        lambda cmd: "/usr/local/bin/tectonic",
    )

    class _FakeCompletedProcess:
        returncode = 1
        stdout = ""
        stderr = ""

    def _fake_run(*args: object, **kwargs: object) -> _FakeCompletedProcess:
        return _FakeCompletedProcess()

    monkeypatch.setattr(
        "src.agents.resume_tailor.compiler.subprocess.run", _fake_run
    )

    with pytest.raises(ResumeCompileError, match="Missing"):
        compile_resume_tex(tex_path=fake_tex)
