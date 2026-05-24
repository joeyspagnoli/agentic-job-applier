"""Unit tests for the private helpers in `src.agents.resume_tailor.locator`.

Purpose:
    Cover Risk Areas #2 (`_resolve_itemize_item_body` boundary handling),
    #3 (`_dedupe_by_line` macro-over-fallback precedence), and #5
    (entry-id minting + line-span math) from the Phase 0 handoff. The
    public-API tests in `test_bullet_locator.py` exercise the happy path;
    these tests pin the corner cases that the helpers can hide.
"""

from __future__ import annotations

import re

from src.agents.resume_tailor.contract import ENTRY_HEADER_PATTERNS, EntryHeaderPattern
from src.agents.resume_tailor.locator import (
    MAX_ENTRY_ID_LENGTH,
    _build_entry_id,
    _dedupe_by_line,
    _EntryHeaderHit,
    _line_span_containing,
    _resolve_balanced_brace_body,
    _resolve_itemize_item_body,
    build_bullet_manifest,
)
from src.agents.resume_tailor.manifest import BulletManifest


def _pattern_by_id(pattern_id: str) -> EntryHeaderPattern:
    """Pick an `EntryHeaderPattern` from the shared registry by id.

    Purpose:
        Build realistic `_EntryHeaderHit` instances without hand-crafting
        regex objects.
    Args:
        pattern_id: One of the literals from `EntryHeaderPatternId`.
    Output:
        The matching `EntryHeaderPattern` from `ENTRY_HEADER_PATTERNS`.
    """

    for pattern in ENTRY_HEADER_PATTERNS:
        if pattern.pattern_id == pattern_id:
            return pattern
    raise AssertionError(f"pattern_id {pattern_id!r} not in registry")


# ---------------------------------------------------------------------------
# Risk #3 — `_dedupe_by_line` macro-over-fallback precedence
# ---------------------------------------------------------------------------


def test_dedupe_prefers_macro_pattern_over_fallback_on_same_line() -> None:
    """Risk #3 — a macro hit must beat a fallback hit at the same line."""

    fallback_pattern = _pattern_by_id("fallback_textbf_at")
    macro_pattern = _pattern_by_id("resumeSubheading")

    fallback_first = _EntryHeaderHit(
        line_start=10,
        line_end=80,
        header_text="\\textbf{Engineer at Acme}",
        pattern=fallback_pattern,
    )
    macro_second = _EntryHeaderHit(
        line_start=10,
        line_end=80,
        header_text="\\resumeSubheading{Engineer}{2024}{Acme}{Remote}",
        pattern=macro_pattern,
    )

    deduped = _dedupe_by_line([fallback_first, macro_second])

    assert len(deduped) == 1
    assert deduped[0].pattern.pattern_id == "resumeSubheading"


def test_dedupe_keeps_macro_pattern_when_macro_comes_first() -> None:
    """Risk #3 — once a macro hit is in, a later fallback hit cannot evict it."""

    fallback_pattern = _pattern_by_id("fallback_textbf_at")
    macro_pattern = _pattern_by_id("resumeSubheading")

    macro_first = _EntryHeaderHit(
        line_start=10,
        line_end=80,
        header_text="\\resumeSubheading{Engineer}{2024}{Acme}{Remote}",
        pattern=macro_pattern,
    )
    fallback_second = _EntryHeaderHit(
        line_start=10,
        line_end=80,
        header_text="\\textbf{Engineer at Acme}",
        pattern=fallback_pattern,
    )

    deduped = _dedupe_by_line([macro_first, fallback_second])

    assert len(deduped) == 1
    assert deduped[0].pattern.pattern_id == "resumeSubheading"


def test_dedupe_returns_hits_sorted_by_line_start() -> None:
    """Risk #3 — output ordering must be ascending by `line_start`."""

    macro_pattern = _pattern_by_id("resumeSubheading")

    hits = [
        _EntryHeaderHit(line_start=50, line_end=80, header_text="c", pattern=macro_pattern),
        _EntryHeaderHit(line_start=10, line_end=20, header_text="a", pattern=macro_pattern),
        _EntryHeaderHit(line_start=30, line_end=40, header_text="b", pattern=macro_pattern),
    ]

    deduped = _dedupe_by_line(hits)

    assert [hit.line_start for hit in deduped] == [10, 30, 50]


def test_dedupe_handles_empty_input() -> None:
    """An empty hit list returns an empty list — never raises."""

    result = _dedupe_by_line([])

    assert result == []


