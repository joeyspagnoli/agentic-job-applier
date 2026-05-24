"""Shared brace-matching helper for locator + future patcher use.

Purpose:
    Provide a single balanced-brace walker that respects LaTeX
    backslash-escapes so callers (locator now, patcher in Phase 1) can
    extract `\\macro{...}` bodies even when the body contains nested
    `{...}` groups.

This duplicates `_find_matching_brace` from `latex_sanitize.py` to keep
Phase 0 from modifying that file. Phase 4 will delete the duplicate and
re-route the sanitizer through this module.
"""

from __future__ import annotations


def find_matching_brace(text: str, start: int) -> int | None:
    """Locate the closing `}` that balances the `{` at `start`.

    Purpose:
        Walk a `\\macro{...}` body whose argument may contain nested
        `{...}` groups, returning the index of the outer closing brace.
        LaTeX backslash-escaped braces (`\\{` and `\\}`) are skipped so
        they do not perturb the depth counter.
    Args:
        text: The full input text being walked.
        start: Index of the opening `{` to match. Callers are
            responsible for ensuring `text[start] == "{"`.
    Output:
        The index of the matching `}` when balanced, otherwise `None`
        to signal an unbalanced group (validator caller flags this).
    """

    # Track nesting depth so embedded `{...}` groups do not fool the
    # walker into closing the outer group prematurely.
    depth = 0
    index = start
    length = len(text)
    while index < length:
        current_char = text[index]
        # A backslash-escaped character is a literal — skip past the
        # pair so `\{` and `\}` do not shift the depth counter.
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


__all__ = ["find_matching_brace"]
