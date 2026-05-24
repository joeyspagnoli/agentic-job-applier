"""Unicode round-trip and golden-manifest tests for the locator.

Purpose:
    Cover Risk Area #4 (multibyte character round-tripping — `byte_start`/
    `byte_end` are Python str indices despite the name, so the patcher
    must be able to splice via them for any unicode payload), and pin
    canonical manifest JSON for the two reference fixtures so future
    regressions surface as snapshot diffs.

The golden manifests live in `tests/fixtures/manifests/`. Regenerate
them only when the manifest schema or locator behavior intentionally
changes:

    uv run python -c "from src.agents.resume_tailor.locator import \\
        build_bullet_manifest; from pathlib import Path; import json; \\
        ..."
"""

from __future__ import annotations

import json
from pathlib import Path

import pydantic
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from src.agents.resume_tailor.locator import build_bullet_manifest
from src.agents.resume_tailor.manifest import BulletManifest

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "resumes"
MANIFESTS_DIR = Path(__file__).parent / "fixtures" / "manifests"


def _read_fixture(name: str) -> str:
    """Load a `.tex` fixture from `tests/fixtures/resumes/`."""

    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Risk #4 — multibyte character round-trip via byte offsets
# ---------------------------------------------------------------------------


def test_dogfood_resume_round_trips_existing_unicode_glyphs() -> None:
    """Risk #4 — the dogfood resume contains `²` and `–`; bullets still round-trip."""

    tex = _read_fixture("dogfood_user.tex")
    manifest = build_bullet_manifest(tex)

    # Confirm the corpus actually contains the multibyte glyphs we want
    # to exercise — otherwise the round-trip assertion would be vacuous.
    assert any(ch in tex for ch in ("²", "–", "—")), (
        "Dogfood fixture lost its multibyte glyphs — update the test or "
        "the fixture."
    )

    for section in manifest.sections:
        for entry in section.entries:
            for bullet in entry.bullets:
                assert tex[bullet.byte_start : bullet.byte_end] == bullet.text


@given(
    st.text(
        alphabet=st.characters(
            min_codepoint=0x20,
            max_codepoint=0xFFFF,
            blacklist_characters="{}\\%",
            blacklist_categories=["Cs", "Cc"],
        ),
        min_size=1,
        max_size=80,
    )
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_property_arbitrary_unicode_bullet_bodies_round_trip(
    payload: str,
) -> None:
    """Risk #4 — for any unicode payload, byte_start/byte_end round-trip exactly.

    Builds a minimal valid `.tex` with a single `\\resumeItem{<payload>}`
    bullet and confirms that `tex[byte_start:byte_end] == bullet.text`
    no matter what unicode payload Hypothesis generates.
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
        "      \\resumeItem{"
        + payload
        + "}\n"
        "    \\end{itemize}\n"
        "\\end{itemize}\n"
        "\\end{document}\n"
    )

    manifest = build_bullet_manifest(tex)
    bullets = [
        bullet
        for section in manifest.sections
        for entry in section.entries
        for bullet in entry.bullets
    ]

    assert len(bullets) == 1
    bullet = bullets[0]
    assert tex[bullet.byte_start : bullet.byte_end] == bullet.text
    assert bullet.text == payload


def test_header_byte_start_points_at_literal_role_context_for_unicode_headers() -> None:
    """Risk #4 — `header_byte_start` lines up with the literal entry line, glyphs and all."""

    tex = (
        "\\documentclass{article}\n"
        "\\newcommand{\\resumeItem}[1]{\\item #1}\n"
        "\\newcommand{\\resumeSubheading}[4]"
        "{\\item \\textbf{#1} \\hfill \\textbf{#2}\\\\#3\\hfill#4}\n"
        "\\begin{document}\n"
        "\\section{Experience}\n"
        "\\begin{itemize}\n"
        "  \\resumeSubheading{Ingeniería Sénior}{2024 — Présent}{Café Co}{París}\n"
        "    \\begin{itemize}\\resumeItem{Built things.}\\end{itemize}\n"
        "\\end{itemize}\n"
        "\\end{document}\n"
    )

    manifest = build_bullet_manifest(tex)

    entry = manifest.sections[0].entries[0]
    line_end = tex.find("\n", entry.header_byte_start)
    line_end = len(tex) if line_end == -1 else line_end
    literal_line = tex[entry.header_byte_start:line_end].strip()
    assert entry.role_context == literal_line
    # And the literal must contain the unicode glyphs (sanity check that
    # the round-trip is doing real work).
    assert "í" in entry.role_context


# ---------------------------------------------------------------------------
# Golden manifest snapshots — regression catch for serialization drift
# ---------------------------------------------------------------------------


def _load_golden(name: str) -> dict[str, object]:
    """Load a pinned manifest JSON snapshot from `tests/fixtures/manifests/`."""

    raw_text = (MANIFESTS_DIR / name).read_text(encoding="utf-8")
    parsed: dict[str, object] = json.loads(raw_text)
    return parsed


def test_synthetic_minimal_manifest_matches_golden_snapshot() -> None:
    """Pin the synthetic_minimal manifest to its golden JSON file."""

    tex = _read_fixture("synthetic_minimal.tex")
    manifest = build_bullet_manifest(tex)

    actual = manifest.model_dump(mode="json")
    expected = _load_golden("synthetic_minimal.manifest.json")

    assert actual == expected


def test_dogfood_user_manifest_matches_golden_snapshot() -> None:
    """Pin the dogfood user manifest to its golden JSON file."""

    tex = _read_fixture("dogfood_user.tex")
    manifest = build_bullet_manifest(tex)

    actual = manifest.model_dump(mode="json")
    expected = _load_golden("dogfood_user.manifest.json")

    assert actual == expected


# ---------------------------------------------------------------------------
# Determinism — extended from the existing 2-run pin to 10 runs
# ---------------------------------------------------------------------------


def test_locator_is_deterministic_across_ten_runs() -> None:
    """Per handoff: extend the existing 2-run determinism pin to 10 runs."""

    tex = _read_fixture("dogfood_user.tex")
    baseline = build_bullet_manifest(tex).model_dump_json()

    repeats = [build_bullet_manifest(tex).model_dump_json() for _ in range(10)]

    for index, serialized in enumerate(repeats):
        assert serialized == baseline, f"Run {index} drifted from baseline"


def test_manifest_pydantic_rejects_invalid_section_kind() -> None:
    """`BulletSection.kind` is constrained to experience/projects — anything else fails."""

    with pytest.raises(pydantic.ValidationError):
        BulletManifest.model_validate(
            {
                "sections": [
                    {
                        "id": "bad",
                        "kind": "skills",  # not in the Literal allowlist
                        "heading": "Skills",
                        "entries": [],
                    }
                ]
            }
        )


def test_bullet_count_and_entry_count_helpers_return_zero_for_empty_manifest() -> None:
    """Helper methods on `BulletManifest` handle the empty case."""

    empty = BulletManifest(sections=[])

    assert empty.bullet_count() == 0
    assert empty.entry_count() == 0