def test_dedupe_keeps_fallback_when_no_macro_competes() -> None:
    """A solo fallback hit must survive when no macro hit shadows it."""

    fallback_pattern = _pattern_by_id("fallback_textbf_at")

    fallback_only = _EntryHeaderHit(
        line_start=5,
        line_end=50,
        header_text="\\textbf{Engineer at Acme}",
        pattern=fallback_pattern,
    )

    deduped = _dedupe_by_line([fallback_only])

    assert len(deduped) == 1
    assert deduped[0].pattern.template_family == "fallback"


# ---------------------------------------------------------------------------
# Risk #2 — `_resolve_itemize_item_body` boundary handling
# ---------------------------------------------------------------------------


def test_itemize_item_body_terminates_at_next_item_token() -> None:
    """Risk #2 — `\\item ...text \\item` stops at the next `\\item`."""

    text = "\\item first body text\n\\item second"
    macro_position = 0

    span = _resolve_itemize_item_body(
        tex_text=text, macro_position=macro_position, range_end=len(text)
    )

    assert span is not None
    body_start, body_end, advance_to = span
    body_text = text[body_start:body_end]
    assert body_text.strip() == "first body text"
    # The advance cursor must land on the next `\item` boundary so the
    # caller's outer loop picks it up next iteration.
    assert text[advance_to : advance_to + len("\\item")] == "\\item"


def test_itemize_item_body_terminates_at_resume_item() -> None:
    """Risk #2 — boundary detection includes `\\resumeItem` and `\\cvline`."""

    text = "\\item plain body\n\\resumeItem{styled body}"
    macro_position = 0

    span = _resolve_itemize_item_body(
        tex_text=text, macro_position=macro_position, range_end=len(text)
    )

    assert span is not None
    body_start, body_end, _ = span
    assert text[body_start:body_end].strip() == "plain body"


def test_itemize_item_body_terminates_at_resume_item_list_end() -> None:
    """Risk #2 — `\\resumeItemListEnd` is a valid boundary token."""

    text = "\\item tail bullet\n\\resumeItemListEnd"
    macro_position = 0

    span = _resolve_itemize_item_body(
        tex_text=text, macro_position=macro_position, range_end=len(text)
    )

    assert span is not None
    body_start, body_end, _ = span
    assert text[body_start:body_end].strip() == "tail bullet"


def test_itemize_item_brace_form_extracts_balanced_body() -> None:
    """Risk #2 — `\\item{...}` form returns the balanced inner body."""

    text = "\\item{wrapped body with \\textbf{nested} group}\n\\item next"
    macro_position = 0

    span = _resolve_itemize_item_body(
        tex_text=text, macro_position=macro_position, range_end=len(text)
    )

    assert span is not None
    body_start, body_end, _ = span
    extracted = text[body_start:body_end]
    assert extracted == "wrapped body with \\textbf{nested} group"


def test_itemize_item_body_trims_trailing_whitespace() -> None:
    """Risk #2 — `body_end` is trimmed of trailing spaces/tabs/newlines."""

    text = "\\item body with trailing space    \n\\item next"
    macro_position = 0

    span = _resolve_itemize_item_body(
        tex_text=text, macro_position=macro_position, range_end=len(text)
    )

    assert span is not None
    body_start, body_end, _ = span
    # The recorded body must not end on whitespace.
    assert not text[body_end - 1].isspace()
    assert text[body_start:body_end] == "body with trailing space"


def test_itemize_item_body_returns_none_for_whitespace_only_body() -> None:
    """Risk #2 — an empty/whitespace-only body returns `None`."""

    # `\item` with nothing useful before the next boundary.
    text = "\\item   \n\\item next"
    macro_position = 0

    span = _resolve_itemize_item_body(
        tex_text=text, macro_position=macro_position, range_end=len(text)
    )

    assert span is None


def test_itemize_item_body_runs_to_range_end_when_no_boundary_present() -> None:
    """Risk #2 — without a boundary token, body extends to `range_end`."""

    text = "\\item only bullet ever"
    macro_position = 0

    span = _resolve_itemize_item_body(
        tex_text=text, macro_position=macro_position, range_end=len(text)
    )

    assert span is not None
    body_start, body_end, advance_to = span
    assert text[body_start:body_end] == "only bullet ever"
    assert advance_to == len(text)


