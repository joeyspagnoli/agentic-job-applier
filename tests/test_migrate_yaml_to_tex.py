"""Tests for `scripts/migrate_yaml_to_tex.py` (Phase 3, Risk #4).

Purpose:
    The Phase 1-4 handoff calls out the YAML→TeX migration script as
    "tested manually once" and asks for an automated suite covering
    the three outcome codes plus idempotence on a second run.

    The script's `run_migration(*, repo_root=...)` entry point accepts
    a `repo_root` override so tests can drive it against a `tmp_path`
    sandbox and inspect file moves / deletions in isolation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.migrate_yaml_to_tex import (
    EXIT_MANUAL_FIX_REQUIRED,
    EXIT_NO_SOURCE,
    EXIT_OK,
    run_migration,
)

# A minimal but contract-conforming `.tex` document. Mirrors the
# fixture used by the API endpoint tests so any locator change that
# breaks this also breaks the upload-path coverage at the same time.
_CONFORMING_TEX = (
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

# A `.tex` document that fails the contract — no tailorable section.
_NON_CONFORMING_TEX = (
    "\\documentclass{article}\\begin{document}no sections\\end{document}"
)


def _make_repo_sandbox(tmp_path: Path) -> Path:
    """Create the `config/` directory scaffolding inside a tmp repo root.

    Purpose:
        The migration script expects `<repo_root>/config/` to exist as
        the home of `resume.tex`, `resume_base.tex`, and
        `resume_content.yaml`. We materialize that here so each test
        can drop files inline.
    Args:
        tmp_path: pytest-provided per-test temp dir used as repo root.
    Output:
        `<tmp_path>/config` directory path.
    """

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


# ---------------------------------------------------------------------------
# Step 1 — ALREADY-MIGRATED short-circuit
# ---------------------------------------------------------------------------


def test_already_migrated_short_circuit_returns_exit_ok(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An existing + valid `resume.tex` is a no-op exit-0 run."""

    config_dir = _make_repo_sandbox(tmp_path)
    (config_dir / "resume.tex").write_text(_CONFORMING_TEX, encoding="utf-8")

    exit_code = run_migration(repo_root=tmp_path)

    assert exit_code == EXIT_OK
    captured = capsys.readouterr().out
    assert "ALREADY-MIGRATED" in captured


def test_already_migrated_does_not_touch_legacy_files(tmp_path: Path) -> None:
    """The short-circuit must NOT delete `resume_base.tex` or `resume_content.yaml`."""

    config_dir = _make_repo_sandbox(tmp_path)
    (config_dir / "resume.tex").write_text(_CONFORMING_TEX, encoding="utf-8")
    legacy_tex = config_dir / "resume_base.tex"
    legacy_yaml = config_dir / "resume_content.yaml"
    legacy_tex.write_text("legacy", encoding="utf-8")
    legacy_yaml.write_text("legacy: yaml", encoding="utf-8")

    run_migration(repo_root=tmp_path)

    assert legacy_tex.exists()
    assert legacy_yaml.exists()


# ---------------------------------------------------------------------------
# Step 2 — NO-SOURCE-TEX-FOUND
# ---------------------------------------------------------------------------


def test_no_source_tex_found_returns_exit_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No `resume.tex` AND no `resume_base.tex` → NO-SOURCE-TEX-FOUND."""

    _make_repo_sandbox(tmp_path)

    exit_code = run_migration(repo_root=tmp_path)

    assert exit_code == EXIT_NO_SOURCE
    captured = capsys.readouterr().out
    assert "NO-SOURCE-TEX-FOUND" in captured


# ---------------------------------------------------------------------------
# Step 3a — ALREADY-CONFORMING-MIGRATED (rename + drop YAML)
# ---------------------------------------------------------------------------


def test_legacy_tex_is_renamed_to_resume_tex_when_valid(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A valid `resume_base.tex` is renamed to `resume.tex` and yaml is dropped."""

    config_dir = _make_repo_sandbox(tmp_path)
    (config_dir / "resume_base.tex").write_text(_CONFORMING_TEX, encoding="utf-8")
    (config_dir / "resume_content.yaml").write_text(
        "legacy: yaml content", encoding="utf-8"
    )

    exit_code = run_migration(repo_root=tmp_path)

    assert exit_code == EXIT_OK
    assert (config_dir / "resume.tex").exists()
    assert not (config_dir / "resume_base.tex").exists()
    assert not (config_dir / "resume_content.yaml").exists()
    captured = capsys.readouterr().out
    assert "ALREADY-CONFORMING-MIGRATED" in captured


