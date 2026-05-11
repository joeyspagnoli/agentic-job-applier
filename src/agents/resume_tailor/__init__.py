"""Resume tailor + reviewer pipeline driven by Instructor LLM calls.

Each stage (tailor → optional trim → reviewer → optional retry →
optional 3-way pick) is one structured Pydantic-validated call routed
through the Instructor library, with the orchestration plus filesystem
side-effects living in `pipeline.py`. Public entry points are exposed
here so the worker daemon and the API BackgroundTask both share one
implementation.
"""

from __future__ import annotations

from src.agents.resume_tailor.pipeline import run_tailor_review_pipeline
from src.agents.resume_tailor.pipeline_schemas import (
    BulletEdit,
    ReviewerOutput,
    ReviewerScores,
    ReviewerVerdict,
    TailorOutput,
    TailorRunResult,
)

__all__ = [
    "BulletEdit",
    "ReviewerOutput",
    "ReviewerScores",
    "ReviewerVerdict",
    "TailorOutput",
    "TailorRunResult",
    "run_tailor_review_pipeline",
]
