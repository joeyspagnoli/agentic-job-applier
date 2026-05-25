"""Pydantic schemas + deps for the apply-finisher agent.

These types form the contract between the Pydantic AI agent loop, the
typed BYO tools, and the worker that consumes the final
``FinisherResult``. Keeping them in their own module avoids a circular
import between ``agent.py`` (registers tools) and ``tools.py`` (uses
``FinisherDeps``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:  # pragma: no cover - import only for typing
    from src.agents.apply_finisher.answer_cache import AnswerCache
    from src.agents.apply_finisher.defer_rules import DeferRules

# Discrete ATS platforms the finisher knows how to drive in v1.
SupportedAts = Literal["greenhouse", "ashby"]


class DeferredQuestion(BaseModel):
    """A Tier-3 question the finisher declined to answer.

    Attributes:
        field_id: ``aria-ref`` identifier of the field (e.g. ``"e5"``).
        label: Visible label text captured at defer time.
        field_type: Type token (``select``, ``textarea``, ``checkbox``, ...).
        category: Defer category (``sponsorship``, ``eeo``, ``salary``,
            ``start_date``, ``other``).
        reason: Short human-readable reason the finisher recorded.
    """

    field_id: str
    label: str
    field_type: str
    category: str
    reason: str


class DraftedField(BaseModel):
    """A Tier-2 draft the finisher filled but flagged for human review.

    Attributes:
        field_id: ``aria-ref`` identifier the draft targets.
        label: Visible label captured when the draft was authored.
        drafted_value: The text the agent wrote into the field.
        confidence: Self-reported confidence in [0.0, 1.0]. Gate logic
            in the worker compares this against
            ``application_defaults.tier2_confidence_threshold`` from
            the candidate profile.
        reasoning: Short justification the model produced before
            scoring confidence (kept so users can audit the choice).
    """

    field_id: str
    label: str
    drafted_value: str
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


class FinisherResult(BaseModel):
    """Final structured output from the finisher loop.

    Attributes:
        turns_used: Number of agent iterations consumed (1 per
            ``ModelRequestNode``).
        cost_usd: Accumulated USD cost computed from each turn's
            ``RunUsage`` delta via ``litellm.cost_per_token``.
        fields_filled: Count of Tier-1 fills that landed without flagging.
        fields_deferred: Count of Tier-3 fields the agent skipped.
        deferred_questions: Full list of Tier-3 records for handoff.
        drafted_fields_flagged_for_verify: Tier-2 drafts the human must
            approve before they're cached as Tier 1.
        outcome: Terminal state. ``COMPLETE`` is the only state in which
            the gate may auto-submit; the other three force NEEDS_REVIEW.
        all_required_filled: True when the agent verified every required
            field is either filled (Tier 1) or drafted (Tier 2).
        has_tier3_deferred: Convenience flag mirroring
            ``len(deferred_questions) > 0``.
        has_tier2_pending: Convenience flag mirroring
            ``len(drafted_fields_flagged_for_verify) > 0``.
        simplify_no_op: Telemetry mirror of the verify-after-fill helper;
            forwarded into ``finisher_diagnostics_json`` without
            changing control flow.
    """

    turns_used: int = 0
    cost_usd: float = 0.0
    fields_filled: int = 0
    fields_deferred: int = 0
    deferred_questions: list[DeferredQuestion] = Field(default_factory=list)
    drafted_fields_flagged_for_verify: list[DraftedField] = Field(default_factory=list)
    outcome: Literal[
        "COMPLETE",
        "AGENT_GAVE_UP",
        "USAGE_LIMIT_HIT",
        "RUNTIME_ERROR",
    ] = "COMPLETE"
    all_required_filled: bool = False
    has_tier3_deferred: bool = False
    has_tier2_pending: bool = False
    simplify_no_op: bool = False


@dataclass
class FinisherDeps:
    """Runtime dependencies passed to every tool call via ``RunContext.deps``.

    The browser surface is the agent-browser CLI running in the
    persistent CDP session the worker bootstrapped before invoking the
    finisher — process-global state, not held on this struct.

    Attributes:
        ats: ATS dialect; used for the system-prompt fragment.
        target_company: Company name extracted from the job posting;
            used by the answer cache for ``$COMPANY`` substitution.
        defer_rules: Compiled defer-rule classifier.
        cache: Loaded answer cache used by ``lookup_cached_answer``.
        recorded_deferrals: Per-run accumulator the ``defer`` tool
            appends to. The runner reads this when synthesizing the
            final ``FinisherResult``.
        drafted_fields: Per-run accumulator the ``flag_for_verify``
            tool appends to.
        fields_filled_count: Counter for Tier-1 fills (used by the
            agent to gauge progress; surfaced in ``FinisherResult``).
        profile_yaml: Pre-serialized YAML of the candidate profile
            so prompt assembly stays a single read.
    """

    ats: SupportedAts
    target_company: str
    defer_rules: "DeferRules"
    cache: "AnswerCache"
    profile_yaml: str
    recorded_deferrals: list[DeferredQuestion] = field(default_factory=list)
    drafted_fields: list[DraftedField] = field(default_factory=list)
    fields_filled_count: int = 0


__all__ = [
    "DeferredQuestion",
    "DraftedField",
    "FinisherDeps",
    "FinisherResult",
    "SupportedAts",
]
