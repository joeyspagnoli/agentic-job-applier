"""ADK agent builders and one-shot runner for the tailor/reviewer pipeline.

This module wraps `google.adk.agents.Agent` construction behind two small
factories — `build_tailor_agent` and `build_reviewer_agent` — and exposes
`run_agent_once`, a thin async helper that runs one agent invocation with
a user message and returns the model's raw text response.

JSON parsing lives next door in `pipeline.py` so the agents themselves
remain transport-only.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any, Optional

from google.adk.agents import Agent, BaseAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from src.agents.shared import build_openai_litellm_model

from .prompts import REVIEWER_INSTRUCTION, TAILOR_INSTRUCTION, TRIM_INSTRUCTION

DEFAULT_TAILOR_MODEL = "openai/gpt-5.1-codex-mini"
DEFAULT_REVIEWER_MODEL = "openai/gpt-5.1-codex-mini"

TAILOR_MODEL_ENV_VAR = "RESUME_TAILOR_MODEL"
REVIEWER_MODEL_ENV_VAR = "RESUME_REVIEWER_MODEL"

TAILOR_PROVIDER = "openai"
REVIEWER_PROVIDER = "openai"


def get_tailor_model_name() -> str:
    """Return the tailor model identifier, honoring env override.

    Purpose:
        Centralize model resolution so both the agent factory and cost
        metadata observers see the same string.
    Args:
        None.
    Output:
        Returns the fully qualified LiteLLM model identifier.
    """

    return os.getenv(TAILOR_MODEL_ENV_VAR, "").strip() or DEFAULT_TAILOR_MODEL


def get_reviewer_model_name() -> str:
    """Return the reviewer model identifier, honoring env override.

    Purpose:
        Centralize model resolution for reviewer construction and cost
        tracking.
    Args:
        None.
    Output:
        Returns the fully qualified LiteLLM model identifier.
    """

    return os.getenv(REVIEWER_MODEL_ENV_VAR, "").strip() or DEFAULT_REVIEWER_MODEL


def build_tailor_agent(*, mode: str = "tailor", model: Optional[Any] = None) -> Agent:
    """Build the tailor or trim agent.

    Purpose:
        Both the initial tailor pass and the page-fit trim pass use the
        same JSON `TailorOutput` schema; they only differ by instruction
        template. One factory handles both via `mode`.
    Args:
        mode: Either `tailor` (the default initial pass) or `trim` (the
            page-fit shortening pass).
        model: Optional ADK-compatible model implementation for testing;
            when omitted the OpenAI LiteLLM model is constructed.
    Output:
        Returns a configured ADK `Agent`.
    Raises:
        ValueError: When `mode` is not one of `tailor` / `trim`.
    """

    if mode not in ("tailor", "trim"):
        raise ValueError(f"Unknown tailor agent mode {mode!r}")

    instruction = TAILOR_INSTRUCTION if mode == "tailor" else TRIM_INSTRUCTION
    effective_model = (
        model
        if model is not None
        else build_openai_litellm_model(model_name=get_tailor_model_name())
    )
    return Agent(
        name=f"resume_tailor_{mode}",
        description=f"Resume {mode} agent — emits JSON bullet edits.",
        model=effective_model,
        instruction=instruction,
    )


def build_reviewer_agent(*, model: Optional[Any] = None) -> Agent:
    """Build the reviewer agent.

    Purpose:
        Score base and tailored variants and pick the final one. The same
        agent handles both the 2-way (base vs v1) and 3-way (base vs v1 vs
        v2) comparisons — the user message tells it which.
    Args:
        model: Optional ADK-compatible model implementation for testing;
            when omitted the OpenAI LiteLLM model is constructed.
    Output:
        Returns a configured ADK `Agent`.
    """

    effective_model = (
        model
        if model is not None
        else build_openai_litellm_model(model_name=get_reviewer_model_name())
    )
    return Agent(
        name="resume_tailor_reviewer",
        description="Resume reviewer — picks the best variant for one job posting.",
        model=effective_model,
        instruction=REVIEWER_INSTRUCTION,
    )


def _extract_event_text(event: object) -> str:
    """Pull plain text out of one ADK event.

    Purpose:
        Mirror the helper used by `root_apply_decider` so streaming and
        final responses are concatenated identically.
    Args:
        event: ADK event emitted by `Runner.run_async`.
    Output:
        Returns the concatenated text content, or `""` when the event
        carries no plain text parts.
    """

    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None)
    if not parts:
        return ""

    text_parts: list[str] = []
    for part in parts:
        part_text = getattr(part, "text", None)
        if part_text:
            text_parts.append(part_text)
    return "".join(text_parts)


async def run_agent_once(*, agent: BaseAgent, user_message: str) -> str:
    """Run one ADK agent invocation and return the model's final text.

    Purpose:
        Provide a single-call helper for the tailor, trim, and reviewer
        stages so `pipeline.py` does not duplicate ADK session boilerplate.
    Args:
        agent: Configured ADK agent.
        user_message: User-role message to send for this invocation.
    Output:
        Returns the concatenated raw text response from the model.
    Raises:
        RuntimeError: When the model returns no text at all.
    """

    # google-adk currently lacks strict type hints for this constructor.
    session_service = InMemorySessionService()  # type: ignore[no-untyped-call]
    app_name = "resume_tailor_adk"
    user_id = "worker"
    session_id = str(uuid.uuid4())

    await session_service.create_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
        state={},
    )

    runner = Runner(agent=agent, app_name=app_name, session_service=session_service)
    final_text = ""
    fragments: list[str] = []

    try:
        new_message = types.Content(
            role="user",
            parts=[types.Part(text=user_message)],
        )
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=new_message,
        ):
            event_text = _extract_event_text(event)
            if not event_text:
                continue
            fragments.append(event_text)
            if getattr(event, "partial", False):
                continue
            if hasattr(event, "is_final_response") and event.is_final_response():
                final_text = event_text
    finally:
        # google-adk currently lacks strict type hints for this method.
        await runner.close()  # type: ignore[no-untyped-call]

    response_text = final_text or "".join(fragments).strip()
    if not response_text:
        raise RuntimeError("Model returned no text response")
    return response_text


def extract_first_json_object(raw_response: str) -> Optional[dict[str, Any]]:
    """Recover the first top-level JSON object embedded in a response.

    Purpose:
        Survive providers that prepend or append stray tokens around the
        JSON payload. Mirrors `root_apply_decider.agent._extract_first_json_object`.
    Args:
        raw_response: Full raw model response.
    Output:
        Returns the parsed JSON object as a dict, or `None` when no
        complete object can be recovered.
    """

    response_text = raw_response.strip()
    if not response_text:
        return None
    try:
        parsed = json.loads(response_text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for start_index, character in enumerate(response_text):
        if character != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(response_text[start_index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None
