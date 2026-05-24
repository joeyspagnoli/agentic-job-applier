"""Deterministic bullet locator for `.tex` resumes that conform to the contract.

Purpose:
    Walk a contract-conforming `.tex` document and emit a `BulletManifest`
    that the tailor pipeline can hand to the LLM (filtered down to
    experience + projects) and that the patcher can splice into. Pure
    function: same input → same output, no LLM call, no caching.

The walker is layered:
    1. Find every `\\section{...}` heading and map to `experience` /
       `projects` / `other` via the §2.1 allowlist.
    2. For each tailorable section, walk its body looking for an
       entry-header match from §2.2 (6 macro forms + 2 fallbacks).
    3. For each entry, locate every bullet between its header line and
       the next entry's header line using the §2.3 patterns, recording
       (byte_start, byte_end) of the body payload only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from ._braces import find_matching_brace
from .contract import (
    CVLINE_RE,
    ENTRY_HEADER_PATTERNS,
    ITEM_RE,
    RESUME_ITEM_RE,
    SECTION_ALLOWLIST,
    SECTION_HEADING_RE,
    EntryHeaderPattern,
)
from .manifest import BulletEntry, BulletItem, BulletManifest, BulletSection

# Cap the length of any generated identifier so manifest IDs stay
# readable in LLM payloads and DB columns. Bullet IDs append a `_b<N>`
# suffix to their entry ID, so we reserve room for that suffix and
# truncate the entry portion shorter than the overall bullet cap.
MAX_ID_LENGTH = 64
BULLET_SUFFIX_RESERVE = 6  # supports up to `_b9999`, well past realistic counts
MAX_ENTRY_ID_LENGTH = MAX_ID_LENGTH - BULLET_SUFFIX_RESERVE

# Number of words to slug into the entry-id from the header text. Eight
# is the threshold the plan landed on (§3.1) — long enough to be
# recognizable, short enough not to dominate the ID.
ENTRY_ID_SLUG_WORDS = 8


@dataclass(frozen=True)
class _EntryHeaderHit:
    """One detected entry-header line, pre-deduplication.

    Purpose:
        Internal record carried between the entry-header scan and the
        per-line dedupe step. Holds enough state to pick the highest-
        priority match when several patterns hit the same line.
    """

    line_start: int
    line_end: int
    header_text: str
    pattern: EntryHeaderPattern


def build_bullet_manifest(tex_text: str) -> BulletManifest:
    """Build the deterministic bullet manifest for a resume `.tex`.

    Purpose:
        Produce the canonical view of every tailorable bullet in the
        document, in source order, with stable IDs and byte spans the
        patcher can use to splice replacements back in.
    Args:
        tex_text: Full text of the user's `config/resume.tex` (or any
            conforming `.tex`). Must already pass `validate_resume_tex`
            for the manifest to be meaningful — the locator does not
            re-validate.
    Output:
        `BulletManifest` containing only sections of kind `experience`
        or `projects`. Skills / Education / Summary / Awards / etc. are
        intentionally filtered out per the contract.
    """

    # Walk every `\section{...}` heading once so we can compute body
    # spans (each section ends where the next one starts, or EOF).
    section_matches = list(SECTION_HEADING_RE.finditer(tex_text))
    total_length = len(tex_text)

    sections_out: list[BulletSection] = []
    # Per-kind sequence counter so a second "Projects" section gets
    # `projects_2` to keep IDs unique across the manifest.
    kind_sequence: dict[str, int] = {"experience": 0, "projects": 0}

    for index, section_match in enumerate(section_matches):
        heading_raw = section_match.group("heading").strip()
        kind = SECTION_ALLOWLIST.get(heading_raw.lower())
        if kind is None:
            # `other` kind — skills/education/etc. The locator never
            # surfaces these to the manifest; the validator may inspect
            # them separately for contract conformance but does not
            # parse their internals.
            continue

        body_start = section_match.end()
        body_end = (
            section_matches[index + 1].start()
            if index + 1 < len(section_matches)
            else total_length
        )

        kind_sequence[kind] += 1
        section_id = (
            kind if kind_sequence[kind] == 1 else f"{kind}_{kind_sequence[kind]}"
        )

        entries = _walk_entries(
            tex_text=tex_text,
            body_start=body_start,
            body_end=body_end,
            section_id=section_id,
        )

        sections_out.append(
            BulletSection(
                id=section_id,
                kind=kind,
                heading=heading_raw,
                entries=entries,
            )
        )

    return BulletManifest(sections=sections_out)


def _walk_entries(
    *,
    tex_text: str,
    body_start: int,
    body_end: int,
    section_id: str,
) -> list[BulletEntry]:
    """Walk one section body and emit its `BulletEntry` list.

    Purpose:
        Detect entry headers via the §2.2 patterns, dedupe per line
        (macro forms beat fallback forms when both match a line), then
        slice the section into per-entry bullet ranges.
    Args:
        tex_text: Full document text (used for absolute byte offsets).
        body_start: Absolute offset where this section's body begins.
        body_end: Absolute offset where the next section starts, or EOF.
        section_id: Stable identifier of the enclosing section, used as
            the prefix when minting entry IDs.
    Output:
        Ordered list of `BulletEntry`. Empty when the section has no
        recognized entry headers.
    """

    hits = list(_scan_entry_header_hits(tex_text, body_start, body_end))
    deduped = _dedupe_by_line(hits)

    entries_out: list[BulletEntry] = []
    for entry_index, header_hit in enumerate(deduped):
        # Bullet content lives between this entry's header line end and
        # the next entry's header line start (or section end).
        if entry_index + 1 < len(deduped):
            next_header_start = deduped[entry_index + 1].line_start
        else:
            next_header_start = body_end

        entry_id = _build_entry_id(
            section_id=section_id,
            header_text=header_hit.header_text,
            sequence=entry_index,
        )

        bullets = _extract_bullets(
            tex_text=tex_text,
            start=header_hit.line_end,
            end=next_header_start,
            entry_id=entry_id,
        )

        entries_out.append(
            BulletEntry(
                id=entry_id,
                role_context=header_hit.header_text,
                header_byte_start=header_hit.line_start,
                bullets=bullets,
            )
        )

    return entries_out


def _scan_entry_header_hits(
    tex_text: str,
    body_start: int,
    body_end: int,
) -> Iterable[_EntryHeaderHit]:
    """Yield one `_EntryHeaderHit` per regex match in a section body.

    Purpose:
        Run every §2.2 pattern over the section body and emit raw,
        un-deduped hits. The caller is responsible for resolving
        multiple-patterns-on-one-line collisions.
    Args:
        tex_text: Full document text.
        body_start: Section body start offset (inclusive).
        body_end: Section body end offset (exclusive).
    Output:
        Generator of `_EntryHeaderHit`, one per regex match.
    """

    section_body = tex_text[body_start:body_end]
    for pattern_def in ENTRY_HEADER_PATTERNS:
        for match in pattern_def.regex.finditer(section_body):
            absolute_match_start = body_start + match.start()
            line_start, line_end = _line_span_containing(
                tex_text, absolute_match_start
            )
            header_text = tex_text[line_start:line_end].strip()
            yield _EntryHeaderHit(
                line_start=line_start,
                line_end=line_end,
                header_text=header_text,
                pattern=pattern_def,
            )


def _dedupe_by_line(hits: list[_EntryHeaderHit]) -> list[_EntryHeaderHit]:
    """Reduce per-line hit collisions, preferring macro forms over fallbacks.

    Purpose:
        Per §2.2 the two fallback patterns are only engaged when none
        of the six macro forms matched a given line. We honor that by
        bucketing hits per line and keeping the first non-fallback hit
        if any, otherwise the first fallback hit.
    Args:
        hits: All raw hits from the scan pass.
    Output:
        Ordered list of `_EntryHeaderHit` with one entry per source
        line, sorted by `line_start` ascending.
    """

    by_line: dict[int, _EntryHeaderHit] = {}
    for hit in hits:
        existing = by_line.get(hit.line_start)
        if existing is None:
            by_line[hit.line_start] = hit
            continue
        existing_is_fallback = existing.pattern.template_family == "fallback"
        new_is_fallback = hit.pattern.template_family == "fallback"
        # Replace only when the existing pick is a fallback and the new
        # hit is a macro — never demote a macro to a fallback.
        if existing_is_fallback and not new_is_fallback:
            by_line[hit.line_start] = hit

    return sorted(by_line.values(), key=lambda h: h.line_start)


def _extract_bullets(
    *,
    tex_text: str,
    start: int,
    end: int,
    entry_id: str,
) -> list[BulletItem]:
    """Extract bullet payloads from one entry's content range.

    Purpose:
        Find every `\\resumeItem{...}`, `\\cvline{}{}`, and itemize
        `\\item` token in `[start, end)` and record the body span the
        patcher will splice into.
    Args:
        tex_text: Full document text.
        start: Inclusive start of the entry's content range (typically
            the byte right after the entry-header line).
        end: Exclusive end of the entry's content range (typically the
            start of the next entry's header line).
        entry_id: Stable identifier of the enclosing entry, used as the
            prefix when minting bullet IDs.
    Output:
        Ordered list of `BulletItem` with `text` plus byte offsets.
    """

    items: list[BulletItem] = []
    bullet_sequence = 0
    cursor = start

    while cursor < end:
        next_hit = _next_bullet_start(tex_text, cursor, end)
        if next_hit is None:
            break

        macro_position, macro_kind = next_hit

        body_span = _resolve_body_span(
            tex_text=tex_text,
            macro_position=macro_position,
            macro_kind=macro_kind,
            range_end=end,
        )
        if body_span is None:
            # Malformed (unbalanced braces, off the end, etc.) — advance
            # past the macro so we don't loop forever and let the
            # validator report the underlying CONTRACT_UNBALANCED_BULLET.
            cursor = macro_position + 1
            continue

        body_start, body_end, advance_to = body_span
        body_text = tex_text[body_start:body_end]

        bullet_id_raw = f"{entry_id}_b{bullet_sequence}"
        items.append(
            BulletItem(
                id=bullet_id_raw[:MAX_ID_LENGTH],
                text=body_text,
                byte_start=body_start,
                byte_end=body_end,
            )
        )
        bullet_sequence += 1
        cursor = advance_to

    return items


def _next_bullet_start(
    tex_text: str, start: int, end: int
) -> tuple[int, str] | None:
    """Find the earliest bullet-starting macro within a range.

    Purpose:
        Scan `[start, end)` for the first of `\\resumeItem`,
        `\\cvline`, or `\\item` (whichever appears first) so the bullet
        extractor can dispatch the right body-span resolver.
    Args:
        tex_text: Full document text.
        start: Inclusive scan start.
        end: Exclusive scan end.
    Output:
        Tuple `(macro_position, macro_kind)` where `macro_kind` is one
        of `resume_item`, `cvline`, or `itemize_item`. Returns `None`
        when no bullet macros remain in the range.
    """

    candidates: list[tuple[int, str]] = []

    resume_item_match = RESUME_ITEM_RE.search(tex_text, start, end)
    if resume_item_match is not None:
        candidates.append((resume_item_match.start(), "resume_item"))

    cvline_match = CVLINE_RE.search(tex_text, start, end)
    if cvline_match is not None:
        candidates.append((cvline_match.start(), "cvline"))

    item_match = ITEM_RE.search(tex_text, start, end)
    if item_match is not None:
        candidates.append((item_match.start(), "itemize_item"))

    if not candidates:
        return None
    return min(candidates, key=lambda pair: pair[0])


def _resolve_body_span(
    *,
    tex_text: str,
    macro_position: int,
    macro_kind: str,
    range_end: int,
) -> tuple[int, int, int] | None:
    """Resolve the body byte span for one bullet macro.

    Purpose:
        Centralize the per-macro body-extraction rules from §2.3:
        balanced-brace for `\\resumeItem`, second-arg balanced-brace
        for `\\cvline`, and to-next-boundary for itemize `\\item`.
    Args:
        tex_text: Full document text.
        macro_position: Offset of the macro's leading backslash.
        macro_kind: One of `resume_item`, `cvline`, or `itemize_item`.
        range_end: Outer bound — body never extends past this.
    Output:
        Tuple `(body_start, body_end, advance_to)` of byte offsets, or
        `None` when the body is malformed (caller skips + advances).
    """

    if macro_kind == "resume_item":
        return _resolve_balanced_brace_body(
            tex_text=tex_text,
            macro_position=macro_position,
            arg_index=0,
            range_end=range_end,
        )
    if macro_kind == "cvline":
        return _resolve_balanced_brace_body(
            tex_text=tex_text,
            macro_position=macro_position,
            arg_index=1,
            range_end=range_end,
        )
    if macro_kind == "itemize_item":
        return _resolve_itemize_item_body(
            tex_text=tex_text,
            macro_position=macro_position,
            range_end=range_end,
        )
    return None


def _resolve_balanced_brace_body(
    *,
    tex_text: str,
    macro_position: int,
    arg_index: int,
    range_end: int,
) -> tuple[int, int, int] | None:
    """Resolve a body span for a balanced-brace macro at `macro_position`.

    Purpose:
        Walk forward from the macro, skipping over `arg_index` brace
        groups, and return the byte span of the target argument body.
        `arg_index=0` returns the first `{...}` body, `arg_index=1`
        skips one group and returns the second (`\\cvline` body case).
    Args:
        tex_text: Full document text.
        macro_position: Offset of the macro's leading backslash.
        arg_index: Zero-based index of the brace group whose body to
            return.
        range_end: Outer bound — body never extends past this.
    Output:
        `(body_start, body_end, advance_to)` or `None` when unbalanced.
    """

    cursor = macro_position
    target_open: int | None = None
    target_close: int | None = None

    # Skip past `arg_index` complete brace groups, then capture the
    # next one as the target body.
    for current_arg in range(arg_index + 1):
        open_brace = tex_text.find("{", cursor)
        if open_brace == -1 or open_brace >= range_end:
            return None
        close_brace = find_matching_brace(tex_text, open_brace)
        if close_brace is None or close_brace >= range_end:
            return None
        if current_arg == arg_index:
            target_open = open_brace
            target_close = close_brace
        cursor = close_brace + 1

    if target_open is None or target_close is None:
        return None

    body_start = target_open + 1
    body_end = target_close
    advance_to = target_close + 1
    return body_start, body_end, advance_to


# Macros that mark the boundary of an itemize `\item` body. Each entry
# is a literal LaTeX token; the regex below builds an alternation from
# them anchored at the next occurrence after the item's own position.
ITEM_BODY_BOUNDARY_TOKENS: tuple[str, ...] = (
    r"\item",
    r"\resumeItem",
    r"\cvline",
    r"\end{itemize}",
    r"\resumeItemListEnd",
    r"\resumeSubHeadingListEnd",
)

# Pre-compiled boundary scanner — escape each token, sort longest-first
# so `\resumeItem` is preferred over `\item` at the same position.
_BOUNDARY_RE: re.Pattern[str] = re.compile(
    "|".join(re.escape(tok) for tok in sorted(ITEM_BODY_BOUNDARY_TOKENS, key=len, reverse=True))
)


def _resolve_itemize_item_body(
    *,
    tex_text: str,
    macro_position: int,
    range_end: int,
) -> tuple[int, int, int] | None:
    """Resolve the body of one itemize `\\item` bullet.

    Purpose:
        Implement the §2.3 rule for `\\item`: body runs from the
        position right after the `\\item` token (skipping leading
        whitespace and an optional `{...}` group) to the next bullet
        or end-of-list boundary.
    Args:
        tex_text: Full document text.
        macro_position: Offset of the macro's leading backslash.
        range_end: Outer bound — body never extends past this.
    Output:
        `(body_start, body_end, advance_to)` or `None` when no useful
        body can be extracted before the next boundary.
    """

    body_start = macro_position + len("\\item")
    # Skip whitespace between `\item` and its content.
    while body_start < range_end and tex_text[body_start] in " \t":
        body_start += 1

    # Some templates wrap the bullet in `\item{...}` (the user's
    # dogfood resume's Skills section does this). Treat that as a
    # balanced-brace body when present.
    if body_start < range_end and tex_text[body_start] == "{":
        close_brace = find_matching_brace(tex_text, body_start)
        if close_brace is not None and close_brace < range_end:
            return body_start + 1, close_brace, close_brace + 1

    # Otherwise, scan forward for the next boundary token.
    boundary_match = _BOUNDARY_RE.search(tex_text, body_start + 1, range_end)
    if boundary_match is None:
        body_end = range_end
        advance_to = range_end
    else:
        body_end = boundary_match.start()
        advance_to = boundary_match.start()

    # Trim trailing whitespace so the recorded body is the visible text.
    while body_end > body_start and tex_text[body_end - 1] in " \t\n\r":
        body_end -= 1

    if body_end <= body_start:
        return None

    return body_start, body_end, advance_to


def _line_span_containing(tex_text: str, position: int) -> tuple[int, int]:
    """Return the `(line_start, line_end)` byte span enclosing `position`.

    Purpose:
        The entry-header dedupe step keys on line identity, so we need
        a cheap way to map an arbitrary offset to its enclosing line.
        `line_end` points at the trailing newline (exclusive) so
        `tex_text[line_start:line_end]` is the line content.
    Args:
        tex_text: Full document text.
        position: Any offset inside the target line.
    Output:
        Tuple `(line_start, line_end)`. `line_start` is `0` when the
        target line is the first; `line_end` is `len(tex_text)` when
        the target line is the last and has no trailing newline.
    """

    total_length = len(tex_text)
    if position > total_length:
        position = total_length

    line_start = tex_text.rfind("\n", 0, position) + 1
    next_newline = tex_text.find("\n", position)
    line_end = total_length if next_newline == -1 else next_newline
    return line_start, line_end


_SLUG_ALLOWED_RE: re.Pattern[str] = re.compile(r"[^a-z0-9]+")


def _build_entry_id(*, section_id: str, header_text: str, sequence: int) -> str:
    """Mint a stable entry identifier from header text + sequence.

    Purpose:
        Produce deterministic, human-readable entry IDs so the LLM can
        refer back to them. Same `.tex` → same IDs; not stable across
        edits to the resume (acceptable per §4.1 — IDs are only valid
        for the duration of one tailor run).
    Args:
        section_id: Enclosing section's ID, used as the prefix.
        header_text: Literal entry-header line, slugified into the ID.
        sequence: Zero-based entry index within the section, used as a
            tiebreaker for collisions and as a stable ordering hint.
    Output:
        Identifier string of the form
        `{section_id}_{first-words-slug}_{sequence}`, truncated to 64
        characters.
    """

    # Strip LaTeX macro tokens before slugifying so IDs don't contain
    # `textbf` / `hfill` noise that obscures the actual role text.
    stripped_text = re.sub(r"\\[A-Za-z]+", " ", header_text)
    lowercase_text = stripped_text.lower()
    words = lowercase_text.split()[:ENTRY_ID_SLUG_WORDS]
    slug_source = " ".join(words)
    slug = _SLUG_ALLOWED_RE.sub("_", slug_source).strip("_")
    if not slug:
        slug = "entry"
    candidate = f"{section_id}_{slug}_{sequence}"
    return candidate[:MAX_ENTRY_ID_LENGTH]


__all__ = ["build_bullet_manifest"]
