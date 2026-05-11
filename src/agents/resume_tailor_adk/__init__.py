"""ADK-driven resume tailor + reviewer pipeline.

Replaces the pi-coding-agent subprocess harness with a small ADK pipeline:
tailor → render → optional trim → reviewer → optional one re-tailor →
final pick. Public entry points are exposed from this package so workers
and API BackgroundTasks share one implementation.
"""

from __future__ import annotations

from src.agents.resume_tailor_adk.pipeline import run_tailor_review_pipeline
from src.agents.resume_tailor_adk.pipeline_schemas import (
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
