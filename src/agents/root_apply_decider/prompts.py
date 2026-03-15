"""Prompt constants and payload builder for the root apply-decider."""

from __future__ import annotations

from typing import Any
from typing import Mapping

ROOT_APPLY_DECIDER_INSTRUCTION = """
You are the apply/skip gate for a job application workflow.

Your task is to decide whether this candidate should APPLY or SKIP a job.

Decision rules:
- Return APPLY when the role is aligned overall and does not violate hard filters.
- Return SKIP when the role clearly violates hard filters or is obviously a poor fit.
- Bias toward APPLY for borderline but aligned roles.
- Do not require the candidate to meet every listed requirement.
- Treat the candidate as a current bachelor's student, so non-internship or non-student roles are usually a bad fit.
- Prefer ML, AI, and MLOps roles most strongly.
- General software roles are acceptable if they are in strong technology organizations and involve real engineering work.
- Skip frontend-focused, IT/support, embedded, low-code, defense-related, or weak-engineering roles.
- If compensation is listed and clearly below $25/hour, treat that as a strong negative signal.
- If compensation is not listed, rely on company quality and role alignment.
- If the company is unfamiliar but the role still looks aligned, bias toward APPLY.

Output:
Return a JSON object with this required field:
{"decision":"APPLY"} or {"decision":"SKIP"}

You may also include:
- "confidence": number from 0.0 to 1.0
- "explanation": short explanation
- "preference_matches": array of short strings
- "preference_conflicts": array of short strings

Do not return markdown fences or any text outside the JSON object.
""".strip()

ROOT_APPLY_DECIDER_CANDIDATE_CONTEXT = """
Candidate Context
- Education: BS in Computer Science in progress at University of Florida.
- Citizenship: US citizen.
- Target roles: ML internship, AI internship, MLOps internship, software engineering internship
- Strongest areas: ML, AI engineering, MLOps, backend software, agentic systems, Python, PyTorch, FastAPI, Docker, AWS, GCP
- Experience highlights:
  - AI Solutions Engineer Intern at GE Appliances
  - AI Scholars Researcher at University of Florida
  - AI Engineer Intern at Amentum supporting NASA Johnson Space Center
  - Projects in retrieval systems, backend APIs, MLOps workflows, and AI tooling
- Hard filters:
  - US only
  - internship/co-op/student roles only
  - no frontend
  - no IT/support
  - no embedded
  - no low-code
  - no defense
  - no roles with little real engineering content
- Preferences:
  - prefer ML, AI, and MLOps
  - allow general software roles in strong technology organizations
  - prefer high-signal, technically complex, or high-paying environments
  - bias toward APPLY when aligned and no strong negative evidence exists
  - if compensation is listed, prefer at least $25/hour
- Compensation rule: If compensation is listed, prefer at least $25/hour.
""".strip()


def _trim_prompt_text(text: str, *, limit: int) -> str:
    """Trim long free-text values to keep runtime prompts compact.

    Purpose:
        Keep decider inputs within a predictable size so unusually long job
        descriptions do not crowd out the decision-critical sections.
    Args:
        text: Free-text field value to include in the payload.
        limit: Maximum number of characters to keep before truncating.
    Output:
        Returns the original text when short enough, or a truncated value with
        a trailing marker when the limit is exceeded.
    """

    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n[truncated]"


def _format_salary_range(job: Mapping[str, Any]) -> str:
    """Format stored salary fields into a readable compensation string.

    Purpose:
        Convert cents-based salary fields to prompt-friendly text so the decider
        can reason about compensation without JSON-centric parsing.
    Args:
        job: Normalized job row mapping that may include salary fields.
    Output:
        Returns a human-readable compensation line for the job section.
    """

    salary_min = job.get("salary_min")
    salary_max = job.get("salary_max")
    salary_currency = job.get("salary_currency") or "USD"
    salary_source = job.get("salary_source") or "not_listed"

    if salary_min is None and salary_max is None:
        return f"Not listed ({salary_source})"

    # Salary fields are stored in cents, so convert to normal units for the
    # model-facing prompt text.
    if salary_min is not None and salary_max is not None:
        return f"{salary_currency} ${salary_min / 100:,.0f} - ${salary_max / 100:,.0f} ({salary_source})"
    if salary_min is not None:
        return f"{salary_currency} ${salary_min / 100:,.0f}+ ({salary_source})"
    return f"Up to {salary_currency} ${salary_max / 100:,.0f} ({salary_source})"


def build_gate_payload(job: Mapping[str, Any]) -> str:
    """Build the runtime payload text for one root apply-decider run.

    Purpose:
        Inject the hardcoded candidate context and the target job fields into
        one labeled text payload that the agent instruction can evaluate.
    Args:
        job: Normalized job row loaded from the database.
    Output:
        Returns the final prompt payload sent as the user message to the model.
    """

    prompt_lines = [
        ROOT_APPLY_DECIDER_CANDIDATE_CONTEXT,
        "",
        "Job Posting",
        f"- Company: {job.get('company') or 'Not specified'}",
        f"- Title: {job.get('title') or 'Not specified'}",
        f"- Source: {job.get('source') or 'Not specified'}",
        f"- URL: {job.get('source_url') or 'Not specified'}",
        f"- Location: {job.get('location') or 'Not specified'}",
        f"- Remote: {job.get('is_remote')}",
        f"- Job type: {job.get('job_type') or 'Not specified'}",
        f"- Compensation: {_format_salary_range(job)}",
        "Description:",
        _trim_prompt_text(job.get("description") or "Not provided", limit=4000),
        "",
        "Requirements:",
        _trim_prompt_text(job.get("requirements") or "Not provided", limit=2000),
    ]
    return "\n".join(prompt_lines)
