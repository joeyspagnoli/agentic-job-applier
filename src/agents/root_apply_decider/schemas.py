"""Schema models for the root apply-decider agent."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel
from pydantic import Field


class ApplyDecision(str, Enum):
    """Enumerate the two allowed apply-decider outcomes."""

    APPLY = "APPLY"
    SKIP = "SKIP"


class GateDebugInfo(BaseModel):
    """Store optional model metadata for logging and debugging."""

    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence score from 0 to 1 when provided by the model.",
    )
    explanation: str | None = Field(
        default=None,
        description="Short explanation of why the gate chose APPLY or SKIP.",
    )
    preference_matches: list[str] = Field(
        default_factory=list,
        description="Candidate preferences or strengths that matched the role.",
    )
    preference_conflicts: list[str] = Field(
        default_factory=list,
        description="Candidate preferences or hard filters that conflicted with the role.",
    )


class GateRunResult(BaseModel):
    """Capture the persisted result payload for one gate run."""

    decision: ApplyDecision
    debug: GateDebugInfo = Field(default_factory=GateDebugInfo)
    raw_response: str
    provider: str
    model: str
    parse_mode: str
