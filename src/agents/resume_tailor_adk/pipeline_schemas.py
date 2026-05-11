"""Pydantic schemas for the ADK tailor/reviewer pipeline.

These models are intentionally separate from the canonical `ResumeContent`
schemas in `schemas.py` — they describe the *contract* the tailor and
reviewer agents emit, not the resume document itself.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

EDITABLE_SECTION_IDS: tuple[str, ...] = (
    "experience",
    "projects",
    "skills_achievements",
)


class ReviewerVerdict(str, Enum):
    """Final-pick verdict emitted by the reviewer agent.

    Purpose:
        Encode the three reviewer outcomes consumed by `pipeline.py` to
        decide which resume PDF is served back to the caller.
    """

    TAILORED_BETTER = "tailored_better"
    BASE_BETTER = "base_better"
    NO_MEANINGFUL_IMPROVEMENT = "no_meaningful_improvement"


class BulletEdit(BaseModel):
    """One bullet-level edit emitted by the tailor or trim agent.

    Purpose:
        Apply targeted bullet rewrites/replacements without forcing the model
        to re-emit the full resume YAML. The orchestrator applies these edits
        in-memory; the on-disk `config/resume_content.yaml` is never mutated.
    """

    section: str = Field(
        description="Section ID — one of experience, projects, skills_achievements.",
    )
    listing_id: str = Field(description="Stable listing ID inside the section.")
    bullet_id: Optional[str] = Field(
        default=None,
        description=(
            "Stable bullet ID inside the listing. Required for experience and "
            "projects sections; ignored for skills_achievements where the entire "
            "row text is rewritten via `new_text`."
        ),
    )
    new_text: str = Field(description="Replacement text for the bullet or row.")


class TailorOutput(BaseModel):
    """Structured response shape returned by the tailor (and trim) agent."""

    edits: list[BulletEdit] = Field(default_factory=list)
    summary: str = Field(default="", description="Human-readable summary of changes.")


class ReviewerScores(BaseModel):
    """Rubric scores assigned by the reviewer agent to one resume variant."""

    keywords: int = Field(ge=0, le=5, description="Keyword/JD-alignment score 0-5.")
    specificity: int = Field(ge=0, le=5, description="Concreteness/impact score 0-5.")
    fit: int = Field(ge=0, le=5, description="Overall role-fit score 0-5.")


class ReviewerOutput(BaseModel):
    """Structured reviewer response covering one tailor attempt."""

    verdict: ReviewerVerdict
    scores_base: ReviewerScores
    scores_tailored: ReviewerScores
    rationale: str = Field(default="")
    feedback_for_retry: Optional[str] = Field(
        default=None,
        description=(
            "When verdict is `base_better`, an actionable critique that the "
            "re-tailor pass should address. Required by the orchestrator on "
            "base_better; ignored otherwise."
        ),
    )


class TailorRunResult(BaseModel):
    """Final return payload from `run_tailor_review_pipeline`.

    Purpose:
        Give callers (the worker and the API BackgroundTask) a single
        deterministic value describing which artifacts were produced and
        why the pipeline ended in this state.
    """

    success: bool
    job_hash: str
    tailor_run_id: int
    review_run_id: Optional[int] = None
    verdict: Optional[str] = None
    selected_pdf_path: Optional[str] = None
    selected_yaml_path: Optional[str] = None
    selected_tex_path: Optional[str] = None
    page_count: Optional[int] = None
    scores_base: Optional[ReviewerScores] = None
    scores_tailored: Optional[ReviewerScores] = None
    error: Optional[str] = None
