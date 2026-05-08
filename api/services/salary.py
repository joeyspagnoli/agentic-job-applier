"""Salary, gate, and pipeline-step rendering helpers for jobs endpoints."""

from __future__ import annotations

import json


def _salary_display(
    salary_min: int | None,
    salary_max: int | None,
    salary_currency: str | None,
) -> str:
    """Render salary fields to a single human-readable display string.

    Purpose:
        Keep salary formatting consistent across all jobs-table rows.
    Args:
        salary_min: Minimum salary in cents, when available.
        salary_max: Maximum salary in cents, when available.
        salary_currency: Currency code (for example, USD).
    Output:
        Returns a display string suitable for direct table rendering.
    """

    currency = (salary_currency or "USD").upper()
    if salary_min is None and salary_max is None:
        return "—"
    if salary_min is not None and salary_max is not None:
        return f"{currency} ${salary_min / 100:,.0f}–${salary_max / 100:,.0f}"
    if salary_min is not None:
        return f"{currency} ${salary_min / 100:,.0f}+"
    if salary_max is None:
        return "—"
    return f"Up to {currency} ${salary_max / 100:,.0f}"


def _parse_gate_result(agent_result: str | None) -> tuple[str, str]:
    """Parse gate decision and explanation from stored JSON payload.

    Purpose:
        Decode serialized gate output safely for jobs-table detail rendering
        without failing requests on malformed legacy payloads.
    Args:
        agent_result: Raw serialized gate payload from `job_postings.agent_result`.
    Output:
        Returns `(decision, explanation)` with safe fallback values.
    """

    if not agent_result:
        return "UNKNOWN", "No gate reasoning is available for this job yet."

    try:
        payload = json.loads(agent_result)
    except json.JSONDecodeError:
        return "UNKNOWN", "Gate result could not be parsed from stored payload."

    decision = str(payload.get("decision") or "UNKNOWN").upper()
    explanation = str(payload.get("explanation") or "No explanation provided.")
    return decision, explanation


def _parse_unresolved_fields(raw_json: str | None) -> list[dict[str, str]]:
    """Normalize stored unresolved-field payloads for human-review UI cards.

    Purpose:
        Convert flexible worker JSON output into a stable structure consumed by
        the review dashboard table expansion panel.
    Args:
        raw_json: Serialized unresolved-fields JSON from apply telemetry.
    Output:
        Returns a list with `field_name`, `ai_answer`, `reasoning`, and
        `answer_confidence` keys.
    """

    if not raw_json:
        return []

    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError:
        return []

    if not isinstance(payload, list):
        return []

    normalized_items: list[dict[str, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue

        field_name = str(
            item.get("label")
            or item.get("field_name")
            or item.get("name")
            or "Unresolved field"
        )
        ai_answer = str(
            item.get("recommended_value")
            or item.get("suggested_value")
            or item.get("value")
            or "Manual response required"
        )
        reasoning = str(
            item.get("reason")
            or item.get("hint")
            or "Generated from captured form context."
        )

        confidence_raw = str(item.get("confidence") or "medium").lower()
        if confidence_raw in {"high", "medium", "low"}:
            answer_confidence = confidence_raw
        else:
            answer_confidence = "medium"

        normalized_items.append(
            {
                "field_name": field_name,
                "ai_answer": ai_answer,
                "reasoning": reasoning,
                "answer_confidence": answer_confidence,
            }
        )

    return normalized_items


def _build_pipeline_steps(
    *,
    job_status: str,
    has_tailor_success: bool,
    has_review_success: bool,
    has_apply_success: bool,
    has_pending_handoff: bool,
) -> list[dict[str, str]]:
    """Construct timeline step states for one jobs-table expansion panel.

    Purpose:
        Keep pipeline-step rendering deterministic using persisted stage
        outcomes and the current top-level job status.
    Args:
        job_status: Coarse job status from `job_postings.status`.
        has_tailor_success: Whether at least one tailor run succeeded.
        has_review_success: Whether at least one review run succeeded.
        has_apply_success: Whether at least one apply run succeeded.
        has_pending_handoff: Whether a pending human-review handoff exists.
    Output:
        Returns six step records with `label` and `status` keys.
    """

    status_upper = job_status.upper()
    discovered = "complete"
    qualified = (
        "complete"
        if status_upper in {"QUALIFIED", "APPLIED", "REJECTED", "FILTERED"}
        else "pending"
    )
    tailored = "complete" if has_tailor_success else "pending"
    reviewed = "complete" if has_review_success else "pending"
    applied = "complete" if has_apply_success else "pending"
    human_review = "active" if has_pending_handoff else "pending"

    return [
        {"label": "DISCOVERED", "status": discovered},
        {"label": "QUALIFIED", "status": qualified},
        {"label": "TAILORED", "status": tailored},
        {"label": "REVIEWED", "status": reviewed},
        {"label": "APPLIED", "status": applied},
        {"label": "HUMAN REVIEW", "status": human_review},
    ]
