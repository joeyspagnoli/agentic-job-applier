"""Builders for `ResumeContent` and reviewer payloads used by pipeline tests.

Purpose:
    Concentrate fixture construction so each test reads as a sequence of
    behaviors rather than a wall of nested dicts. Every factory returns a
    fully validated Pydantic model so tests fail fast on schema drift.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from src.agents.resume_tailor.llm import LlmCallResult
from src.agents.resume_tailor.pipeline_schemas import (
    BulletEdit,
    ReviewerOutput,
    ReviewerScores,
    ReviewerVerdict,
    TailorOutput,
)
from src.agents.resume_tailor.schemas import (
    EducationEntry,
    EducationSection,
    ExperienceListing,
    ExperienceSection,
    PersonalSection,
    ProjectListing,
    ProjectsSection,
    ResumeBullet,
    ResumeContent,
    ResumeLink,
    SkillListing,
    SkillsAchievementsSection,
)


def row_int(row: dict[str, object] | None, key: str) -> int:
    """Extract one int field from a `dict[str, object]` row safely.

    Purpose:
        Avoid scattering `int(cast(int, row["id"]))` across every test.
        Asserts the row is not `None` and the field is integral.
    Args:
        row: Database row mapping returned by `DatabaseManager` methods.
        key: Field name to extract.
    Output:
        Returns the integer value.
    """

    assert row is not None, "expected a row, got None"
    return int(cast(int, row[key]))


def row_str(row: dict[str, object] | None, key: str) -> str:
    """Extract one string field from a `dict[str, object]` row safely."""

    assert row is not None, "expected a row, got None"
    return str(cast(str, row[key]))


def resume_yaml_fixture_path() -> Path:
    """Return the absolute path to the populated resume YAML fixture."""

    return Path(__file__).resolve().parent.parent / "fixtures" / "resume_content_populated.yaml"


def build_minimal_resume_content() -> ResumeContent:
    """Build a minimal, schema-valid `ResumeContent` for unit tests.

    Purpose:
        Provide a deterministic Pydantic model with one entry in each
        editable section so the bullet-edit and pipeline branches can
        be exercised without coupling to a YAML file.
    """

    return ResumeContent(
        personal=PersonalSection(
            name="Test Person",
            phone="555-555-0000",
            email="test@example.com",
            links=[ResumeLink(id="linkedin_t", label="li/test", url="https://example.com")],
        ),
        education=EducationSection(
            entries=[
                EducationEntry(
                    id="edu_a",
                    institution="Test U",
                    date_range="2020-2024",
                    degree="B.S.",
                    detail="GPA 4.0",
                    bullets=[ResumeBullet(id="edu_a_bullet_0", text="Coursework")],
                )
            ]
        ),
        experience=ExperienceSection(
            listings=[
                ExperienceListing(
                    id="exp_a",
                    title="Engineer",
                    date_range="2024-2025",
                    organization="ACME",
                    bullets=[
                        ResumeBullet(id="bullet_a0", text="Built things"),
                        ResumeBullet(id="bullet_a1", text="Shipped things"),
                    ],
                )
            ]
        ),
        projects=ProjectsSection(
            listings=[
                ProjectListing(
                    id="proj_a",
                    title="Project A",
                    tech_stack="Python",
                    date_range="2024",
                    bullets=[ResumeBullet(id="bullet_p0", text="Made a thing")],
                )
            ]
        ),
        skills_achievements=SkillsAchievementsSection(
            listings=[
                SkillListing(
                    id="skill_langs",
                    category="Languages",
                    text="Python, Rust",
                )
            ]
        ),
    )


def make_tailor_result(
    *,
    edits: list[BulletEdit] | None = None,
    summary: str = "",
) -> LlmCallResult[TailorOutput]:
    """Build an `LlmCallResult[TailorOutput]` stub for monkeypatching.

    Purpose:
        Keep test assertions focused on pipeline branches; the LLM call
        result shape stays consistent across every scenario.
    """

    output = TailorOutput(edits=list(edits or []), summary=summary)
    return LlmCallResult(
        parsed=output,
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        model="openai/test-model",
    )


def make_reviewer_result(
    *,
    verdict: ReviewerVerdict,
    feedback_for_retry: str | None = None,
    rationale: str = "",
) -> LlmCallResult[ReviewerOutput]:
    """Build an `LlmCallResult[ReviewerOutput]` stub."""

    output = ReviewerOutput(
        verdict=verdict,
        scores_base=ReviewerScores(keywords=3, specificity=3, fit=3),
        scores_tailored=ReviewerScores(keywords=4, specificity=4, fit=4),
        rationale=rationale,
        feedback_for_retry=feedback_for_retry,
    )
    return LlmCallResult(
        parsed=output,
        prompt_tokens=20,
        completion_tokens=8,
        total_tokens=28,
        model="openai/test-model",
    )


def single_valid_edit() -> BulletEdit:
    """Return one edit that targets the populated YAML fixture.

    Purpose:
        Match the IDs in `tests/fixtures/resume_content_populated.yaml`
        so the pipeline counts the edit as applicable.
    """

    return BulletEdit(
        section="experience",
        listing_id="exp_software_engineering_intern",
        bullet_id="software_engineering_intern_bullet_0",
        new_text="Rewrote the thing.",
    )