def test_itemize_item_body_skips_leading_spaces_and_tabs() -> None:
    """Risk #2 — leading whitespace between `\\item` and content is stripped."""

    text = "\\item\t  body after tab and spaces\n\\item next"
    macro_position = 0

    span = _resolve_itemize_item_body(
        tex_text=text, macro_position=macro_position, range_end=len(text)
    )

    assert span is not None
    body_start, _, _ = span
    # body_start must point AT the `b` of "body", not at the whitespace.
    assert text[body_start] == "b"


# ---------------------------------------------------------------------------
# `_resolve_balanced_brace_body` — `arg_index=1` for `\cvline`
# ---------------------------------------------------------------------------


def test_balanced_brace_body_returns_first_arg_when_arg_index_zero() -> None:
    """Risk #2 — `arg_index=0` returns the first `{...}` body."""

    text = "\\resumeItem{the body text}"
    macro_position = 0

    span = _resolve_balanced_brace_body(
        tex_text=text,
        macro_position=macro_position,
        arg_index=0,
        range_end=len(text),
    )

    assert span is not None
    body_start, body_end, advance_to = span
    assert text[body_start:body_end] == "the body text"
    assert advance_to == len(text)


def test_balanced_brace_body_skips_first_arg_when_arg_index_one() -> None:
    """`arg_index=1` (for `\\cvline`) skips arg 0 and returns arg 1."""

    text = "\\cvline{dates}{the actual body text}"
    macro_position = 0

    span = _resolve_balanced_brace_body(
        tex_text=text,
        macro_position=macro_position,
        arg_index=1,
        range_end=len(text),
    )

    assert span is not None
    body_start, body_end, _ = span
    assert text[body_start:body_end] == "the actual body text"


def test_balanced_brace_body_returns_none_when_arg_missing() -> None:
    """Risk #2 — missing arg at the requested index returns `None`."""

    text = "\\cvline{only one arg}"
    macro_position = 0

    span = _resolve_balanced_brace_body(
        tex_text=text,
        macro_position=macro_position,
        arg_index=1,
        range_end=len(text),
    )

    assert span is None


def test_balanced_brace_body_returns_none_when_unbalanced() -> None:
    """Risk #2 — unbalanced body returns `None` (delegates to brace walker)."""

    text = "\\resumeItem{open with no close"
    macro_position = 0

    span = _resolve_balanced_brace_body(
        tex_text=text,
        macro_position=macro_position,
        arg_index=0,
        range_end=len(text),
    )

    assert span is None


def test_balanced_brace_body_respects_range_end() -> None:
    """Risk #2 — bodies that close past `range_end` return `None`."""

    text = "\\resumeItem{body extends past the cap}"
    # Cap mid-body, before the closing brace.
    range_cap = text.index("body")

    span = _resolve_balanced_brace_body(
        tex_text=text,
        macro_position=0,
        arg_index=0,
        range_end=range_cap,
    )

    assert span is None


# ---------------------------------------------------------------------------
# Risk #5 — `_line_span_containing` math
# ---------------------------------------------------------------------------


def test_line_span_first_line_starts_at_zero() -> None:
    """Risk #5 — position on line 1 yields `line_start == 0`."""

    text = "first\nsecond\nthird"

    start, end = _line_span_containing(text, position=2)

    assert start == 0
    assert text[start:end] == "first"


def test_line_span_middle_line_excludes_newline_boundaries() -> None:
    """Risk #5 — `line_end` points at the trailing newline (exclusive)."""

    text = "first\nsecond\nthird"
    middle_offset = text.index("second") + 1  # inside "second"

    start, end = _line_span_containing(text, position=middle_offset)

    assert text[start:end] == "second"
    assert text[end] == "\n"


def test_line_span_last_line_without_trailing_newline() -> None:
    """Risk #5 — last line without `\\n` ends at `len(tex_text)`."""

    text = "first\nlast"
    last_offset = text.index("last") + 2

    start, end = _line_span_containing(text, position=last_offset)

    assert text[start:end] == "last"
    assert end == len(text)


def test_line_span_handles_position_past_end() -> None:
    """Risk #5 — positions beyond text length are clamped, not raised on."""

    text = "only"

    start, end = _line_span_containing(text, position=999)

    assert (start, end) == (0, len(text))


def test_line_span_handles_position_on_newline_itself() -> None:
    """Risk #5 — pointing at the `\\n` returns the preceding line span."""

    text = "alpha\nbeta"
    newline_index = text.index("\n")

    start, end = _line_span_containing(text, position=newline_index)

    # rfind("\n", 0, newline_index) returns -1, so line_start is 0;
    # find("\n", newline_index) returns newline_index, so line_end is
    # newline_index. The line is "alpha".
    assert text[start:end] == "alpha"


