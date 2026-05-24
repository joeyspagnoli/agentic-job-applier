"""Behavior tests for `src.agents.resume_tailor.locator`.

Purpose:
    Pin the locator's deterministic-pure-function contract: same `.tex`
    in → same manifest out, byte offsets round-trip back to the bullet
    bodies they describe, role_context is the literal entry-header
    line (never LLM-summarized), and only experience/projects sections
    surface in the manifest.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.agents.resume_tailor.locator import build_bullet_manifest
from src.agents.resume_tailor.manifest import BulletManifest

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "resumes"


def _read_fixture(name: str) -> str:
    """Load a fixture `.tex` from `tests/fixtures/resumes/`.

    Purpose:
        Same I/O helper as in `test_contract_validator.py`; duplicated
        on purpose so test files stay independently readable.
    Args:
        name: Path relative to the resumes directory.
    Output:
        Raw `.tex` text.
    """

    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def test_minimal_fixture_emits_expected_section_kinds() -> None:
    manifest = build_bullet_manifest(_read_fixture("synthetic_minimal.tex"))

    section_kinds = [section.kind for section in manifest.sections]

    assert section_kinds == ["experience", "projects"]


def test_dogfood_resume_emits_15_bullets_across_8_entries() -> None:
    manifest = build_bullet_manifest(_read_fixture("dogfood_user.tex"))

    assert manifest.entry_count() == 8
    assert manifest.bullet_count() == 15


def test_byte_offsets_round_trip_to_bullet_body_text() -> None:
    tex = _read_fixture("dogfood_user.tex")
    manifest = build_bullet_manifest(tex)

    for section in manifest.sections:
        for entry in section.entries:
            for bullet in entry.bullets:
                slice_text = tex[bullet.byte_start : bullet.byte_end]
                assert slice_text == bullet.text


def test_bullet_ids_are_unique_within_a_manifest() -> None:
    manifest = build_bullet_manifest(_read_fixture("dogfood_user.tex"))

    all_ids = [
        bullet.id
        for section in manifest.sections
        for entry in section.entries
        for bullet in entry.bullets
    ]

    assert len(all_ids) == len(set(all_ids))


def test_entry_ids_are_unique_within_a_manifest() -> None:
    manifest = build_bullet_manifest(_read_fixture("dogfood_user.tex"))

    all_ids = [
        entry.id for section in manifest.sections for entry in section.entries
    ]

    assert len(all_ids) == len(set(all_ids))


def test_role_context_is_literal_entry_header_line() -> None:
    # Per §2.2 we never LLM-summarize the entry header — the
    # `role_context` field must equal the raw line, stripped only.
    tex = _read_fixture("dogfood_user.tex")
    manifest = build_bullet_manifest(tex)

    for section in manifest.sections:
        for entry in section.entries:
            header_line_start = entry.header_byte_start
            line_end = tex.find("\n", header_line_start)
            line_end = len(tex) if line_end == -1 else line_end
            literal_line = tex[header_line_start:line_end].strip()
            assert entry.role_context == literal_line


def test_locator_is_deterministic_across_two_runs() -> None:
    tex = _read_fixture("dogfood_user.tex")

    manifest_a = build_bullet_manifest(tex)
    manifest_b = build_bullet_manifest(tex)

    assert manifest_a.model_dump_json() == manifest_b.model_dump_json()


def test_other_kind_sections_are_filtered_out_of_the_manifest() -> None:
    # The dogfood resume has Education + Skills & Achievements sections
    # in addition to Experience + Projects. Only the latter two should
    # surface in the manifest.
    manifest = build_bullet_manifest(_read_fixture("dogfood_user.tex"))

    section_kinds = {section.kind for section in manifest.sections}

    assert section_kinds == {"experience", "projects"}


def test_section_id_counts_up_when_two_sections_share_a_kind() -> None:
    # Two `\section{Projects}` headings should produce ids `projects`
    # and `projects_2` so downstream consumers can disambiguate.
    tex = (
        "\\documentclass{article}\n"
        "\\newcommand{\\resumeItem}[1]{\\item #1}\n"
        "\\newcommand{\\resumeSubheading}[4]{\\item \\textbf{#1} \\hfill \\textbf{#2}\\\\#3\\hfill#4}\n"
        "\\begin{document}\n"
        "\\section{Projects}\n"
        "\\begin{itemize}\n"
        "  \\resumeSubheading{P1}{2024}{Solo}{}\n"
        "    \\begin{itemize}\\resumeItem{First.}\\end{itemize}\n"
        "\\end{itemize}\n"
        "\\section{Personal Projects}\n"
        "\\begin{itemize}\n"
        "  \\resumeSubheading{P2}{2023}{Solo}{}\n"
        "    \\begin{itemize}\\resumeItem{Second.}\\end{itemize}\n"
        "\\end{itemize}\n"
        "\\end{document}\n"
    )

    manifest = build_bullet_manifest(tex)

    ids = [section.id for section in manifest.sections]
    assert ids == ["projects", "projects_2"]


def test_empty_document_produces_empty_manifest() -> None:
    manifest = build_bullet_manifest("\\documentclass{article}\\begin{document}\\end{document}")

    assert isinstance(manifest, BulletManifest)
    assert manifest.sections == []


def test_no_bullets_is_valid_and_produces_zero_bullet_entries() -> None:
    # A resume with experience entries but no bullets (e.g. roles
    # listed only by title) must still produce entries — just with
    # empty bullet lists.
    tex = (
        "\\documentclass{article}\n"
        "\\newcommand{\\resumeSubheading}[4]{\\item \\textbf{#1} \\hfill \\textbf{#2}\\\\#3\\hfill#4}\n"
        "\\begin{document}\n"
        "\\section{Experience}\n"
        "\\begin{itemize}\n"
        "  \\resumeSubheading{Engineer}{2024}{Acme}{Remote}\n"
        "\\end{itemize}\n"
        "\\end{document}\n"
    )

    manifest = build_bullet_manifest(tex)

    assert manifest.entry_count() == 1
    assert manifest.bullet_count() == 0


@pytest.mark.parametrize(
    "fixture_name",
    [
        "synthetic_minimal.tex",
        "dogfood_user.tex",
        "external/deedy_resume.tex",
        "external/fallback_b_textbf_hfill.tex",
    ],
)
def test_passing_fixtures_produce_at_least_one_entry(fixture_name: str) -> None:
    manifest = build_bullet_manifest(_read_fixture(fixture_name))

    assert manifest.entry_count() > 0


def test_manifest_pydantic_round_trip_via_json() -> None:
    # The manifest crosses process boundaries via JSON in the pipeline;
    # ensure pydantic's serialize+deserialize round-trips intact.
    manifest = build_bullet_manifest(_read_fixture("synthetic_minimal.tex"))

    serialized = manifest.model_dump_json()
    rehydrated = BulletManifest.model_validate_json(serialized)

    assert rehydrated.model_dump() == manifest.model_dump()
