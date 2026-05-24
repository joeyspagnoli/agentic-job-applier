"""Behavior tests for `src.agents.resume_tailor.validator`.

Purpose:
    Pin the validator's externally-visible behavior — every error code
    has a triggering fixture, line numbers point at meaningful places,
    and conforming `.tex` documents produce an `ok=True` report with a
    populated manifest preview.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.agents.resume_tailor.validator import (
    ValidatorReport,
    validate_resume_tex,
)

# Fixture paths are resolved from this file so the suite still works
# when pytest is invoked from any cwd.
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "resumes"
SYNTHETIC_FAILURES_DIR = FIXTURES_DIR / "synthetic_failures"


def _read_fixture(name: str) -> str:
    """Load a fixture `.tex` from `tests/fixtures/resumes/`.

    Purpose:
        Centralize the I/O so individual tests stay focused on
        behavior rather than path plumbing.
    Args:
        name: Path of the fixture relative to the resumes directory.
    Output:
        Raw `.tex` text.
    """

    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def test_synthetic_minimal_passes_static_checks() -> None:
    report = validate_resume_tex(
        _read_fixture("synthetic_minimal.tex"), run_compile_check=False
    )

    assert report.ok is True
    assert report.errors == []


def test_dogfood_user_resume_passes_static_checks() -> None:
    # The user's own resume must validate unmodified per plan §11 (the
    # Phase 3 acceptance gate; we assert it here too so any regression
    # is caught at the Phase 0 layer).
    report = validate_resume_tex(
        _read_fixture("dogfood_user.tex"), run_compile_check=False
    )

    assert report.ok is True
    assert report.errors == []
    assert report.manifest_preview is not None
    assert report.manifest_preview.bullet_count() > 0


def test_no_tailorable_section_fixture_triggers_expected_code() -> None:
    report = validate_resume_tex(
        _read_fixture("synthetic_failures/no_tailorable_section.tex"),
        run_compile_check=False,
    )

    assert report.ok is False
    assert len(report.errors) == 1
    assert report.errors[0].code == "CONTRACT_NO_TAILORABLE_SECTION"


def test_orphan_bullet_fixture_triggers_expected_code() -> None:
    report = validate_resume_tex(
        _read_fixture("synthetic_failures/orphan_bullet.tex"),
        run_compile_check=False,
    )

    assert report.ok is False
    assert report.errors[0].code == "CONTRACT_ORPHAN_BULLET"


def test_unbalanced_bullet_fixture_triggers_expected_code() -> None:
    report = validate_resume_tex(
        _read_fixture("synthetic_failures/unbalanced_bullet.tex"),
        run_compile_check=False,
    )

    assert report.ok is False
    assert report.errors[0].code == "CONTRACT_UNBALANCED_BULLET"


def test_unknown_entry_header_fixture_triggers_expected_code() -> None:
    report = validate_resume_tex(
        _read_fixture("synthetic_failures/unknown_entry_header.tex"),
        run_compile_check=False,
    )

    assert report.ok is False
    assert report.errors[0].code == "CONTRACT_UNKNOWN_ENTRY_HEADER"


def test_every_error_record_carries_a_nonempty_suggested_fix() -> None:
    # Suggested-fix text is what the frontend renders inline; an empty
    # value would look broken.
    fixture_names = [
        "synthetic_failures/no_tailorable_section.tex",
        "synthetic_failures/orphan_bullet.tex",
        "synthetic_failures/unbalanced_bullet.tex",
        "synthetic_failures/unknown_entry_header.tex",
    ]

    for name in fixture_names:
        report = validate_resume_tex(_read_fixture(name), run_compile_check=False)
        for error in report.errors:
            assert error.suggested_fix.strip() != ""


def test_orphan_bullet_line_number_points_at_offending_bullet() -> None:
    # The orphan fixture's first `\resumeItem` sits on line 12 (see the
    # fixture). Assert the validator reports that line, not line 1.
    report = validate_resume_tex(
        _read_fixture("synthetic_failures/orphan_bullet.tex"),
        run_compile_check=False,
    )

    assert report.errors[0].line == 12


def test_halt_on_first_failure_returns_one_error_per_run() -> None:
    # The validator halts on the first failure rather than enumerating
    # all violations — keeps the UI predictable. We assert that here
    # so accidental future "collect everything" refactors get caught.
    report = validate_resume_tex(
        _read_fixture("synthetic_failures/orphan_bullet.tex"),
        run_compile_check=False,
    )

    assert len(report.errors) == 1


def test_unrecognized_section_is_treated_as_other_kind_not_a_failure() -> None:
    # A resume with only a `Hobbies` section is rejected because no
    # tailorable section exists, but a resume with Experience + Hobbies
    # passes — the Hobbies section is just classified as `other`.
    tex_with_hobbies = (
        "\\documentclass{article}\n"
        "\\newcommand{\\resumeItem}[1]{\\item #1}\n"
        "\\newcommand{\\resumeSubheading}[4]{\\item \\textbf{#1} \\hfill \\textbf{#2}\\\\#3\\hfill#4}\n"
        "\\begin{document}\n"
        "\\section{Experience}\n"
        "\\begin{itemize}\n"
        "  \\resumeSubheading{Engineer}{2024}{Acme}{Remote}\n"
        "    \\begin{itemize}\n"
        "      \\resumeItem{Built X.}\n"
        "    \\end{itemize}\n"
        "\\end{itemize}\n"
        "\\section{Hobbies}\n"
        "I enjoy long walks.\n"
        "\\end{document}\n"
    )

    report = validate_resume_tex(tex_with_hobbies, run_compile_check=False)

    assert report.ok is True


def test_manifest_preview_is_populated_when_validation_passes() -> None:
    report = validate_resume_tex(
        _read_fixture("synthetic_minimal.tex"), run_compile_check=False
    )

    assert report.manifest_preview is not None
    # The minimal fixture has two sections: Experience + Projects.
    assert len(report.manifest_preview.sections) == 2


def test_manifest_preview_is_none_when_validation_fails() -> None:
    report = validate_resume_tex(
        _read_fixture("synthetic_failures/orphan_bullet.tex"),
        run_compile_check=False,
    )

    assert report.manifest_preview is None


@pytest.mark.parametrize(
    "fixture_name",
    [
        "synthetic_minimal.tex",
        "dogfood_user.tex",
        "external/deedy_resume.tex",
        "external/fallback_b_textbf_hfill.tex",
    ],
)
def test_known_passing_fixtures_validate(fixture_name: str) -> None:
    report = validate_resume_tex(
        _read_fixture(fixture_name), run_compile_check=False
    )

    assert report.ok is True, f"{fixture_name} unexpectedly failed: {report.errors}"


def test_validator_report_repr_is_informative() -> None:
    # The repr is used in audit-script logs; assert it carries enough
    # detail to debug a failed run from the log alone.
    report = ValidatorReport(ok=False, errors=[], warnings=[], manifest_preview=None)

    text = repr(report)

    assert "ok=False" in text
    assert "errors=0" in text