def test_legacy_tex_rename_preserves_file_content(tmp_path: Path) -> None:
    """After the rename, `resume.tex` content matches the original `resume_base.tex`."""

    config_dir = _make_repo_sandbox(tmp_path)
    (config_dir / "resume_base.tex").write_text(_CONFORMING_TEX, encoding="utf-8")

    run_migration(repo_root=tmp_path)

    assert (config_dir / "resume.tex").read_text(encoding="utf-8") == _CONFORMING_TEX


def test_missing_legacy_yaml_does_not_block_successful_migration(
    tmp_path: Path,
) -> None:
    """Migration succeeds even when `resume_content.yaml` was never present."""

    config_dir = _make_repo_sandbox(tmp_path)
    (config_dir / "resume_base.tex").write_text(_CONFORMING_TEX, encoding="utf-8")

    exit_code = run_migration(repo_root=tmp_path)

    assert exit_code == EXIT_OK
    assert (config_dir / "resume.tex").exists()


# ---------------------------------------------------------------------------
# Step 3b — MANUAL-FIX-REQUIRED (legacy .tex fails contract)
# ---------------------------------------------------------------------------


def test_invalid_legacy_tex_returns_manual_fix_required(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An invalid `resume_base.tex` is reported and exits 2 — never auto-rewritten."""

    config_dir = _make_repo_sandbox(tmp_path)
    legacy_path = config_dir / "resume_base.tex"
    legacy_path.write_text(_NON_CONFORMING_TEX, encoding="utf-8")

    exit_code = run_migration(repo_root=tmp_path)

    assert exit_code == EXIT_MANUAL_FIX_REQUIRED
    # The legacy file must still exist — the script never deletes data
    # it couldn't validate.
    assert legacy_path.exists()
    assert not (config_dir / "resume.tex").exists()
    captured = capsys.readouterr().out
    assert "MANUAL-FIX-REQUIRED" in captured
    # The script surfaces the failing contract code in its output.
    assert "CONTRACT_NO_TAILORABLE_SECTION" in captured


def test_invalid_existing_resume_tex_returns_manual_fix_required(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A drifted-invalid `resume.tex` is surfaced with FOUND-INVALID-RESUME-TEX."""

    config_dir = _make_repo_sandbox(tmp_path)
    (config_dir / "resume.tex").write_text(_NON_CONFORMING_TEX, encoding="utf-8")

    exit_code = run_migration(repo_root=tmp_path)

    assert exit_code == EXIT_MANUAL_FIX_REQUIRED
    captured = capsys.readouterr().out
    assert "FOUND-INVALID-RESUME-TEX" in captured


# ---------------------------------------------------------------------------
# Risk #4 — idempotence
# ---------------------------------------------------------------------------


def test_running_migration_twice_is_a_clean_no_op_on_second_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Risk #4 — second run reports ALREADY-MIGRATED without touching disk."""

    config_dir = _make_repo_sandbox(tmp_path)
    (config_dir / "resume_base.tex").write_text(_CONFORMING_TEX, encoding="utf-8")
    (config_dir / "resume_content.yaml").write_text("legacy", encoding="utf-8")

    first_exit = run_migration(repo_root=tmp_path)
    first_output = capsys.readouterr().out
    resume_tex_after_first = (config_dir / "resume.tex").read_text(encoding="utf-8")

    second_exit = run_migration(repo_root=tmp_path)
    second_output = capsys.readouterr().out
    resume_tex_after_second = (config_dir / "resume.tex").read_text(encoding="utf-8")

    assert first_exit == EXIT_OK
    assert "ALREADY-CONFORMING-MIGRATED" in first_output

    assert second_exit == EXIT_OK
    assert "ALREADY-MIGRATED" in second_output
    # File content must be byte-identical across the two runs.
    assert resume_tex_after_first == resume_tex_after_second
    # Legacy files stay gone after the second run.
    assert not (config_dir / "resume_base.tex").exists()
    assert not (config_dir / "resume_content.yaml").exists()
