"""Audit the curated `.tex` template library against the contract.

Purpose:
    Run `validate_resume_tex` and `build_bullet_manifest` against every
    fixture in `tests/fixtures/resumes/` and print a Markdown table
    summarizing pass/fail status, bullet counts, and per-template notes.
    Used to populate `docs/resume-tex-contract.md`'s template-support
    section and to gate Phase 0 acceptance per plan §11.

Run from the repo root:
    uv run python scripts/audit_resume_templates.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TypedDict

# Allow running the script without installing the project package
# first — prepend the repo root to sys.path so `src.*` resolves.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agents.resume_tailor.locator import build_bullet_manifest
from src.agents.resume_tailor.validator import validate_resume_tex

# Pass-rate threshold below which the plan's §11 Abort criteria says
# we should escalate to the user. The audit script flags this in its
# trailing summary line.
PASS_RATE_ESCALATION_THRESHOLD = 0.60

# Width of the Template column in the output table — set wide enough
# for the longest fixture filename plus a comfortable margin.
TEMPLATE_COLUMN_WIDTH = 38

# Per-fixture notes surfaced in the audit output. Keys are filenames
# (relative to `tests/fixtures/resumes/`). Use this to record "needs
# minor modification" guidance the user should see in the contract doc.
class _AuditRow(TypedDict):
    """Typed shape for one audit-output row.

    Purpose:
        Keep mypy happy across the discovery → audit → print pipeline.
    """

    name: str
    verdict: str
    bullets: int
    entries: int
    note: str


FIXTURE_NOTES: dict[str, str] = {
    "synthetic_minimal.tex": "handwritten — exercises Jake's-family pattern",
    "dogfood_user.tex": "this repo's own resume (Jake's-family + dates fallback)",
    "external/jakes_resume.tex": (
        "Projects section uses \\resumeProjectHeading (2-arg variant); "
        "rewrap as \\resumeSubheading to pass"
    ),
    "external/sb2nov_resume.tex": (
        "Projects section uses \\resumeSubItem (label+body bullets); "
        "rewrap as \\resumeSubheading+\\resumeItem to pass"
    ),
    "external/posquit0_awesome_cv.tex": (
        "uses \\input{resume/*.tex} fan-out + \\cvsection{} (not in contract); "
        "needs section macro rename + included files"
    ),
    "external/deedy_resume.tex": "Deedy \\runsubsection + \\descript + \\location",
    "external/altacv_sample.tex": (
        "uses \\cvsection{} (not in contract); rename to \\section{}"
    ),
    "external/mcdowell_cv.tex": (
        "uses \\begin{cvsection}{...} environment form (not in contract); "
        "rename to \\section{}"
    ),
    "external/moderncv_template.tex": (
        "\\cventry 6th arg contains nested \\begin{itemize} — \"[^{}]\" regex "
        "can't span the body; needs TexSoup cross-check (planned for v2)"
    ),
    "external/yaac_cv.tex": (
        "uses \\input{section_*.tex} fan-out — actual content lives in files "
        "we don't vendor"
    ),
    "external/fallback_b_textbf_hfill.tex": (
        "handwritten — exercises Fallback B (\\textbf{Role}\\hfill Dates)"
    ),
}


def run_audit() -> int:
    """Audit every fixture, print the table, return the process exit code.

    Purpose:
        Single entry point both the CLI and any future CI step can
        call. Returns 0 unless an unexpected exception fired — pass
        rate alone never fails the process, since the plan treats low
        pass rate as a "escalate" not a "block" signal.
    Output:
        Process exit code (0 on clean run).
    """

    fixtures_root = REPO_ROOT / "tests" / "fixtures" / "resumes"
    fixtures = _discover_fixtures(fixtures_root)

    rows: list[_AuditRow] = []
    for fixture_path in fixtures:
        rows.append(_audit_one(fixture_path=fixture_path, root=fixtures_root))

    _print_table(rows)
    _print_summary(rows)
    return 0


def _discover_fixtures(root: Path) -> list[Path]:
    """Return every `.tex` fixture worth auditing, in stable order.

    Purpose:
        Audit output should be reproducible run-to-run; sort the file
        list deterministically. The synthetic_failures dir is skipped
        because those fixtures are designed to fail and would muddy
        the pass-rate signal.
    Args:
        root: `tests/fixtures/resumes/` directory.
    Output:
        Sorted list of fixture paths.
    """

    happy_path_fixtures = sorted(
        path for path in root.glob("*.tex") if path.is_file()
    )
    external_fixtures = sorted(
        path for path in (root / "external").glob("*.tex") if path.is_file()
    )
    return happy_path_fixtures + external_fixtures


def _audit_one(*, fixture_path: Path, root: Path) -> _AuditRow:
    """Validate one fixture and build a summary row.

    Purpose:
        Encapsulate the per-fixture work so `run_audit` reads as a
        clean sequence: discover → audit → print.
    Args:
        fixture_path: Filesystem path of the fixture.
        root: Repository fixtures root — used to derive the relative
            display name in the table.
    Output:
        Dict carrying display name, pass/fail verdict, bullet count,
        and the user-facing note.
    """

    tex_text = fixture_path.read_text(encoding="utf-8")
    report = validate_resume_tex(tex_text, run_compile_check=False)
    display_name = str(fixture_path.relative_to(root))

    if report.ok:
        manifest = build_bullet_manifest(tex_text)
        verdict = "PASS"
        bullet_count = manifest.bullet_count()
        entry_count = manifest.entry_count()
    else:
        verdict = "FAIL"
        bullet_count = 0
        entry_count = 0

    note = FIXTURE_NOTES.get(display_name, "")
    if not report.ok:
        codes = ", ".join(error.code for error in report.errors)
        note_prefix = f"[{codes}] "
        note = (note_prefix + note).strip()

    return _AuditRow(
        name=display_name,
        verdict=verdict,
        bullets=bullet_count,
        entries=entry_count,
        note=note,
    )


def _print_table(rows: list[_AuditRow]) -> None:
    """Print a Markdown-ready table of audit results to stdout.

    Purpose:
        Match the §10.5 schema from the plan so the output can be
        pasted directly into the PR description and the contract doc.
    Args:
        rows: Per-fixture summary rows from `_audit_one`.
    """

    template_width = max(TEMPLATE_COLUMN_WIDTH, max(len(row["name"]) for row in rows) + 2)
    print(
        f"{'Template':<{template_width}} | {'Verdict':<9} | "
        f"{'Entries':>7} | {'Bullets':>7} | Notes"
    )
    print("-" * template_width + "-+-" + "-" * 9 + "-+-" + "-" * 7 + "-+-" + "-" * 7 + "-+-" + "-" * 60)
    for row in rows:
        print(
            f"{row['name']:<{template_width}} | "
            f"{row['verdict']:<9} | "
            f"{row['entries']:>7} | "
            f"{row['bullets']:>7} | "
            f"{row['note']}"
        )


def _print_summary(rows: list[_AuditRow]) -> None:
    """Print the pass-rate summary + escalation banner if applicable.

    Purpose:
        The plan §11 Abort criteria says <60% pass rate should
        escalate to the user. We can't block here (the audit is meant
        to be informational), but we surface the threshold breach
        loudly so the PR reviewer can see it.
    Args:
        rows: Per-fixture summary rows from `_audit_one`.
    """

    total = len(rows)
    passing = sum(1 for row in rows if row["verdict"] == "PASS")
    rate = passing / total if total else 0.0

    print()
    print(f"Total fixtures: {total}  |  Passing: {passing}  |  Pass rate: {rate:.0%}")

    if rate < PASS_RATE_ESCALATION_THRESHOLD:
        print()
        print("=" * 78)
        print(
            "ESCALATION (per plan §11 Abort criteria): pass rate below "
            f"{int(PASS_RATE_ESCALATION_THRESHOLD * 100)}%. "
            "Review the FAIL rows above and decide whether to:"
        )
        print(
            "  (a) loosen the contract to cover more macro families "
            "(adds support but expands the surface to maintain), or"
        )
        print(
            "  (b) document the failing templates as 'needs minor "
            "modification' and ship the strict contract."
        )
        print("=" * 78)


if __name__ == "__main__":
    sys.exit(run_audit())
