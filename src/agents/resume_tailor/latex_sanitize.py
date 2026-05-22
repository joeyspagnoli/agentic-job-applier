"""Sanitize tailored bullet text so it compiles inside a `.tex` template.

Purpose:
    Convert raw LLM-authored bullet/skill-row text into LaTeX-safe text by
    escaping bare special characters, preserving an allowlist of well-formed
    emphasis/glyph commands, and stripping unknown control sequences that
    would otherwise abort the `latexmk` compile (see issue #54).

The policy is intentionally selective rather than a blanket escape:
    - Pre-escaped specials (`\\&`, `\\%`, ...) are kept as-is so the base
      YAML's `\\textbf{20\\%}` round-trips unchanged.
    - `\\textbf{X}` / `\\textit{X}` are kept (the renderer descends into the
      argument and re-sanitizes it) so legitimate emphasis markup survives.
    - Bare LaTeX-active characters become their escaped form.
    - Unknown backslash commands (`\\ETC`, `\\alpha`, ...) — the failure mode
      from issue #54 — have the backslash stripped so the word-residue
      remains as plain text.

The sanitizer is idempotent: running it twice on any input produces the
same output as running it once, which is enforced by a property test.
"""

from __future__ import annotations

# Commands that wrap a non-empty argument. Empty arguments collapse to
# nothing because an emphasis wrapper with no content is meaningless.
EMPHASIS_COMMANDS: frozenset[str] = frozenset({"textbf", "textit"})

# Commands that produce a single glyph and conventionally take an empty
# `{}` group. Only used to preserve idempotency on the output of this
# sanitizer (the LLM contract never asks for these directly).
GLYPH_COMMANDS: frozenset[str] = frozenset({"textasciitilde", "textasciicircum"})

# Characters that LaTeX treats as active and that must appear as `\<char>`
# inside running text to render literally.
ESCAPABLE_SPECIALS: frozenset[str] = frozenset({"&", "%", "$", "#", "_", "{", "}"})


def _find_matching_brace(text: str, start: int) -> int | None:
    """Locate the closing `}` that balances the `{` at `start`.

    Purpose:
        Support brace-aware command parsing so nested emphasis like
        `\\textbf{X \\textit{Y}}` is detected as a single balanced group
        rather than two unbalanced ones.

    Args:
        text: The full input text being walked.
        start: Index of the opening `{` to match. The caller is
            responsible for ensuring `text[start] == "{"`.

    Returns:
        The index of the matching `}` if one exists, otherwise `None` to
        signal that the group is unbalanced and the caller should treat
        the command as malformed.
    """

    # Track nesting depth so embedded `{...}` groups don't fool us into
    # closing the outer group early.
    depth = 0
    index = start
    length = len(text)
    while index < length:
        current_char = text[index]
        # A backslash-escaped character is a literal — skip past the pair
        # so `\{` and `\}` don't shift the depth counter.
        if current_char == "\\" and index + 1 < length:
            index += 2
            continue
        if current_char == "{":
            depth += 1
        elif current_char == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def _emit_emphasis_command(
    text: str,
    command: str,
    command_end_index: int,
) -> tuple[str, int]:
    """Render one occurrence of `\\textbf{...}` or `\\textit{...}`.

    Purpose:
        Handle the three emphasis cases from the issue #54 policy table —
        well-formed (recurse), empty argument (drop), and unbalanced
        (strip wrapper and sanitize the trailing tail).

    Args:
        text: The full input text.
        command: The bare command name (`"textbf"` or `"textit"`), already
            stripped of its leading backslash.
        command_end_index: Index immediately after the command word —
            where we expect to see an opening `{`.

    Returns:
        A `(emitted_fragment, next_index)` pair. `emitted_fragment` is the
        sanitized text to append to the output; `next_index` is the
        position in `text` to resume the outer scan from. When the group
        is unbalanced the function consumes the entire remaining input
        and returns the input length as `next_index`.
    """

    length = len(text)

    # No brace follows: the LLM produced a bare `\textbf` with no arg.
    # Strip the backslash and keep the word as plain text — a permissive
    # recovery so we don't lose content.
    if command_end_index >= length or text[command_end_index] != "{":
        return command, command_end_index

    closing_index = _find_matching_brace(text, command_end_index)
    if closing_index is None:
        # Unbalanced: strip the `\<cmd>{` prefix and sanitize whatever
        # follows. Consume the rest of the input since there is no
        # well-defined boundary for the outer scan to resume from.
        inner_tail = text[command_end_index + 1 :]
        return latex_safe(inner_tail), length

    inner_content = text[command_end_index + 1 : closing_index]
    sanitized_inner = latex_safe(inner_content)
    if sanitized_inner == "":
        # Empty emphasis wrapper carries no content; drop the whole thing
        # rather than emit `\textbf{}` which compiles to nothing visible.
        return "", closing_index + 1

    return f"\\{command}{{{sanitized_inner}}}", closing_index + 1


