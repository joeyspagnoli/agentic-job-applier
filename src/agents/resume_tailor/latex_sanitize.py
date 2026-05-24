"""Escape LaTeX-active characters in LLM-authored bullet replacement text.

Purpose:
    Phase 4 (#60) simplified the sanitizer to the bare minimum: escape
    only the five "hard-break" LaTeX-active characters (`&`, `%`, `$`,
    `#`, `_`) and leave everything else — including `\\foo{...}`
    macros, raw `{` / `}`, `~`, `^`, and `\\\\` — alone. The tailor
    prompt tells the LLM "copy any macros verbatim" so the previous
    emphasis-allowlist machinery is no longer load-bearing; if the LLM
    ignores that instruction and emits an unknown `\\macro{...}`,
    tectonic will fail to compile and the pipeline ships the base PDF
    via the existing failure path.

The function remains idempotent — already-escaped sequences pass
through unchanged.
"""

from __future__ import annotations

# Characters LaTeX treats as active and that must appear as `\<char>`
# inside running text to render literally.
ESCAPABLE_SPECIALS: frozenset[str] = frozenset({"&", "%", "$", "#", "_"})


def latex_safe(text: str) -> str:
    """Escape the five LaTeX-active characters in `text`.

    Purpose:
        Stop tailored bullets from breaking the tectonic compile when
        the LLM emits a bare `&` / `%` / `$` / `#` / `_`. Pre-escaped
        sequences (`\\&`, `\\%`, ...) are recognized so a second pass
        produces the same output as the first.
    Args:
        text: Raw bullet replacement text emitted by the tailor LLM.
    Output:
        The same content with bare specials rewritten as `\\<char>`.
        Returns the empty string when `text` is empty.
    """

    if not text:
        return ""

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

        if current_char in ESCAPABLE_SPECIALS:
            output_fragments.append(f"\\{current_char}")
            index += 1
            continue

        output_fragments.append(current_char)
        index += 1

    return "".join(output_fragments)


__all__ = ["latex_safe"]
