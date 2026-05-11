"""Tests for `_apply_edits_in_memory` — the bullet-edit application logic.

Purpose:
    The handoff flagged `_apply_edits_in_memory` as a cognitive-complexity
    hotspot. These tests cover the documented invariants:

    * The on-disk YAML is never mutated; the function returns a new copy.
    * Edits referencing unknown sections/listings/bullets are dropped with
      a warning rather than aborting.
    * Empty `new_text` removes bullets and disables skill rows.
    * Non-empty `new_text` rewrites bullet/skill text.

    These are pure-function invariants — no DB, no filesystem.
"""

from __future__ import annotations

from copy import deepcopy

import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from src.agents.resume_tailor.pipeline import _apply_edits_in_memory
from src.agents.resume_tailor.pipeline_schemas import BulletEdit
from src.agents.resume_tailor.schemas import ResumeContent

from tests.helpers.pipeline_factories import (
    build_minimal_resume_content,
    resume_yaml_fixture_path,
)


def _load_populated_resume() -> ResumeContent:
    """Load the populated fixture resume model used across pipeline tests."""

    with open(resume_yaml_fixture_path(), "r", encoding="utf-8") as fixture_file:
        payload = yaml.safe_load(fixture_file)
    return ResumeContent.model_validate(payload)


def test_returns_new_copy_and_leaves_input_unchanged() -> None:
    """Input model is not mutated regardless of which edits are applied."""

    resume = _load_populated_resume()
    snapshot = resume.model_dump(mode="json")
    edits = [
        BulletEdit(
            section="experience",
            listing_id="exp_software_engineering_intern",
            bullet_id="software_engineering_intern_bullet_0",
            new_text="Rewrote the backend to handle 50k qps.",
        )
    ]

    new_resume, applied = _apply_edits_in_memory(resume, edits)

    assert applied == 1
    assert resume.model_dump(mode="json") == snapshot
    assert new_resume.model_dump(mode="json") != snapshot


def test_rewrites_bullet_text_when_target_matches() -> None:
    """Non-empty `new_text` replaces the targeted bullet's text exactly."""

    resume = _load_populated_resume()
    edits = [
        BulletEdit(
            section="experience",
            listing_id="exp_software_engineering_intern",
            bullet_id="software_engineering_intern_bullet_0",
            new_text="Owned a critical service.",
        )
    ]

    new_resume, _ = _apply_edits_in_memory(resume, edits)

    listing = new_resume.experience.listings[0]
    matching_bullet = next(
        bullet
        for bullet in listing.bullets
        if bullet.id == "software_engineering_intern_bullet_0"
    )
    assert matching_bullet.text == "Owned a critical service."


def test_empty_new_text_removes_bullet_entirely() -> None:
    """Empty/whitespace replacement removes the bullet from the listing."""

    resume = _load_populated_resume()
    edits = [
        BulletEdit(
            section="experience",
            listing_id="exp_software_engineering_intern",
            bullet_id="software_engineering_intern_bullet_0",
            new_text="   ",
        )
    ]
    original_count = len(resume.experience.listings[0].bullets)

    new_resume, applied = _apply_edits_in_memory(resume, edits)

    assert applied == 1
    assert len(new_resume.experience.listings[0].bullets) == original_count - 1


def test_skill_row_disabled_when_new_text_is_empty() -> None:
    """Empty `new_text` on a skill row sets `enabled=False` rather than deleting."""

    resume = _load_populated_resume()
    edits = [
        BulletEdit(
            section="skills_achievements",
            listing_id="skill_languages",
            bullet_id=None,
            new_text="",
        )
    ]

    new_resume, applied = _apply_edits_in_memory(resume, edits)

    assert applied == 1
    skill = next(
        listing
        for listing in new_resume.skills_achievements.listings
        if listing.id == "skill_languages"
    )
    assert skill.enabled is False
    assert skill.text == "Python, TypeScript, SQL, Bash"


def test_skill_row_rewritten_when_new_text_non_empty() -> None:
    """Non-empty `new_text` on a skill row rewrites `text` and keeps it enabled."""

    resume = _load_populated_resume()
    edits = [
        BulletEdit(
            section="skills_achievements",
            listing_id="skill_languages",
            bullet_id=None,
            new_text="Rust, Go, Python",
        )
    ]

    new_resume, _ = _apply_edits_in_memory(resume, edits)

    skill = next(
        listing
        for listing in new_resume.skills_achievements.listings
        if listing.id == "skill_languages"
    )
    assert skill.text == "Rust, Go, Python"
    assert skill.enabled is True


