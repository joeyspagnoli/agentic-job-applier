"""One-shot migration: rename `config/resume_base.tex` → `config/resume.tex`.

Purpose:
    Move existing dogfood / power users from the YAML-era resume layout
    to the Phase 3+ `.tex`-canonical layout described in
    `docs/resume-tex-contract.md`. The plan §9 spec is:

        1. If `config/resume.tex` already exists AND validates →
           ALREADY-MIGRATED, exit 0.
        2. If `config/resume_base.tex` does not exist →
           NO-SOURCE-TEX-FOUND, exit 1.
        3. Validate `config/resume_base.tex` against the contract:
              3a. ok → rename to `config/resume.tex`, delete
                  `config/resume_content.yaml` if present, print
                  ALREADY-CONFORMING-MIGRATED, exit 0.
              3b. fail → print errors with line numbers + suggested
                  fixes, print MANUAL-FIX-REQUIRED, exit 2 (we do
                  NOT auto-rewrite — per plan §11 the user has to fix
                  the file themselves to avoid silent data damage).

Run from the repo root:

    uv run python scripts/migrate_yaml_to_tex.py

The script is idempotent — step 1 short-circuits on re-runs.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running the script without installing the project package
# first — prepend the repo root to sys.path so `src.*` resolves.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agents.resume_tailor.validator import validate_resume_tex

EXIT_OK = 0
EXIT_NO_SOURCE = 1
EXIT_MANUAL_FIX_REQUIRED = 2


def run_migration(*, repo_root: Path | None = None) -> int:
    """Migrate the user from `resume_content.yaml` + `resume_base.tex` → `resume.tex`.

    Purpose:
        Single entry point both the CLI and tests call. Returns the
        process exit code so the caller can branch on outcome without
        capturing stdout.
    Args:
        repo_root: Optional override of the repo root (tests pass a
            tmp dir). Defaults to this file's parent directory.
    Output:
        Process exit code per the docstring header.
    """

    repo_root = repo_root or REPO_ROOT
    resume_tex_new = repo_root / "config" / "resume.tex"
    resume_tex_legacy = repo_root / "config" / "resume_base.tex"
    resume_yaml = repo_root / "config" / "resume_content.yaml"

    # Step 1: target already exists + validates → no work to do.
    if resume_tex_new.exists():
        existing_text = resume_tex_new.read_text(encoding="utf-8")
        existing_report = validate_resume_tex(
            existing_text, run_compile_check=False
        )
        if existing_report.ok:
            print("ALREADY-MIGRATED: config/resume.tex exists and validates.")
            return EXIT_OK
        print(
            "FOUND-INVALID-RESUME-TEX: config/resume.tex exists but does NOT "
            "satisfy the contract. Fix the listed errors and re-run:"
        )
        for error in existing_report.errors:
            print(f"  line {error.line}: [{error.code}] {error.violation}")
            print(f"    fix: {error.suggested_fix}")
        return EXIT_MANUAL_FIX_REQUIRED

    # Step 2: no source to migrate from.
    if not resume_tex_legacy.exists():
        print(
            "NO-SOURCE-TEX-FOUND: config/resume_base.tex does not exist. "
            "Place a contract-conforming .tex file at config/resume.tex "
            "manually, or see docs/resume-tex-contract.md for the spec."
        )
        return EXIT_NO_SOURCE

    # Step 3: validate the legacy .tex.
    legacy_text = resume_tex_legacy.read_text(encoding="utf-8")
    legacy_report = validate_resume_tex(legacy_text, run_compile_check=False)
    if not legacy_report.ok:
        print(
            "MANUAL-FIX-REQUIRED: config/resume_base.tex does NOT satisfy the "
            ".tex contract. Fix the listed errors and re-run:"
        )
        for error in legacy_report.errors:
            print(f"  line {error.line}: [{error.code}] {error.violation}")
            print(f"    fix: {error.suggested_fix}")
        return EXIT_MANUAL_FIX_REQUIRED

    # Step 3a: rename legacy → new, drop the YAML if it still exists.
    resume_tex_legacy.rename(resume_tex_new)
    yaml_dropped = False
    if resume_yaml.exists():
        resume_yaml.unlink()
        yaml_dropped = True

    print("ALREADY-CONFORMING-MIGRATED: config/resume_base.tex → config/resume.tex.")
    if yaml_dropped:
        print("Deleted config/resume_content.yaml (now obsolete).")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(run_migration())