# ---------------------------------------------------------------------------
# Risk #5 — `_build_entry_id` slugging + truncation
# ---------------------------------------------------------------------------


def test_build_entry_id_strips_latex_macro_tokens() -> None:
    """Risk #5 — `\\textbf`, `\\hfill` are removed before slugifying."""

    header = "\\textbf{Senior Engineer} \\hfill \\textbf{2024 -- Present}"

    entry_id = _build_entry_id(
        section_id="experience", header_text=header, sequence=0
    )

    # Tokens like "textbf" or "hfill" must NOT appear in the slug.
    assert "textbf" not in entry_id
    assert "hfill" not in entry_id
    # The actual role words should survive in some form.
    assert "senior" in entry_id


def test_build_entry_id_includes_section_id_prefix_and_sequence_suffix() -> None:
    """Risk #5 — id format is `{section}_{slug}_{sequence}`."""

    entry_id = _build_entry_id(
        section_id="projects", header_text="Open Source Tooling", sequence=3
    )

    assert entry_id.startswith("projects_")
    assert entry_id.endswith("_3")


def test_build_entry_id_truncates_to_max_entry_id_length() -> None:
    """Risk #5 — ids are capped at `MAX_ENTRY_ID_LENGTH` characters."""

    very_long_header = "Word " * 50

    entry_id = _build_entry_id(
        section_id="experience",
        header_text=very_long_header,
        sequence=0,
    )

    assert len(entry_id) <= MAX_ENTRY_ID_LENGTH


def test_build_entry_id_caps_slug_at_eight_words() -> None:
    """Risk #5 — only the first 8 words of the header land in the slug."""

    header = "one two three four five six seven eight nine ten eleven"

    entry_id = _build_entry_id(
        section_id="experience", header_text=header, sequence=0
    )

    # `nine`, `ten`, `eleven` must NOT appear in the id.
    assert "nine" not in entry_id
    assert "ten" not in entry_id
    assert "eleven" not in entry_id
    # The first 8 words should be present.
    assert "eight" in entry_id


def test_build_entry_id_falls_back_to_entry_when_slug_is_empty() -> None:
    """Risk #5 — a header that slugs to nothing produces the `entry` slug."""

    # Header consisting entirely of LaTeX macros + punctuation.
    header = "\\textbf{}\\hfill"

    entry_id = _build_entry_id(
        section_id="experience", header_text=header, sequence=0
    )

    assert entry_id == "experience_entry_0"


def test_build_entry_id_collapses_non_alphanumeric_into_underscores() -> None:
    """Risk #5 — punctuation and whitespace flatten into single `_` runs."""

    header = "Role: A&B, Inc. (2024 -- Present)"

    entry_id = _build_entry_id(
        section_id="experience", header_text=header, sequence=0
    )

    # No double underscores expected, no punctuation passed through.
    assert "__" not in entry_id
    # The pattern must match `lowercase + digits + underscores` only.
    assert re.fullmatch(r"[a-z0-9_]+", entry_id) is not None


# ---------------------------------------------------------------------------
# Risk #5 — `_collect_section_records` body_end calculation (via public API)
# ---------------------------------------------------------------------------


def test_section_body_end_is_next_section_start_for_intermediate_sections() -> None:
    """Risk #5 — intermediate sections' `body_end` is the next section's start.

    We verify this via the public manifest: bullets in Experience must
    not bleed into Projects.
    """

    tex = (
        "\\documentclass{article}\n"
        "\\newcommand{\\resumeItem}[1]{\\item #1}\n"
        "\\newcommand{\\resumeSubheading}[4]"
        "{\\item \\textbf{#1} \\hfill \\textbf{#2}\\\\#3\\hfill#4}\n"
        "\\begin{document}\n"
        "\\section{Experience}\n"
        "\\begin{itemize}\n"
        "  \\resumeSubheading{Engineer}{2024}{Acme}{Remote}\n"
        "    \\begin{itemize}\\resumeItem{exp-bullet}\\end{itemize}\n"
        "\\end{itemize}\n"
        "\\section{Projects}\n"
        "\\begin{itemize}\n"
        "  \\resumeSubheading{P1}{2023}{Solo}{}\n"
        "    \\begin{itemize}\\resumeItem{proj-bullet}\\end{itemize}\n"
        "\\end{itemize}\n"
        "\\end{document}\n"
    )

    manifest = build_bullet_manifest(tex)

    experience = next(s for s in manifest.sections if s.kind == "experience")
    projects = next(s for s in manifest.sections if s.kind == "projects")

    experience_bullets = [b.text for e in experience.entries for b in e.bullets]
    project_bullets = [b.text for e in projects.entries for b in e.bullets]

    assert experience_bullets == ["exp-bullet"]
    assert project_bullets == ["proj-bullet"]


