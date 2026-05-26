"""Pydantic schemas for the resume-tailor / reviewer pipeline.

These models describe the *contract* the tailor and reviewer LLM
calls emit, not the resume document itself. The contract is
rationale-first by design — small models constrained by strict
`json_schema` collapse when forced to emit the answer before the
reasoning (Let Me Speak Freely, arXiv 2408.02442), so `rewrite_plan`
and `rationale` are field-1 in their respective payloads.

The pipeline operates on a bullet manifest + byte-offset patch shape.
YAML-era schemas (`BulletEdit`, the old `TailorOutput` /
`ReviewerOutput`, `EDITABLE_SECTION_IDS`) are no longer in use.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ReviewerVerdict(str, Enum):
    """Final-pick verdict emitted by the reviewer agent.

    Purpose:
        Encode the three reviewer outcomes consumed by `pipeline.py`
        to decide which resume PDF is served back to the caller.
    """

    TAILORED_BETTER = "tailored_better"
    BASE_BETTER = "base_better"
    NO_MEANINGFUL_IMPROVEMENT = "no_meaningful_improvement"


class BulletPatchProposal(BaseModel):
    """One bullet-level edit emitted by the tailor LLM.

    Purpose:
        Carry the manifest bullet ID + the LLM's decision (keep vs
        rewrite) + replacement text the pipeline will splice in.

    Field order is intentional: `rationale` precedes `action` and
    `new_text` so strict JSON-schema generation can't lock in the
    answer before producing reasoning.
    """

    id: str = Field(description="Exact bullet ID from the manifest.")
    rationale: str = Field(
        description="Why this bullet should be kept or rewritten."
    )
    action: Literal["keep", "rewrite"] = Field(
        description="Decision for this bullet."
    )
    new_text: str = Field(
        default="",
        description=(
            "Replacement text when action='rewrite'; empty when "
            "action='keep'. Copy any macros (\\textbf{X}, \\textit{X}) "
            "from the original bullet verbatim. Use only plain text + "
            "LaTeX escapes (\\&, \\%, \\$, \\#, \\_)."
        ),
    )


class SkippedBulletNote(BaseModel):
    """Acknowledgment of a bullet the LLM chose not to touch.

    Purpose:
        Let the LLM surface "I considered this but won't change it"
        signals without forcing a `keep`-action payload for every
        manifest bullet. The pipeline records these in
        `review_report_json` for debugging.
    """

    id: str = Field(description="Manifest bullet ID that was skipped.")
    reason: str = Field(description="Why the bullet was left alone.")


class TailorOutput(BaseModel):
    """Strict-JSON output shape from the tailor LLM.

    Purpose:
        Pair the rationale-first rewrite plan with the per-bullet
        decisions the pipeline patches into the user's `.tex`.

    `rewrite_plan` is field-1 to keep the LMSF-safe field ordering
    intact even when the schema is rendered as a JSON tool call.
    """

    rewrite_plan: str = Field(
        description=(
            "Overall strategy: which bullets you targeted and why, "
            "before emitting per-bullet decisions."
        ),
    )
    bullets: list[BulletPatchProposal] = Field(default_factory=list)
    skipped_bullets: list[SkippedBulletNote] = Field(default_factory=list)


class ReviewerScores(BaseModel):
    """Rubric scores assigned by the reviewer to one resume variant.

    Purpose:
        Pin the three rubric axes from plan §4.5 — `keyword_fit`,
        `specificity`, `factuality` — at 0-5 each. Factuality acts
        as a veto in the reviewer prompt (see §4.5): any unsupported
        claim mandates `base_better` regardless of the other axes.
    """

    keyword_fit: int = Field(
        ge=0, le=5, description="Alignment with the JD's keywords/skills."
    )
    specificity: int = Field(
        ge=0, le=5, description="Concreteness, action verbs, measurable impact."
    )
    factuality: int = Field(
        ge=0,
        le=5,
        description=(
            "Zero invented claims. Veto axis: any unsupported claim "
            "forces `base_better` regardless of the other scores."
        ),
    )


class ReviewerOutput(BaseModel):
    """Structured reviewer response covering one tailor attempt.

    Purpose:
        Combine rationale-first reasoning with rubric scores and the
        verdict the pipeline acts on. `feedback_for_retry` is required
        when the verdict is `base_better` so the optional one-shot
        retry has actionable critique to work from.
    """

    rationale: str = Field(
        description="2-3 sentences justifying the pick. Field-1 by design.",
    )
    scores_base: ReviewerScores
    scores_tailored: ReviewerScores
    verdict: ReviewerVerdict
    feedback_for_retry: Optional[str] = Field(
        default=None,
        description=(
            "Required when verdict is base_better; null otherwise. The "
            "re-tailor pass uses this critique verbatim."
        ),
    )


class TailorRunResult(BaseModel):
    """Final return payload from `run_tailor_review_pipeline`.

    Purpose:
        Give callers (the worker and the API BackgroundTask) a single
        deterministic value describing which artifacts were produced
        and why the pipeline ended in this state.
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


__all__ = [
    "BulletPatchProposal",
    "ReviewerOutput",
    "ReviewerScores",
    "ReviewerVerdict",
    "SkippedBulletNote",
    "TailorOutput",
    "TailorRunResult",
]
