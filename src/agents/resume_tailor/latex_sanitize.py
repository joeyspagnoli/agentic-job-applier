"""Escape LaTeX-active characters in LLM-authored bullet replacement text.

Purpose:
    The sanitizer escapes only the five "hard-break" LaTeX-active
    characters (`&`, `%`, `$`, `#`, `_`) and leaves everything else —
    including `\\foo{...}` macros, raw `{` / `}`, `~`, `^`, and
    `\\\\` — alone. The tailor prompt instructs the LLM to "copy any
    macros verbatim" so the previous emphasis-allowlist machinery is no
    longer load-bearing; if the LLM ignores that instruction and emits
    an unknown `\\macro{...}`, tectonic will fail to compile and the
    pipeline ships the base PDF via the existing failure path.

`$` has dual meaning in LaTeX — literal currency *and* math-mode
delimiter (`$R^2$`, `$O(n)$`). Eagerly escaping every `$` breaks math
mode: the contents (`^`, `_`) become invalid outside math mode and
tectonic aborts with "Missing $ inserted". We therefore treat `$`
pairwise — an even count of unescaped `$` in the bullet is assumed to
be math-mode delimiters and passes through; an odd count is treated as
a stray literal and every bare `$` is escaped.

The function remains idempotent — already-escaped sequences pass
through unchanged.
"""

from __future__ import annotations

# Characters LaTeX treats as active and that must appear as `\<char>`
# inside running text to render literally. `$` is in this set so the
# idempotency check still recognizes `\$`, but it is handled apart
# from the others (see module docstring) because of its dual meaning.
ESCAPABLE_SPECIALS: frozenset[str] = frozenset({"&", "%", "$", "#", "_"})
_ALWAYS_ESCAPE: frozenset[str] = ESCAPABLE_SPECIALS - {"$"}


def _count_unescaped_dollars(text: str) -> int:
    count = 0
    index = 0
    length = len(text)
    while index < length:
        if (
            text[index] == "\\"
            and index + 1 < length
            and text[index + 1] == "$"
        ):
            index += 2
            continue
        if text[index] == "$":
            count += 1
        index += 1
    return count


def latex_safe(text: str) -> str:
    """Escape the five LaTeX-active characters in `text`.

    Purpose:
        Stop tailored bullets from breaking the tectonic compile when
        the LLM emits a bare `&` / `%` / `$` / `#` / `_`. Pre-escaped
        sequences (`\\&`, `\\%`, ...) are recognized so a second pass
        produces the same output as the first. Balanced `$...$` math
        mode is preserved (see module docstring).
    Args:
        text: Raw bullet replacement text emitted by the tailor LLM.
    Output:
        The same content with bare specials rewritten as `\\<char>`.
        Returns the empty string when `text` is empty.
    """

    if not text:
        return ""

    unescaped_dollars = _count_unescaped_dollars(text)
    dollars_are_paired = unescaped_dollars > 0 and unescaped_dollars % 2 == 0

    output_fragments: list[str] = []
    index = 0
    length = len(text)

    while index < length:
        current_char = text[index]

        # Pre-escaped special — pass through verbatim so the function
        # stays idempotent on its own output.
        if (
            current_char == "\\"
            and index + 1 < length
            and text[index + 1] in ESCAPABLE_SPECIALS
        ):
            output_fragments.append(text[index : index + 2])
            index += 2
            continue

        if current_char == "$":
            output_fragments.append("$" if dollars_are_paired else "\\$")
            index += 1
            continue

        if current_char in _ALWAYS_ESCAPE:
            output_fragments.append(f"\\{current_char}")
            index += 1
            continue

        output_fragments.append(current_char)
        index += 1

    return "".join(output_fragments)


__all__ = ["latex_safe"]
