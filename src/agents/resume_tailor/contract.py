"""Pure data and regex constants encoding the `.tex` resume contract.

Purpose:
    Hold the section allowlist, entry-header macro patterns, bullet
    patterns, and the structured error model that the validator and
    locator share. Keeping this in one module means the contract has a
    single source of truth — every change to "what `.tex` shapes we
    accept" lands here and propagates through validator + locator
    without drift.

The contract itself lives in `docs/resume-tex-contract.md`; this module
encodes it in code so the validator can enforce it deterministically.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Pattern

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# §2.1 Section heading allowlist
# ---------------------------------------------------------------------------

# Case-insensitive heading text → semantic kind. Headings outside this
# allowlist are recorded as kind="other" and skipped at tailor time;
# they are NOT rejected so users can still have Skills / Education /
# Summary / Awards sections.
SectionKind = Literal["experience", "projects", "other"]

SECTION_ALLOWLIST: dict[str, Literal["experience", "projects"]] = {
    "experience": "experience",
    "work experience": "experience",
    "professional experience": "experience",
    "employment": "experience",
    "employment history": "experience",
    "work history": "experience",
    "career experience": "experience",
    "projects": "projects",
    "side projects": "projects",
    "personal projects": "projects",
    "open source projects": "projects",
    "selected projects": "projects",
}

# Matches `\section{Heading}` or `\section{\textbf{Heading}}`. The
# `heading` group is the inner text we normalize and look up in the
# allowlist. We do not handle starred `\section*{...}` because the
# curated 10 templates do not use it; if a user uses `\section*` we
# treat it as `other` (no match here) which means the tailor skips it.
SECTION_HEADING_RE: Pattern[str] = re.compile(
    r"^\s*\\section\{(?:\\textbf\{)?(?P<heading>[^{}]+?)\}?\}\s*$",
    flags=re.MULTILINE,
)


# ---------------------------------------------------------------------------
# §2.2 Entry-header macro + fallback patterns
# ---------------------------------------------------------------------------

EntryHeaderPatternId = Literal[
    "resumeSubheading",
    "cventry",
    "cvitem",
    "cvevent",
    "deedy_runsubsection",
    "generic_bold_item",
    "fallback_textbf_at",
    "fallback_textbf_hfill_dates",
]


@dataclass(frozen=True)
class EntryHeaderPattern:
    """Definition of one entry-header form the locator recognizes.

    Purpose:
        Pair a compiled regex with the metadata the locator needs to
        slot it into a `BulletEntry` — which capture group is the
        role/title (for `role_context` fallback) and which template
        family the pattern belongs to.
    """

    pattern_id: EntryHeaderPatternId
    template_family: str
    regex: Pattern[str]


# The 6 macro forms + 2 fallback forms, in priority order. Per §2.2 the
# `[^{}]*` in macro args is intentional: brace-nesting inside a macro
# arg means we treat the whole line as the candidate span and rely on
# the validator's brace-balance check to catch malformed entries.
ENTRY_HEADER_PATTERNS: tuple[EntryHeaderPattern, ...] = (
    # 1. Jake's / sb2nov: \resumeSubheading{title}{dates}{org}{location}
    # `\s*` between groups allows multi-line invocations where args
    # are split across lines for readability — common in Jake's family.
    EntryHeaderPattern(
        pattern_id="resumeSubheading",
        template_family="jakes_sb2nov",
        regex=re.compile(
            r"\\resumeSubheading\s*\{(?P<a>[^{}]*)\}\s*\{(?P<b>[^{}]*)\}"
            r"\s*\{(?P<c>[^{}]*)\}\s*\{(?P<d>[^{}]*)\}"
        ),
    ),
    # 2. ModernCV / Awesome-CV: \cventry[opts]{dates}{role}{company}{loc}{...}{...}
    EntryHeaderPattern(
        pattern_id="cventry",
        template_family="moderncv_awesomecv",
        regex=re.compile(
            r"\\cventry\s*(?:\[[^\]]*\])?\s*"
            r"\{(?P<a>[^{}]*)\}\s*\{(?P<b>[^{}]*)\}\s*\{(?P<c>[^{}]*)\}"
            r"\s*\{(?P<d>[^{}]*)\}\s*\{(?P<e>[^{}]*)\}\s*\{(?P<f>[^{}]*)\}"
        ),
    ),
    # 3. ModernCV terse: \cvitem{dates}{role at company}
    EntryHeaderPattern(
        pattern_id="cvitem",
        template_family="moderncv_terse",
        regex=re.compile(
            r"\\cvitem\s*\{(?P<a>[^{}]*)\}\s*\{(?P<b>[^{}]*)\}"
        ),
    ),
    # 4. AltaCV: \cvevent{title}{holder_or_dates}{location}{description}
    EntryHeaderPattern(
        pattern_id="cvevent",
        template_family="altacv",
        regex=re.compile(
            r"\\cvevent\s*\{(?P<a>[^{}]*)\}\s*\{(?P<b>[^{}]*)\}"
            r"\s*\{(?P<c>[^{}]*)\}\s*\{(?P<d>[^{}]*)\}"
        ),
    ),
    # 5. Deedy: \runsubsection{company} \descript{| role} \location{dates}
    # Brace contents allow basic LaTeX inside the third arg's location
    # (Deedy commonly includes pipes / vertical bars there).
    EntryHeaderPattern(
        pattern_id="deedy_runsubsection",
        template_family="deedy",
        regex=re.compile(
            r"\\runsubsection\s*\{(?P<a>[^{}]+)\}\s*"
            r"\\descript\s*\{\|\s*(?P<b>[^{}]*)\}\s*"
            r"\\location\s*\{(?P<c>[^{}]*)\}"
        ),
    ),
    # 6. Generic bold-item: \item {\textbf{Role}} \hfill {\textbf{Dates}}
    # This is the pattern the dogfood resume uses; both `{}` braces and
    # `\hfill`/dates are optional so terser variants still match.
    EntryHeaderPattern(
        pattern_id="generic_bold_item",
        template_family="generic_bold",
        regex=re.compile(
            r"\\item\s*\{?\\textbf\{(?P<title>[^{}]+)\}\}?"
            r"(?:\s*\\hfill\s*\{?\\textbf\{(?P<dates>[^{}]+)\}\}?)?"
        ),
    ),
    # Fallback A: \textbf{Role at Company} on its own line. Optional
    # trailing `\\` (LaTeX hard line-break) is allowed so users who end
    # the header with one still match.
    EntryHeaderPattern(
        pattern_id="fallback_textbf_at",
        template_family="fallback",
        regex=re.compile(
            r"^\s*\\textbf\{(?P<role_at_company>[^{}]+\sat\s[^{}]+)\}"
            r"\s*(?:\\\\)?\s*$",
            flags=re.MULTILINE,
        ),
    ),
    # Fallback B: \textbf{Role}\hfill Dates on its own line. Dates must
    # start with an uppercase letter OR a digit (years are the most
    # common date opener) so this doesn't collide with prose.
    # Trailing `\\` allowed for the same reason as Fallback A.
    EntryHeaderPattern(
        pattern_id="fallback_textbf_hfill_dates",
        template_family="fallback",
        regex=re.compile(
            r"^\s*\\textbf\{(?P<role>[^{}]+)\}\s*\\hfill\s+"
            r"(?P<dates>[A-Z0-9][^\\{}]+?)\s*(?:\\\\)?\s*$",
            flags=re.MULTILINE,
        ),
    ),
)


# ---------------------------------------------------------------------------
# §2.3 Bullet patterns
# ---------------------------------------------------------------------------

BulletPatternId = Literal["resume_item", "cvline", "itemize_item"]


@dataclass(frozen=True)
class BulletPattern:
    """Definition of one bullet form the locator extracts.

    Purpose:
        Pair the bullet recognizer regex with the brace-handling mode
        the locator should use to find the body span.

    `body_extraction` is the contract for how the locator turns a regex
    match into `(byte_start, byte_end)` of the body payload:
        - "balanced": find the opening `{` after the macro and walk to
          its matching `}` using `_find_matching_brace`. Used for
          `\\resumeItem{...}` and `\\cvline{...}{...}` (second arg).
        - "to_next_item": body runs from the `\\item` token up to the
          next `\\item`, `\\end{itemize}`, or another recognized macro.
    """

    pattern_id: BulletPatternId
    starts_with: str
    body_extraction: Literal["balanced", "to_next_item"]


BULLET_PATTERNS: tuple[BulletPattern, ...] = (
    BulletPattern(
        pattern_id="resume_item",
        starts_with=r"\resumeItem",
        body_extraction="balanced",
    ),
    BulletPattern(
        pattern_id="cvline",
        starts_with=r"\cvline",
        body_extraction="balanced",
    ),
    BulletPattern(
        pattern_id="itemize_item",
        starts_with=r"\item",
        body_extraction="to_next_item",
    ),
)


# Compiled regexes used by the locator and validator for orphan-bullet
# detection and bullet-body extraction. We intentionally keep them at
# module scope so the cost is paid once.
RESUME_ITEM_RE: Pattern[str] = re.compile(r"\\resumeItem(?=\{)")
CVLINE_RE: Pattern[str] = re.compile(r"\\cvline(?=\{)")
ITEMIZE_BEGIN_RE: Pattern[str] = re.compile(r"\\begin\{itemize\}")
ITEMIZE_END_RE: Pattern[str] = re.compile(r"\\end\{itemize\}")

# `\item` matches as a word, not as a prefix of `\itemsep`. We use a
# negative lookahead on the next character to anchor that.
ITEM_RE: Pattern[str] = re.compile(r"\\item(?![A-Za-z])")


# ---------------------------------------------------------------------------
# §4.6 Structured validator output
# ---------------------------------------------------------------------------

# Stable error codes the validator can emit. The frontend surfaces these
# verbatim so error rendering can localize without parsing English.
ContractErrorCode = Literal[
    "CONTRACT_COMPILE_FAILED",
    "CONTRACT_NO_TAILORABLE_SECTION",
    "CONTRACT_ORPHAN_BULLET",
    "CONTRACT_UNBALANCED_BULLET",
    "CONTRACT_UNKNOWN_ENTRY_HEADER",
]


class ValidatorError(BaseModel):
    """One contract violation, line-numbered and actionable.

    Purpose:
        Tell the user exactly where their `.tex` breaks the contract
        and what to do about it. The frontend renders this as a
        numbered list with the suggested-fix snippet inline.
    """

    line: int = Field(description="1-indexed line in the user's .tex file.")
    code: str = Field(
        description="Stable error code (e.g. CONTRACT_ORPHAN_BULLET).",
    )
    violation: str = Field(description="Human-readable description.")
    suggested_fix: str = Field(
        description="Concrete snippet or doc anchor to point the user at.",
    )


# Forward reference for the manifest preview field — defined here so
# the schema doesn't pull `manifest.py` into a circular import.
class _ManifestPlaceholder(BaseModel):
    pass


__all__ = [
    "BULLET_PATTERNS",
    "BulletPattern",
    "BulletPatternId",
    "CVLINE_RE",
    "ContractErrorCode",
    "ENTRY_HEADER_PATTERNS",
    "EntryHeaderPattern",
    "EntryHeaderPatternId",
    "ITEMIZE_BEGIN_RE",
    "ITEMIZE_END_RE",
    "ITEM_RE",
    "RESUME_ITEM_RE",
    "SECTION_ALLOWLIST",
    "SECTION_HEADING_RE",
    "SectionKind",
    "ValidatorError",
]
