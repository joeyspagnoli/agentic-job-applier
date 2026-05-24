"""Tests for the simplified `latex_safe` (Phase 4 of #60).

Purpose:
    The Phase 4 sanitizer escapes only the five hard-break LaTeX-active
    characters (`&`, `%`, `$`, `#`, `_`) and leaves everything else —
    macros, braces, tildes, carets, backslashes — alone. The tailor
    prompt is the discipline ("copy macros verbatim"); the sanitizer
    is no longer a safety net for malformed LaTeX.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import settings as hypothesis_settings
from hypothesis import strategies as st

from src.agents.resume_tailor.latex_sanitize import latex_safe
from src.agents.resume_tailor.locator import build_bullet_manifest


# (input, expected_output, id). Each row pins one behavior the
# simplified contract from plan §3.6 / R1 must satisfy.
POLICY_CASES: list[tuple[str, str, str]] = [
    ("", "", "empty_string_in_empty_string_out"),
    ("plain text", "plain text", "plain_text_passes_through"),
    ("Q&A", "Q\\&A", "bare_ampersand_is_escaped"),
    ("20%", "20\\%", "bare_percent_is_escaped"),
    ("$5", "\\$5", "bare_dollar_is_escaped"),
    ("#tag", "\\#tag", "bare_hash_is_escaped"),
    ("under_score", "under\\_score", "bare_underscore_is_escaped"),
    (
        "a $ b # c _ d & e % f",
        "a \\$ b \\# c \\_ d \\& e \\% f",
        "all_bare_specials_are_escaped_in_one_pass",
    ),
    ("\\&", "\\&", "preescaped_ampersand_is_preserved"),
    ("\\%", "\\%", "preescaped_percent_is_preserved"),
    ("\\$", "\\$", "preescaped_dollar_is_preserved"),
    (
        "\\textbf{bold}",
        "\\textbf{bold}",
        "textbf_macro_survives_untouched",
    ),
    (
        "\\highlight{ML/AI}",
        "\\highlight{ML/AI}",
        "user_defined_macro_survives_untouched",
    ),
    (
        "{nested {braces}}",
        "{nested {braces}}",
        "raw_braces_are_left_alone",
    ),
    (
        "non-breaking~space",
        "non-breaking~space",
        "tilde_is_left_alone",
    ),
    (
        "exponent^2",
        "exponent^2",
        "caret_is_left_alone",
    ),
    (
        "line\\\\break",
        "line\\\\break",
        "double_backslash_is_left_alone",
    ),
    (
        "\\textbf{Reduced cost by 20\\%}",
        "\\textbf{Reduced cost by 20\\%}",
        "macro_with_preescaped_specials_survives",
    ),
    (
        "M&Ms cost $5 + 20% tax_inclusive",
        "M\\&Ms cost \\$5 + 20\\% tax\\_inclusive",
        "real_world_mixed_specials_escape_correctly",
    ),
]


@pytest.mark.parametrize(
    "raw_text, expected, _case_id",
    POLICY_CASES,
    ids=[case_id for _, _, case_id in POLICY_CASES],
)
def test_latex_safe_satisfies_policy_table(
    raw_text: str,
    expected: str,
    _case_id: str,
) -> None:
    assert latex_safe(raw_text) == expected


@pytest.mark.parametrize(
    "raw_text, _expected, _case_id",
    POLICY_CASES,
    ids=[case_id for _, _, case_id in POLICY_CASES],
)
def test_latex_safe_is_idempotent_on_policy_rows(
    raw_text: str,
    _expected: str,
    _case_id: str,
) -> None:
    once = latex_safe(raw_text)
    twice = latex_safe(once)

    assert once == twice


@given(arbitrary_text=st.text(max_size=200))
@hypothesis_settings(max_examples=200)
def test_latex_safe_is_idempotent_on_arbitrary_text(arbitrary_text: str) -> None:
    once = latex_safe(arbitrary_text)
    twice = latex_safe(once)

    assert once == twice


@given(arbitrary_text=st.text(max_size=200))
@hypothesis_settings(max_examples=200)
def test_latex_safe_output_contains_no_bare_specials(arbitrary_text: str) -> None:
    """After sanitizing, every special is either escaped or absent."""

    sanitized = latex_safe(arbitrary_text)

    # Walk the sanitized text; every special character must be preceded
    # by a backslash.
    for index, character in enumerate(sanitized):
        if character not in {"&", "%", "$", "#", "_"}:
            continue
        assert index > 0 and sanitized[index - 1] == "\\", (
            f"unescaped {character!r} at position {index} in {sanitized!r}"
        )


def test_dogfood_resume_tex_bullets_are_idempotent_under_sanitize() -> None:
    """Every bullet body in `config/resume.tex` round-trips through latex_safe.

    Purpose:
        The user's own resume should never produce sanitizer drift.
    """

    repo_root = Path(__file__).resolve().parents[3]
    resume_tex_path = repo_root / "config" / "resume.tex"
    tex_text = resume_tex_path.read_text(encoding="utf-8")
    manifest = build_bullet_manifest(tex_text)

    drift: list[tuple[str, str]] = []
    for section in manifest.sections:
        for entry in section.entries:
            for bullet in entry.bullets:
                sanitized = latex_safe(bullet.text)
                if sanitized != bullet.text:
                    drift.append((bullet.text, sanitized))

    assert drift == []