def _emit_glyph_command(
    text: str,
    command: str,
    command_end_index: int,
) -> tuple[str, int]:
    """Render one occurrence of a glyph-producing command like `\\textasciitilde`.

    Purpose:
        Keep the sanitizer idempotent on its own output by recognizing the
        `\\textasciitilde{}` / `\\textasciicircum{}` sequences we emit for
        bare `~` and `^` and passing them through unchanged.

    Args:
        text: The full input text.
        command: The bare command name without its leading backslash.
        command_end_index: Index immediately after the command word.

    Returns:
        A `(emitted_fragment, next_index)` pair. The fragment is always
        `\\<command>{}`; the index advances past any following balanced
        brace group (typically empty) so a caller-supplied `{}` is
        consumed rather than re-escaped on the next iteration.
    """

    length = len(text)
    emitted_fragment = f"\\{command}{{}}"

    # Skip over an optional following `{...}` group so the empty braces
    # we conventionally emit aren't re-processed as bare active chars.
    if command_end_index < length and text[command_end_index] == "{":
        closing_index = _find_matching_brace(text, command_end_index)
        if closing_index is not None:
            return emitted_fragment, closing_index + 1
        return emitted_fragment, command_end_index

    return emitted_fragment, command_end_index


def _emit_backslash_sequence(text: str, index: int) -> tuple[str, int]:
    """Render one backslash-prefixed token starting at `index`.

    Purpose:
        Centralize the dispatch logic for everything that begins with `\\`
        — pre-escaped specials, allowed commands, unknown commands, the
        `\\\\` line-break, and a trailing lone backslash.

    Args:
        text: The full input text.
        index: Position of the `\\` character to process.

    Returns:
        A `(emitted_fragment, next_index)` pair. For unknown commands the
        backslash is dropped and the word is kept as plain text. For
        `\\\\` and trailing `\\` the fragment is empty.
    """

    length = len(text)

    # Trailing backslash with nothing after it: drop, since it cannot
    # form a valid LaTeX sequence.
    if index + 1 >= length:
        return "", index + 1

    next_char = text[index + 1]

    # `\\` — LaTeX hard line break. Strip per policy; the LLM contract
    # forbids it and we don't want surprise line breaks inside a bullet.
    if next_char == "\\":
        return "", index + 2

    # Pre-escaped LaTeX special: pass through verbatim so `\&`, `\%`,
    # etc. survive a second sanitizer pass unchanged.
    if next_char in ESCAPABLE_SPECIALS:
        return text[index : index + 2], index + 2

    # `\<word>` — read the alphabetic command name and dispatch by
    # whether it's on the emphasis, glyph, or unknown list.
    if next_char.isalpha():
        word_end = index + 1
        while word_end < length and text[word_end].isalpha():
            word_end += 1
        command = text[index + 1 : word_end]

        if command in EMPHASIS_COMMANDS:
            return _emit_emphasis_command(text, command, word_end)
        if command in GLYPH_COMMANDS:
            return _emit_glyph_command(text, command, word_end)

        # Unknown command (`\ETC`, `\alpha`, ...): strip the backslash so
        # the word-residue remains as plain text. This is the OP failure
        # case from issue #54.
        return command, word_end

    # Backslash followed by something else (digit, punctuation): drop the
    # backslash and let the outer loop re-examine the next character.
    return "", index + 1


def latex_safe(text: str) -> str:
    """Sanitize raw LLM bullet text into LaTeX-safe text.

    Purpose:
        Stop tailored bullets containing unbalanced braces or unknown
        control sequences (`\\ETC`, em-dashes, ampersands, etc.) from
        crashing `latexmk` when injected into a `\\resumeItem{...}` slot.

    The function is idempotent — `latex_safe(latex_safe(x)) ==
    latex_safe(x)` for every input — so it is safe to apply repeatedly.

    Args:
        text: Raw bullet, skill-row, or other LLM-authored text.

    Returns:
        The same content rewritten so every LaTeX-active character is
        either escaped or part of an allowed `\\textbf` / `\\textit` /
        `\\textasciitilde` / `\\textasciicircum` group.
    """

    if not text:
        return ""

    output_fragments: list[str] = []
    index = 0
    length = len(text)

    while index < length:
        current_char = text[index]

        if current_char == "\\":
            emitted_fragment, next_index = _emit_backslash_sequence(text, index)
            output_fragments.append(emitted_fragment)
            index = next_index
            continue

        # `~` is LaTeX's non-breaking space; the literal tilde glyph is
        # `\textasciitilde{}`. Same story for `^` and `\textasciicircum{}`.
        if current_char == "~":
            output_fragments.append("\\textasciitilde{}")
            index += 1
            continue
        if current_char == "^":
            output_fragments.append("\\textasciicircum{}")
            index += 1
            continue

        if current_char in ESCAPABLE_SPECIALS:
            output_fragments.append(f"\\{current_char}")
            index += 1
            continue

        output_fragments.append(current_char)
        index += 1

    return "".join(output_fragments)


__all__ = ["latex_safe"]
