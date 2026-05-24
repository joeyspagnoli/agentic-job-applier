"""Pattern-level tests for `src.agents.resume_tailor.contract`.

Purpose:
    Pin the behavior of the regex constants the validator and locator
    share — specifically Risk Areas #8 (fallback B dates-opener case
    sensitivity) and #9 (SECTION_HEADING_RE interaction with `\\textbf{}`
    wrappers) from the Phase 0 handoff.
"""

from __future__ import annotations

import re

import pytest

from src.agents.resume_tailor.contract import (
    ENTRY_HEADER_PATTERNS,
    SECTION_ALLOWLIST,
    SECTION_HEADING_RE,
)


def _pattern_for(pattern_id: str) -> re.Pattern[str]:
    """Return the compiled regex for the named entry-header pattern.

    Purpose:
        Avoid hard-coding regex literals in tests — keep tests in sync
        with the contract module's source of truth.
    Args:
        pattern_id: One of the literals in `EntryHeaderPatternId`.
    Output:
        The compiled `re.Pattern` from `ENTRY_HEADER_PATTERNS`.
    """

    for pattern in ENTRY_HEADER_PATTERNS:
        if pattern.pattern_id == pattern_id:
            return pattern.regex
    raise AssertionError(f"pattern_id {pattern_id!r} not in registry")


# ---------------------------------------------------------------------------
# Risk #9 — `SECTION_HEADING_RE` and `\textbf{}` wrap interaction
# ---------------------------------------------------------------------------


def test_section_heading_matches_bare_textual_heading() -> None:
    """Risk #9 — `\\section{Experience}` matches and captures `Experience`."""

    tex = "\\section{Experience}\n"

    match = SECTION_HEADING_RE.search(tex)

    assert match is not None
    assert match.group("heading") == "Experience"


def test_section_heading_matches_textbf_wrapped_heading() -> None:
    """Risk #9 — `\\section{\\textbf{Experience}}` matches; inner text captured."""

    tex = "\\section{\\textbf{Experience}}\n"

    match = SECTION_HEADING_RE.search(tex)

    assert match is not None
    assert match.group("heading") == "Experience"


def test_section_heading_match_falls_into_allowlist_lookup() -> None:
    """Risk #9 — both wrapped and bare headings normalize into the allowlist."""

    bare = SECTION_HEADING_RE.search("\\section{Projects}\n")
    wrapped = SECTION_HEADING_RE.search("\\section{\\textbf{Projects}}\n")

    assert bare is not None and wrapped is not None
    assert SECTION_ALLOWLIST.get(bare.group("heading").strip().lower()) == "projects"
    assert SECTION_ALLOWLIST.get(wrapped.group("heading").strip().lower()) == "projects"


def test_section_heading_does_not_match_starred_form() -> None:
    """`\\section*{...}` is intentionally NOT recognized (contract decision)."""

    tex = "\\section*{Hidden}\n"

    match = SECTION_HEADING_RE.search(tex)

    assert match is None


def test_section_heading_finds_multiple_headings_in_document() -> None:
    """All `\\section` lines must be found by `finditer`."""

    tex = (
        "\\section{Experience}\n"
        "stuff\n"
        "\\section{Education}\n"
        "more\n"
        "\\section{Projects}\n"
    )

    headings = [m.group("heading") for m in SECTION_HEADING_RE.finditer(tex)]

    assert headings == ["Experience", "Education", "Projects"]


def test_section_heading_requires_section_macro_to_start_a_line() -> None:
    """`\\section` mid-line (not column 0) must not match — anchored at line start."""

    tex = "intro \\section{Experience}\n"

    match = SECTION_HEADING_RE.search(tex)

    assert match is None


@pytest.mark.parametrize(
    "heading_text,expected_kind",
    [
        ("experience", "experience"),
        ("Experience", "experience"),
        ("Work Experience", "experience"),
        ("Professional Experience", "experience"),
        ("Employment", "experience"),
        ("Projects", "projects"),
        ("Side Projects", "projects"),
        ("Personal Projects", "projects"),
        ("Open Source Projects", "projects"),
    ],
)
def test_section_allowlist_recognizes_canonical_variants(
    heading_text: str, expected_kind: str
) -> None:
    """Every canonical heading from the contract docs must map correctly."""

    kind = SECTION_ALLOWLIST.get(heading_text.lower())

    assert kind == expected_kind


@pytest.mark.parametrize(
    "heading_text",
    ["Education", "Skills", "Awards", "Hobbies", "Summary", "Certifications"],
)
def test_section_allowlist_returns_none_for_non_tailorable_headings(
    heading_text: str,
) -> None:
    """Non-tailorable sections must NOT be in the allowlist (they get `other` kind)."""

    assert SECTION_ALLOWLIST.get(heading_text.lower()) is None


# ---------------------------------------------------------------------------
# Risk #8 — Fallback B (`fallback_textbf_hfill_dates`) dates-opener
# ---------------------------------------------------------------------------


def test_fallback_b_matches_dates_starting_with_uppercase_letter() -> None:
    """Risk #8 — fallback B accepts dates that open with an uppercase letter.

    `Jan 2024 -- Present` opens with `J` (uppercase) and must match.
    """

    regex = _pattern_for("fallback_textbf_hfill_dates")
    line = "\\textbf{Senior Engineer}\\hfill Jan 2024 -- Present"

    match = regex.search(line)

    assert match is not None
    assert match.group("role") == "Senior Engineer"
    assert match.group("dates").startswith("Jan 2024")


