"""Shared model helpers for ADK agents.

This module centralizes small model-construction helpers so future custom
agents can share the same credential checks and LiteLLM setup behavior.
"""

from __future__ import annotations

import os
from typing import Any


def build_openai_litellm_model(*, model_name: str, temperature: float) -> Any:
    """Build an OpenAI-backed LiteLLM model for ADK agents.

    Purpose:
        Keep OpenAI credential validation and LiteLLM import handling in one
        place so each agent package does not duplicate this wiring.
    Args:
        model_name: Fully qualified LiteLLM model string such as `openai/gpt-5-mini`.
        temperature: Sampling temperature to pass into LiteLLM.
    Output:
        Returns a configured LiteLLM model instance compatible with ADK.
    """

    # OpenAI-backed runs should fail fast when the required credential is
    # missing so scripts do not quietly process zero jobs.
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set for the decider model.")

    try:
        from google.adk.models.lite_llm import LiteLlm
    except ImportError as exc:
        raise RuntimeError(
            "LiteLLM support is not installed. Add `litellm` or install "
            "`google-adk[extensions]` before running agent workflows."
        ) from exc

    return LiteLlm(model=model_name, temperature=temperature)