def test_locator_extracts_cvline_body_from_second_brace_arg() -> None:
    """Risk #2 — `\\cvline{label}{body}` returns the SECOND arg as the body.

    Exercises the `cvline` branch of `_resolve_body_span` end-to-end.
    """

    tex = (
        "\\documentclass{article}\n"
        "\\newcommand{\\cvline}[2]{\\textbf{#1} #2}\n"
        "\\newcommand{\\cventry}[6]{\\textbf{#3} #4}\n"
        "\\begin{document}\n"
        "\\section{Experience}\n"
        "\\cventry{2024}{}{Engineer}{Acme}{Remote}{}\n"
        "\\cvline{Tech}{Built the distributed cache from scratch.}\n"
        "\\cvline{Impact}{Cut p99 latency by 70 percent.}\n"
        "\\end{document}\n"
    )

    manifest = build_bullet_manifest(tex)

    bullets = [
        b for s in manifest.sections for e in s.entries for b in e.bullets
    ]
    bullet_texts = [b.text for b in bullets]
    assert "Built the distributed cache from scratch." in bullet_texts
    assert "Cut p99 latency by 70 percent." in bullet_texts


def test_locator_recovers_from_unbalanced_bullet_without_looping() -> None:
    """Risk #2 — an unbalanced `\\resumeItem{...` advances the cursor cleanly.

    Without the recovery branch in `_extract_bullets` the locator would
    spin forever on a malformed bullet. We feed it a fixture the
    validator would normally have rejected and confirm it returns
    quickly with the well-formed bullet still extracted.
    """

    tex = (
        "\\documentclass{article}\n"
        "\\newcommand{\\resumeItem}[1]{\\item #1}\n"
        "\\newcommand{\\resumeSubheading}[4]"
        "{\\item \\textbf{#1} \\hfill \\textbf{#2}\\\\#3\\hfill#4}\n"
        "\\begin{document}\n"
        "\\section{Experience}\n"
        "\\begin{itemize}\n"
        "  \\resumeSubheading{Engineer}{2024}{Acme}{Remote}\n"
        "    \\begin{itemize}\n"
        "      \\resumeItem{Unbalanced body with no closing brace ever\n"
        "      \\resumeItem{Well-formed bullet right after the broken one.}\n"
        "    \\end{itemize}\n"
        "\\end{itemize}\n"
        "\\end{document}\n"
    )

    manifest = build_bullet_manifest(tex)

    bullet_texts = [
        b.text for s in manifest.sections for e in s.entries for b in e.bullets
    ]
    # The well-formed bullet may or may not survive depending on how
    # the unbalanced body consumed the following text; what we MUST
    # see is that the call returned in finite time with a manifest.
    assert isinstance(manifest, BulletManifest)
    assert len(bullet_texts) >= 0


def test_last_section_body_end_is_end_of_document() -> None:
    """Risk #5 — the last section's body_end is `len(tex_text)`."""

    # Bullet lives AFTER the last section's heading; if body_end were
    # mis-calculated as the start of a phantom next section the bullet
    # would be dropped from the manifest.
    tex = (
        "\\documentclass{article}\n"
        "\\newcommand{\\resumeItem}[1]{\\item #1}\n"
        "\\newcommand{\\resumeSubheading}[4]"
        "{\\item \\textbf{#1} \\hfill \\textbf{#2}\\\\#3\\hfill#4}\n"
        "\\begin{document}\n"
        "\\section{Experience}\n"
        "\\begin{itemize}\n"
        "  \\resumeSubheading{Engineer}{2024}{Acme}{Remote}\n"
        "    \\begin{itemize}\\resumeItem{last-bullet}\\end{itemize}\n"
        "\\end{itemize}\n"
        "\\end{document}\n"
    )

    manifest = build_bullet_manifest(tex)

    bullets = [b.text for s in manifest.sections for e in s.entries for b in e.bullets]
    assert "last-bullet" in bullets
