"""Tests for `src/agents/resume_tailor/latex_sanitize.py` (issue #54).

Purpose:
    Lock down the `latex_safe` policy from issue #54 so a tailored bullet
    containing bare LaTeX-active characters, unknown control sequences,
    or unbalanced emphasis braces can no longer abort the `latexmk`
    compile. Coverage is layered: a parametrized table of the policy
    rows, two Hypothesis properties, and a round-trip check against the
    real `config/resume_content.yaml` so the load-bearing
    `\\textbf{20\\%}`-style markup keeps surviving sanitization.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import settings
from hypothesis import strategies as st

from src.agents.resume_tailor.latex_sanitize import latex_safe
from src.agents.resume_tailor.yaml_io import load_resume_yaml


# Policy table from issue #54, expressed as (input, expected_output, id).
# Every entry corresponds to one row in the docstring decision table for
# `latex_safe` — keep these in sync if the contract ever changes.
POLICY_CASES: list[tuple[str, str, str]] = [
    ("", "", "empty_string_in_empty_string_out"),
    ("plain text", "plain text", "plain_text_passes_through"),
    ("Q&A", "Q\\&A", "bare_ampersand_is_escaped"),
    ("20%", "20\\%", "bare_percent_is_escaped"),
    (
        "a $ b # c _ d",
        "a \\$ b \\# c \\_ d",
        "all_bare_specials_are_escaped_in_one_pass",
    ),
    ("\\&", "\\&", "preescaped_ampersand_is_preserved"),
    ("\\%", "\\%", "preescaped_percent_is_preserved"),
    (
        "\\textbf{20\\%}",
        "\\textbf{20\\%}",
        "load_bearing_textbf_with_preescaped_percent",
    ),
    ("\\textbf{X}", "\\textbf{X}", "wellformed_textbf_is_preserved"),
    ("\\textit{Y}", "\\textit{Y}", "wellformed_textit_is_preserved"),
    ("\\textbf{}", "", "empty_textbf_arg_drops_entirely"),
    ("\\textbf{X", "X", "unbalanced_textbf_strips_wrapper_and_keeps_tail"),
    (
        "\\textbf{X \\textit{Y}}",
        "\\textbf{X \\textit{Y}}",
        "nested_emphasis_round_trips",
    ),
    (
        "\\textbf{Q&A}",
        "\\textbf{Q\\&A}",
        "textbf_inner_argument_is_sanitized_recursively",
    ),
    ("\\ETC", "ETC", "unknown_command_strips_backslash_keeps_word"),
    (
        "\\alpha rocks",
        "alpha rocks",
        "unknown_command_in_running_text_strips_backslash",
    ),
    (
        "tools th\\ETC.",
        "tools thETC.",
        "issue_54_op_failure_case_compiles_to_text",
    ),
    ("\\\\", "", "double_backslash_line_break_is_stripped"),
    ("end\\\\", "end", "trailing_double_backslash_is_stripped"),
    ("end\\", "end", "trailing_lone_backslash_is_stripped"),
    ("~", "\\textasciitilde{}", "bare_tilde_becomes_glyph_macro"),
    ("^", "\\textasciicircum{}", "bare_caret_becomes_glyph_macro"),
    (
        "\\textasciitilde{}",
        "\\textasciitilde{}",
        "glyph_macro_textasciitilde_is_idempotent",
    ),
    (
        "\\textasciicircum{}",
        "\\textasciicircum{}",
        "glyph_macro_textasciicircum_is_idempotent",
    ),
    ("{x}", "\\{x\\}", "bare_braces_are_escaped"),
    ("\\{x\\}", "\\{x\\}", "preescaped_braces_are_preserved"),
]


@pytest.mark.parametrize(
    ("raw_input", "expected_output"),
    [(raw, expected) for raw, expected, _ in POLICY_CASES],
    ids=[case_id for _, _, case_id in POLICY_CASES],
)
def test_latex_safe_matches_policy_table(
    raw_input: str,
    expected_output: str,
) -> None:
    """Every row of the issue #54 policy table maps input to expected output."""

    # Arrange / Act
    sanitized_text = latex_safe(raw_input)

    # Assert
    assert sanitized_text == expected_output