def test_fallback_b_matches_dates_starting_with_digit() -> None:
    """Risk #8 — fallback B accepts dates that open with a digit (year)."""

    regex = _pattern_for("fallback_textbf_hfill_dates")
    line = "\\textbf{Engineer}\\hfill 2024 -- Present"

    match = regex.search(line)

    assert match is not None
    assert match.group("dates").startswith("2024")


def test_fallback_b_rejects_dates_starting_with_lowercase_letter() -> None:
    """Risk #8 — lowercase opener (prose, not dates) must NOT match."""

    regex = _pattern_for("fallback_textbf_hfill_dates")
    line = "\\textbf{Engineer}\\hfill jan 2024"

    match = regex.search(line)

    assert match is None


def test_fallback_b_accepts_optional_trailing_double_backslash() -> None:
    """Trailing `\\\\` LaTeX hard line-break is allowed."""

    regex = _pattern_for("fallback_textbf_hfill_dates")
    line = "\\textbf{Engineer}\\hfill 2024 -- Present \\\\"

    match = regex.search(line)

    assert match is not None


def test_fallback_b_requires_hfill_between_role_and_dates() -> None:
    """Without `\\hfill`, the pattern must not match (it would catch prose)."""

    regex = _pattern_for("fallback_textbf_hfill_dates")
    line = "\\textbf{Engineer} 2024 -- Present"

    match = regex.search(line)

    assert match is None


# ---------------------------------------------------------------------------
# Fallback A (`fallback_textbf_at`) — role-at-company prose
# ---------------------------------------------------------------------------


def test_fallback_a_matches_role_at_company_on_its_own_line() -> None:
    """`\\textbf{Engineer at Acme}` on its own line matches fallback A."""

    regex = _pattern_for("fallback_textbf_at")
    line = "\\textbf{Engineer at Acme Corp}\n"

    match = regex.search(line)

    assert match is not None
    assert "at" in match.group("role_at_company")


def test_fallback_a_rejects_textbf_without_at_separator() -> None:
    """A `\\textbf{...}` without the `at` separator is just bold prose."""

    regex = _pattern_for("fallback_textbf_at")
    line = "\\textbf{Senior Engineer}\n"

    match = regex.search(line)

    assert match is None


# ---------------------------------------------------------------------------
# Macro patterns — multi-line invocations and optional brackets
# ---------------------------------------------------------------------------


def test_resume_subheading_matches_multi_line_invocation() -> None:
    """`\\resumeSubheading{...}` allows args split across lines."""

    regex = _pattern_for("resumeSubheading")
    text = (
        "\\resumeSubheading\n"
        "  {Senior Engineer}\n"
        "  {2024 -- Present}\n"
        "  {Acme Corp}\n"
        "  {Remote}\n"
    )

    match = regex.search(text)

    assert match is not None


def test_cventry_accepts_optional_bracket_arg() -> None:
    """`\\cventry[opts]{a}{b}{c}{d}{e}{f}` must match with the `[opts]` block."""

    regex = _pattern_for("cventry")
    text = "\\cventry[1em]{2024}{Engineer}{Acme}{Remote}{}{description}"

    match = regex.search(text)

    assert match is not None


def test_cventry_also_matches_without_optional_brackets() -> None:
    """`\\cventry{a}{b}{c}{d}{e}{f}` (no brackets) must also match."""

    regex = _pattern_for("cventry")
    text = "\\cventry{2024}{Engineer}{Acme}{Remote}{}{description}"

    match = regex.search(text)

    assert match is not None


def test_deedy_runsubsection_requires_pipe_in_descript_arg() -> None:
    """The Deedy header pattern requires `|` in `\\descript{|...}`."""

    regex = _pattern_for("deedy_runsubsection")

    matching = (
        "\\runsubsection{Acme} \\descript{| Engineer} \\location{2024}"
    )
    non_matching = (
        "\\runsubsection{Acme} \\descript{Engineer} \\location{2024}"
    )

    assert regex.search(matching) is not None
    assert regex.search(non_matching) is None


def test_cvitem_matches_two_brace_form() -> None:
    """`\\cvitem{dates}{role at company}` is the ModernCV terse form."""

    regex = _pattern_for("cvitem")
    text = "\\cvitem{2024}{Engineer at Acme}"

    match = regex.search(text)

    assert match is not None


def test_cvevent_matches_four_brace_form() -> None:
    """`\\cvevent{title}{dates}{location}{description}` — AltaCV form."""

    regex = _pattern_for("cvevent")
    text = "\\cvevent{Engineer}{2024}{Remote}{desc}"

    match = regex.search(text)

    assert match is not None


def test_generic_bold_item_matches_dogfood_style_header() -> None:
    """`\\item{\\textbf{Role}}\\hfill{\\textbf{Dates}}` (dogfood resume form)."""

    regex = _pattern_for("generic_bold_item")
    text = "\\item {\\textbf{Senior Engineer}}\\hfill{\\textbf{2024 -- Present}}"

    match = regex.search(text)

    assert match is not None


def test_generic_bold_item_dates_section_is_optional() -> None:
    """The `\\hfill {\\textbf{Dates}}` tail is optional."""

    regex = _pattern_for("generic_bold_item")
    text = "\\item {\\textbf{Senior Engineer}}"

    match = regex.search(text)

    assert match is not None
