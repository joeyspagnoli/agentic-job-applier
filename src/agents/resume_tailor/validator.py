"""Upload-time contract validator for resume `.tex` files.

Purpose:
    Enforce the `docs/resume-tex-contract.md` rules before a `.tex`
    enters the tailor pipeline. Emits structured `ValidatorError`
    records with 1-indexed line numbers and suggested-fix snippets so
    the frontend can render an actionable error list.

The check order from §2.4 stops on the first failure so the user sees
one targeted error at a time:
    1. Compile check (optional — skipped when no compiler is on PATH).
    2. ≥1 experience/projects section present.
    3. Every bullet follows an entry header.
    4. Bullet bodies have balanced braces.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Literal, TypedDict

from ._braces import find_matching_brace
from .contract import (
    CVLINE_RE,
    ENTRY_HEADER_PATTERNS,
    ITEM_RE,
    RESUME_ITEM_RE,
    SECTION_ALLOWLIST,
    SECTION_HEADING_RE,
    ValidatorError,
)
from .locator import build_bullet_manifest
from .manifest import BulletManifest


class _SectionRecord(TypedDict):
    """Typed shape for the per-section bookkeeping struct.

    Purpose:
        Give mypy something concrete to check against — `dict[str, object]`
        forced int() casts at every read site and obscured the actual
        record shape.
    """

    heading: str
    kind: Literal["experience", "projects", "other"]
    body_start: int
    body_end: int
    line: int

# Maximum number of log lines we surface in a compile-failure error
# message — enough to spot the failing macro, not so many that the
# frontend rendering chokes.
MAX_COMPILE_LOG_LINES = 200

# Tectonic invocation pinned by the plan (§8.1). Used at validator
# time and again in Phase 1's compiler swap.
TECTONIC_COMMAND = ("tectonic", "-X", "compile", "--keep-logs", "--outfmt", "pdf")



class ValidatorReport:
    """Result of running the contract validator against a `.tex` file.

    Purpose:
        Carry the boolean verdict, ordered error/warning lists, and an
        optional manifest preview the frontend can use to show a
        success-state summary (section / entry / bullet counts).

    Attributes:
        ok: True when no errors were raised.
        errors: Ordered list of `ValidatorError` blocking conformance.
        warnings: Ordered list of non-blocking `ValidatorError`.
        manifest_preview: Successful manifest extraction, or `None`
            when validation halted before the locator ran.
    """

    def __init__(
        self,
        *,
        ok: bool,
        errors: list[ValidatorError],
        warnings: list[ValidatorError],
        manifest_preview: BulletManifest | None,
    ) -> None:
        self.ok = ok
        self.errors = errors
        self.warnings = warnings
        self.manifest_preview = manifest_preview

    def __repr__(self) -> str:
        return (
            f"ValidatorReport(ok={self.ok}, "
            f"errors={len(self.errors)}, "
            f"warnings={len(self.warnings)})"
        )


def validate_resume_tex(
    tex_text: str,
    *,
    run_compile_check: bool = True,
) -> ValidatorReport:
    """Validate `tex_text` against the resume `.tex` contract.

    Purpose:
        Single entry point the API and audit script call to confirm a
        `.tex` is tailor-ready. Halts on the first contract violation
        so the user sees one targeted error at a time.
    Args:
        tex_text: Full text of the `.tex` to validate.
        run_compile_check: When True, invoke tectonic in a temp dir to
            confirm the document compiles. When False (or when tectonic
            isn't on PATH), skip the compile check and continue with
            the static checks.
    Output:
        `ValidatorReport` with `ok=True` only when no errors fired.
        The `manifest_preview` field is populated when the static
        checks succeed so callers can show a success-state summary.
    """

    errors: list[ValidatorError] = []
    warnings: list[ValidatorError] = []

    # §2.4 rule 1 — compile check.
    if run_compile_check:
        compile_error = _run_compile_check(tex_text)
        if compile_error is not None:
            errors.append(compile_error)
            return ValidatorReport(
                ok=False, errors=errors, warnings=warnings, manifest_preview=None
            )

    # §2.4 rule 2 — at least one tailorable section.
    section_records = _collect_section_records(tex_text)
    if not any(record["kind"] in ("experience", "projects") for record in section_records):
        first_section_line: int = (
            section_records[0]["line"] if section_records else 1
        )
        errors.append(
            ValidatorError(
                line=first_section_line,
                code="CONTRACT_NO_TAILORABLE_SECTION",
                violation=(
                    "Resume has no \\section heading recognized as "
                    "Experience or Projects."
                ),
                suggested_fix=(
                    "Add or rename a section to one of the allowed "
                    "headings (e.g. \\section{Experience} or "
                    "\\section{Projects}). See docs/resume-tex-contract.md."
                ),
            )
        )
        return ValidatorReport(
            ok=False, errors=errors, warnings=warnings, manifest_preview=None
        )

    # §2.4 rules 3 + 4 — orphan bullets + balanced braces.
    for section_record in section_records:
        if section_record["kind"] not in ("experience", "projects"):
            continue

        structural_errors = _check_section_structure(
            tex_text=tex_text,
            section_record=section_record,
        )
        if structural_errors:
            errors.extend(structural_errors)
            return ValidatorReport(
                ok=False,
                errors=errors,
                warnings=warnings,
                manifest_preview=None,
            )

    # All checks passed — return manifest preview for the success state.
    manifest_preview = build_bullet_manifest(tex_text)
    return ValidatorReport(
        ok=True,
        errors=errors,
        warnings=warnings,
        manifest_preview=manifest_preview,
    )


def _run_compile_check(tex_text: str) -> ValidatorError | None:
    """Compile `tex_text` with tectonic in a temp dir, returning errors.

    Purpose:
        §2.4 rule 1 — confirm the document compiles before applying
        any structural checks. When tectonic is not installed we skip
        silently; the audit script and live upload paths will reinstate
        the check once the Phase 1 Dockerfile bundles tectonic.
    Args:
        tex_text: Full text of the `.tex` to compile.
    Output:
        `ValidatorError` when tectonic ran and failed; `None` when the
        compile succeeded OR when tectonic was not available.
    """

    if shutil.which("tectonic") is None:
        # Phase 0 environments without tectonic skip this check. Phase
        # 1's deploy/Dockerfile installs tectonic and the audit script
        # treats this as an environmental skip, not a contract pass.
        return None

    with tempfile.TemporaryDirectory(prefix="resume-validate-") as temp_dir:
        temp_dir_path = Path(temp_dir)
        tex_path = temp_dir_path / "resume.tex"
        tex_path.write_text(tex_text, encoding="utf-8")

        completed = subprocess.run(
            [*TECTONIC_COMMAND, "--outdir", str(temp_dir_path), str(tex_path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=240,
        )

        if completed.returncode == 0:
            return None

        log_path = temp_dir_path / "resume.log"
        if log_path.exists():
            log_text = log_path.read_text(encoding="utf-8", errors="ignore")
        else:
            log_text = completed.stderr or completed.stdout or ""

        trimmed_log = "\n".join(log_text.splitlines()[:MAX_COMPILE_LOG_LINES])
        first_error_line = _first_log_error_line(log_text)
        return ValidatorError(
            line=first_error_line,
            code="CONTRACT_COMPILE_FAILED",
            violation=(
                "Tectonic could not compile this .tex file. First lines "
                f"of the log:\n{trimmed_log}"
            ),
            suggested_fix=(
                "Fix the LaTeX error shown in the log above and re-upload. "
                "Run `tectonic -X compile <file>.tex` locally to iterate."
            ),
        )


_LATEX_LOG_LINE_RE = re.compile(r"l\.(\d+)")


def _first_log_error_line(log_text: str) -> int:
    """Extract the first `l.<N>` line number from a LaTeX error log.

    Purpose:
        Surface the user-meaningful line number for compile failures so
        the validator points at the offending line, not just line 1.
    Args:
        log_text: Raw LaTeX log content.
    Output:
        1-indexed line number, or `1` when no `l.<N>` token is present.
    """

    match = _LATEX_LOG_LINE_RE.search(log_text)
    if match is None:
        return 1
    return int(match.group(1))


def _collect_section_records(tex_text: str) -> list[_SectionRecord]:
    """Walk every `\\section{...}` and record its kind + body span.

    Purpose:
        Single pass over `\\section` headings so the validator's two
        structural checks share one piece of work.
    Args:
        tex_text: Full document text.
    Output:
        Ordered list of `_SectionRecord` dicts with `heading`, `kind`,
        `body_start`, `body_end`, and `line` keys. `kind` is
        `experience`, `projects`, or `other`.
    """

    matches = list(SECTION_HEADING_RE.finditer(tex_text))
    total_length = len(tex_text)
    records: list[_SectionRecord] = []
    for index, match in enumerate(matches):
        heading_raw = match.group("heading").strip()
        kind: Literal["experience", "projects", "other"] = SECTION_ALLOWLIST.get(
            heading_raw.lower(), "other"
        )
        body_start = match.end()
        body_end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else total_length
        )
        records.append(
            _SectionRecord(
                heading=heading_raw,
                kind=kind,
                body_start=body_start,
                body_end=body_end,
                line=_line_number_of(tex_text, match.start()),
            )
        )
    return records


def _check_section_structure(
    *,
    tex_text: str,
    section_record: _SectionRecord,
) -> list[ValidatorError]:
    """Run rules 3 + 4 against one experience/projects section.

    Purpose:
        Detect bullets-without-entry-headers and unbalanced bullet
        bodies inside a single section, in source order so the first
        violation surfaces a meaningful line number.
    Args:
        tex_text: Full document text.
        section_record: One record from `_collect_section_records`.
    Output:
        List of `ValidatorError` (empty on pass). Caller is responsible
        for short-circuiting after the first non-empty list.
    """

    body_start = section_record["body_start"]
    body_end = section_record["body_end"]

    entry_header_positions = _scan_entry_header_positions(
        tex_text=tex_text, body_start=body_start, body_end=body_end
    )
    bullet_positions = _scan_bullet_positions(
        tex_text=tex_text,
        body_start=body_start,
        body_end=body_end,
        entry_header_positions=entry_header_positions,
    )

    errors: list[ValidatorError] = []

    if bullet_positions and not entry_header_positions:
        # Rule equivalent: section has bullets but no recognized entry
        # header at all → user is using a macro we don't support.
        first_bullet_position = bullet_positions[0]
        errors.append(
            ValidatorError(
                line=_line_number_of(tex_text, first_bullet_position),
                code="CONTRACT_UNKNOWN_ENTRY_HEADER",
                violation=(
                    "Section contains bullets but no recognized entry "
                    "header (\\resumeSubheading, \\cventry, \\cvitem, "
                    "\\cvevent, \\runsubsection, or a \\textbf{Role at "
                    "Company} fallback line)."
                ),
                suggested_fix=(
                    "Wrap each role in a recognized entry-header macro. "
                    "For Jake's-style templates: \\resumeSubheading"
                    "{Title}{Dates}{Org}{Location}."
                ),
            )
        )
        return errors

    # Rule 3 — every bullet must follow at least one entry header. The
    # first entry header anchors the earliest valid bullet position.
    first_entry_position = entry_header_positions[0] if entry_header_positions else None
    if first_entry_position is not None:
        for bullet_position in bullet_positions:
            if bullet_position < first_entry_position:
                errors.append(
                    ValidatorError(
                        line=_line_number_of(tex_text, bullet_position),
                        code="CONTRACT_ORPHAN_BULLET",
                        violation=(
                            "Bullet appears before any recognized entry "
                            "header in its section."
                        ),
                        suggested_fix=(
                            "Move the bullet under a \\resumeSubheading "
                            "or other recognized entry-header macro, or "
                            "wrap the surrounding block in an entry header."
                        ),
                    )
                )
                return errors

    # Rule 4 — every `\resumeItem{...}` and `\cvline{}{...}` must have
    # balanced braces. Walking with `find_matching_brace` is the same
    # check the locator uses, so a failure here means the locator
    # would have produced a degenerate manifest.
    balanced_brace_error = _check_bullet_brace_balance(
        tex_text=tex_text, body_start=body_start, body_end=body_end
    )
    if balanced_brace_error is not None:
        errors.append(balanced_brace_error)

    return errors


def _scan_entry_header_positions(
    *,
    tex_text: str,
    body_start: int,
    body_end: int,
) -> list[int]:
    """Return the byte offsets of every entry-header match in a body.

    Purpose:
        Provide the orphan-bullet check with a stable "where do entry
        headers live" set so it can compare against bullet positions.
    Args:
        tex_text: Full document text.
        body_start: Section body start offset.
        body_end: Section body end offset.
    Output:
        Sorted, deduplicated list of byte offsets.
    """

    section_body = tex_text[body_start:body_end]
    positions: set[int] = set()
    for pattern_def in ENTRY_HEADER_PATTERNS:
        for match in pattern_def.regex.finditer(section_body):
            positions.add(body_start + match.start())
    return sorted(positions)


def _scan_bullet_positions(
    *,
    tex_text: str,
    body_start: int,
    body_end: int,
    entry_header_positions: list[int],
) -> list[int]:
    """Return byte offsets of bullet macros, excluding entry headers.

    Purpose:
        Pattern #6 (`generic_bold_item`) reuses `\\item` as the entry
        token, so the orphan check must exclude `\\item` positions that
        coincide with an entry-header line — otherwise every
        Jake's-family entry would look like an orphan bullet.
    Args:
        tex_text: Full document text.
        body_start: Section body start offset.
        body_end: Section body end offset.
        entry_header_positions: Already-computed offsets of entry
            headers in this section.
    Output:
        Sorted list of bullet macro offsets.
    """

    entry_header_lines = {
        _line_number_of(tex_text, position) for position in entry_header_positions
    }

    positions: list[int] = []
    for regex in (RESUME_ITEM_RE, CVLINE_RE):
        for match in regex.finditer(tex_text, body_start, body_end):
            positions.append(match.start())

    # `\item` is the ambiguous case — collect it only when the line it
    # lives on isn't already accounted for as an entry-header line.
    for match in ITEM_RE.finditer(tex_text, body_start, body_end):
        position = match.start()
        if _line_number_of(tex_text, position) in entry_header_lines:
            continue
        positions.append(position)

    positions.sort()
    return positions


def _check_bullet_brace_balance(
    *,
    tex_text: str,
    body_start: int,
    body_end: int,
) -> ValidatorError | None:
    """Confirm every `\\resumeItem{...}` and `\\cvline{...}{...}` balances.

    Purpose:
        §2.4 rule 4 — catch users who paste raw `{` / `}` chars inside
        a bullet body without escaping. Returns the first failing
        bullet rather than enumerating all of them, matching the
        validator's halt-on-first-failure semantics.
    Args:
        tex_text: Full document text.
        body_start: Section body start offset.
        body_end: Section body end offset.
    Output:
        `ValidatorError` describing the unbalanced bullet, or `None`
        when every bullet body balances.
    """

    for regex, arg_index in ((RESUME_ITEM_RE, 0), (CVLINE_RE, 1)):
        for match in regex.finditer(tex_text, body_start, body_end):
            cursor = match.end()
            unbalanced = False
            # Skip past `arg_index` complete groups, then validate the
            # target group balances on its own.
            for current_arg in range(arg_index + 1):
                open_brace = tex_text.find("{", cursor)
                if open_brace == -1 or open_brace >= body_end:
                    unbalanced = True
                    break
                close_brace = find_matching_brace(tex_text, open_brace)
                if close_brace is None or close_brace >= body_end:
                    unbalanced = True
                    break
                cursor = close_brace + 1

            if unbalanced:
                return ValidatorError(
                    line=_line_number_of(tex_text, match.start()),
                    code="CONTRACT_UNBALANCED_BULLET",
                    violation=(
                        "Bullet body has unbalanced braces — the opening "
                        "{ has no matching } within the bullet."
                    ),
                    suggested_fix=(
                        "Escape literal braces inside the bullet text as "
                        "`\\{` and `\\}`, or close the missing brace."
                    ),
                )
    return None


def _line_number_of(tex_text: str, position: int) -> int:
    """Convert a byte offset to a 1-indexed line number.

    Purpose:
        ValidatorError reports want line numbers, not byte offsets.
        We count newlines before `position` to derive the line.
    Args:
        tex_text: Full document text.
        position: Byte offset inside `tex_text`.
    Output:
        1-indexed line number containing the byte at `position`.
    """

    if position <= 0:
        return 1
    if position > len(tex_text):
        position = len(tex_text)
    return tex_text.count("\n", 0, position) + 1


__all__ = [
    "ValidatorReport",
    "validate_resume_tex",
]