@given(st.text(max_size=200))
@settings(max_examples=200)
def test_latex_safe_is_idempotent(arbitrary_text: str) -> None:
    """Property: running the sanitizer twice equals running it once."""

    sanitized_once = latex_safe(arbitrary_text)
    sanitized_twice = latex_safe(sanitized_once)

    assert sanitized_once == sanitized_twice


# Regex that matches every backslash-prefixed token in sanitizer output.
# Group 1 captures the command word (alphabetic) when present so we can
# check it against the allowlist; group 2 captures a single special
# character (`&%$#_{}`) so we can confirm only those forms appear escaped.
SANITIZER_OUTPUT_BACKSLASH_PATTERN = re.compile(r"\\([A-Za-z]+)|\\([&%$#_{}])")

# Commands that may legally appear in sanitizer output. Anything outside
# this set means an unknown control sequence leaked through.
ALLOWED_OUTPUT_COMMANDS: frozenset[str] = frozenset(
    {"textbf", "textit", "textasciitilde", "textasciicircum"}
)


@given(st.text(max_size=200))
@settings(max_examples=200)
def test_latex_safe_output_only_contains_allowed_backslash_tokens(
    arbitrary_text: str,
) -> None:
    """Property: every `\\<word>` in the output is on the allowlist."""

    sanitized_text = latex_safe(arbitrary_text)

    leaked_commands = [
        match.group(1)
        for match in SANITIZER_OUTPUT_BACKSLASH_PATTERN.finditer(sanitized_text)
        if match.group(1) is not None and match.group(1) not in ALLOWED_OUTPUT_COMMANDS
    ]

    assert leaked_commands == []


# Characters that LaTeX treats as active and that must NEVER appear bare
# in sanitizer output. `\` is excluded because every `\` in the output is
# part of an allowed escape or command (validated by the previous test).
BARE_ACTIVE_CHARACTERS: tuple[str, ...] = ("~", "^")


@pytest.mark.parametrize("forbidden_character", BARE_ACTIVE_CHARACTERS)
@given(st.text(max_size=200))
@settings(max_examples=100)
def test_latex_safe_output_never_contains_bare_tilde_or_caret(
    forbidden_character: str,
    arbitrary_text: str,
) -> None:
    """Property: `~` and `^` are always rewritten to glyph macros."""

    sanitized_text = latex_safe(arbitrary_text)

    assert forbidden_character not in sanitized_text


def test_base_resume_yaml_bullets_are_idempotent_under_sanitize() -> None:
    """Every bullet in the real `config/resume_content.yaml` round-trips."""

    repo_root = Path(__file__).resolve().parents[3]
    base_yaml_path = repo_root / "config" / "resume_content.yaml"
    resume_content = load_resume_yaml(base_yaml_path)

    rewritten_bullets: list[tuple[str, str]] = []
    for experience_listing in resume_content.experience.listings:
        for bullet in experience_listing.bullets:
            sanitized_text = latex_safe(bullet.text)
            if sanitized_text != bullet.text:
                rewritten_bullets.append((bullet.text, sanitized_text))
    for project_listing in resume_content.projects.listings:
        for bullet in project_listing.bullets:
            sanitized_text = latex_safe(bullet.text)
            if sanitized_text != bullet.text:
                rewritten_bullets.append((bullet.text, sanitized_text))
    for skill_listing in resume_content.skills_achievements.listings:
        sanitized_text = latex_safe(skill_listing.text)
        if sanitized_text != skill_listing.text:
            rewritten_bullets.append((skill_listing.text, sanitized_text))

    assert rewritten_bullets == []
