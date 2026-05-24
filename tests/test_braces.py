"""Behavior + property tests for `src.agents.resume_tailor._braces`.

Purpose:
    Pin the balanced-brace walker's contract: it locates the matching
    `}` for any well-formed input, returns `None` (never raises, never
    hangs) on malformed input, and respects LaTeX `\\{` / `\\}` escapes
    so the depth counter does not drift.

These tests cover Risk Area #1 from the Phase 0 handoff
(`/tmp/testing-handoff-phase-0.md`): the helper is a cognitive-complexity
hot spot shared by the locator and the (future) patcher.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from src.agents.resume_tailor._braces import find_matching_brace


# ---------------------------------------------------------------------------
# Unit tests — explicit fixtures for each branch of the contract
# ---------------------------------------------------------------------------


def test_returns_index_of_matching_brace_for_flat_group() -> None:
    """Risk #1 — flat `{...}` body returns its closing-brace offset."""

    text = "before {payload} after"
    open_index = text.index("{")

    result = find_matching_brace(text, open_index)

    assert result == text.index("}")


def test_handles_nested_braces_without_closing_at_inner_brace() -> None:
    """Risk #1 — nested `{...}` groups must not close the outer prematurely."""

    text = r"\textbf{outer {inner} tail}"
    open_index = text.index("{")

    result = find_matching_brace(text, open_index)

    assert result == len(text) - 1
    assert text[result] == "}"


def test_skips_backslash_escaped_opening_brace() -> None:
    """Risk #1 — `\\{` must not increment the depth counter.

    Without escape handling, the inner `\\{` would push depth to 2 and
    the lone closing `}` would only bring depth back to 1, leaving the
    group unbalanced. With escape handling, depth stays at 1 and the
    single `}` closes the outer group cleanly.
    """

    text = r"{outer \{ unmatched-by-design close}"
    open_index = 0

    result = find_matching_brace(text, open_index)

    assert result == len(text) - 1
    assert text[result] == "}"


def test_skips_backslash_escaped_closing_brace() -> None:
    """Risk #1 — `\\}` must not decrement the depth counter."""

    text = r"{body with \} escape then real close}"
    open_index = 0

    result = find_matching_brace(text, open_index)

    assert result == len(text) - 1


def test_returns_none_for_unbalanced_body_with_no_closing_brace() -> None:
    """Risk #1 — missing `}` returns `None`, never raises, never hangs."""

    text = r"{open with no close \resumeItem more"
    open_index = 0

    result = find_matching_brace(text, open_index)

    assert result is None


def test_returns_none_when_string_runs_out_mid_escape() -> None:
    """Risk #1 — trailing `\\` at end-of-string must not raise."""

    text = "{body\\"
    open_index = 0

    result = find_matching_brace(text, open_index)

    assert result is None


def test_handles_empty_braces() -> None:
    """An empty `{}` group is a degenerate but valid case."""

    text = "{}"
    open_index = 0

    result = find_matching_brace(text, open_index)

    assert result == 1


def test_handles_multiple_groups_only_balances_the_indicated_one() -> None:
    """Starting at the first `{` returns that group's `}`, not a later one."""

    text = "{first}{second}"
    first_open = 0

    result = find_matching_brace(text, first_open)

    assert result == text.index("}")
    # The walker must NOT walk past the first group into the second.
    assert text[result + 1] == "{"


def test_handles_consecutive_escaped_brace_pairs() -> None:
    """`\\{\\}` repeated runs of escapes leave depth unchanged."""

    text = r"{\{\}\{\} tail}"
    open_index = 0

    result = find_matching_brace(text, open_index)

    assert result == len(text) - 1


def test_handles_double_backslash_then_brace() -> None:
    """`\\\\{...}` — `\\\\` is escaped backslash; the following `{` IS literal."""

    # In our walker, `\\` skips the next char regardless: `\\` consumes
    # the second `\`, then the next iteration sees `{` and opens a
    # group. That matches LaTeX semantics for a literal `\` followed by
    # a real brace group.
    text = r"{prefix \\{inner} tail}"
    open_index = 0

    result = find_matching_brace(text, open_index)

    assert result == len(text) - 1


# ---------------------------------------------------------------------------
# Property-based tests — Hypothesis generates 100+ random shapes per run
# ---------------------------------------------------------------------------


@st.composite
def _balanced_brace_text(draw: st.DrawFn) -> tuple[str, int]:
    """Generate a string that contains a known-balanced `{...}` group.

    Purpose:
        Produce arbitrary text whose brace pairs are statically known to
        be balanced so the property test can assert the walker locates
        the outer close.
    Args:
        draw: Hypothesis draw callback.
    Output:
        `(text, open_index)` where `text[open_index] == "{"` and the
        group rooted there is balanced.
    """

    # Build a payload from non-brace, non-backslash characters plus
    # nested balanced groups. The recursive strategy guarantees balance.
    payload = draw(
        st.recursive(
            st.text(
                alphabet=st.characters(
                    blacklist_characters="{}\\",
                    blacklist_categories=["Cs"],
                ),
                max_size=10,
            ),
            lambda children: st.lists(children, max_size=3).map(
                lambda parts: "{" + "".join(parts) + "}"
            ),
            max_leaves=8,
        )
    )

    prefix = draw(
        st.text(
            alphabet=st.characters(
                blacklist_characters="{}\\",
                blacklist_categories=["Cs"],
            ),
            max_size=5,
        )
    )
    suffix = draw(
        st.text(
            alphabet=st.characters(
                blacklist_characters="{}\\",
                blacklist_categories=["Cs"],
            ),
            max_size=5,
        )
    )

    full_text = f"{prefix}{{{payload}}}{suffix}"
    open_index = len(prefix)
    return full_text, open_index


@given(_balanced_brace_text())
@settings(max_examples=200)
def test_property_find_matching_brace_returns_balanced_index(
    text_and_index: tuple[str, int],
) -> None:
    """Risk #1 — for any balanced input, the slice between open/close balances."""

    text, open_index = text_and_index

    result = find_matching_brace(text, open_index)

    assert result is not None
    assert text[result] == "}"
    # The substring (inclusive of both braces) must be a balanced group.
    # We re-count by walking and respecting escapes — same rule the
    # function should encode.
    substring = text[open_index : result + 1]
    depth = 0
    cursor = 0
    while cursor < len(substring):
        char = substring[cursor]
        if char == "\\" and cursor + 1 < len(substring):
            cursor += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        cursor += 1
    assert depth == 0


@given(st.text(max_size=200))
@settings(max_examples=500)
def test_property_find_matching_brace_never_raises_on_arbitrary_input(
    text: str,
) -> None:
    """Risk #1 — walker must never raise, regardless of input shape."""

    # Always start at index 0 — if the char isn't `{` the function's
    # contract still says "return None or an int, never raise".
    result = find_matching_brace(text, 0)

    assert result is None or isinstance(result, int)


@given(
    st.text(
        alphabet=st.characters(
            blacklist_characters="{}\\",
            blacklist_categories=["Cs"],
        ),
        min_size=0,
        max_size=50,
    )
)
@settings(max_examples=200)
def test_property_escapes_inside_body_do_not_perturb_match(payload: str) -> None:
    """Risk #1 — embedding `\\{` and `\\}` keeps the outer match stable."""

    # Wrap the payload with escaped brace literals on both sides; the
    # outer `{...}` should still match end-to-end.
    text = "{" + r"\{" + payload + r"\}" + "}"

    result = find_matching_brace(text, 0)

    assert result == len(text) - 1