def test_edit_targeting_non_editable_section_is_dropped() -> None:
    """`personal`/`education` cannot be touched; edits are silently skipped."""

    resume = _load_populated_resume()
    edits = [
        BulletEdit(
            section="education",
            listing_id="edu_test_university",
            bullet_id="edu_test_bullet_0",
            new_text="Anything",
        )
    ]

    _, applied = _apply_edits_in_memory(resume, edits)

    assert applied == 0


def test_edit_with_unknown_listing_is_dropped() -> None:
    """Unknown listing IDs produce no change and zero applied count."""

    resume = _load_populated_resume()
    edits = [
        BulletEdit(
            section="experience",
            listing_id="exp_does_not_exist",
            bullet_id="bullet_x",
            new_text="x",
        )
    ]

    _, applied = _apply_edits_in_memory(resume, edits)

    assert applied == 0


def test_edit_with_unknown_bullet_is_dropped() -> None:
    """Unknown bullet IDs produce no change."""

    resume = _load_populated_resume()
    edits = [
        BulletEdit(
            section="experience",
            listing_id="exp_software_engineering_intern",
            bullet_id="bullet_does_not_exist",
            new_text="x",
        )
    ]

    _, applied = _apply_edits_in_memory(resume, edits)

    assert applied == 0


def test_missing_bullet_id_on_experience_is_dropped() -> None:
    """Experience/projects edits require a `bullet_id`; missing ones drop."""

    resume = _load_populated_resume()
    edits = [
        BulletEdit(
            section="experience",
            listing_id="exp_software_engineering_intern",
            bullet_id=None,
            new_text="x",
        )
    ]

    _, applied = _apply_edits_in_memory(resume, edits)

    assert applied == 0


def test_applied_count_matches_valid_edits_in_mixed_batch() -> None:
    """Among 1 valid and 2 invalid edits, only the valid one counts."""

    resume = _load_populated_resume()
    edits = [
        BulletEdit(
            section="experience",
            listing_id="exp_software_engineering_intern",
            bullet_id="software_engineering_intern_bullet_0",
            new_text="Valid",
        ),
        BulletEdit(
            section="education",
            listing_id="edu_test_university",
            bullet_id="edu_test_bullet_0",
            new_text="Not editable",
        ),
        BulletEdit(
            section="experience",
            listing_id="exp_software_engineering_intern",
            bullet_id="nonexistent_bullet_99",
            new_text="No such bullet",
        ),
    ]

    _, applied = _apply_edits_in_memory(resume, edits)

    assert applied == 1


@given(
    new_texts=st.lists(
        st.text(min_size=0, max_size=80, alphabet=st.characters(blacklist_categories=["Cs"])),
        min_size=0,
        max_size=10,
    )
)
@settings(max_examples=100, deadline=None)
def test_property_input_resume_never_mutated(new_texts: list[str]) -> None:
    """Property: regardless of edit batch, the input model never mutates.

    Purpose:
        Hammer the deep-copy invariant with random edit batches. The handoff
        explicitly flagged this as a load-bearing property of the function.
    """

    resume = build_minimal_resume_content()
    baseline = deepcopy(resume)
    edits = [
        BulletEdit(
            section="experience",
            listing_id="exp_a",
            bullet_id="bullet_a0",
            new_text=text,
        )
        for text in new_texts
    ]

    _apply_edits_in_memory(resume, edits)

    assert resume.model_dump(mode="json") == baseline.model_dump(mode="json")


@pytest.mark.parametrize(
    "section,bullet_id",
    [
        ("experience", "bullet_a0"),
        ("projects", "bullet_p0"),
    ],
)
def test_applies_to_either_editable_section_with_bullets(
    section: str,
    bullet_id: str,
) -> None:
    """Experience and projects share the same bullet-edit path."""

    resume = build_minimal_resume_content()
    listing_id = "exp_a" if section == "experience" else "proj_a"
    edits = [
        BulletEdit(
            section=section,
            listing_id=listing_id,
            bullet_id=bullet_id,
            new_text="rewritten",
        )
    ]

    _, applied = _apply_edits_in_memory(resume, edits)

    assert applied == 1
