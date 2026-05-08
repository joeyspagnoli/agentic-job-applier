"""AI provider and onboarding-status settings router (OpenAI BYOK only).

This release narrows the provider surface to OpenAI BYOK only. Codex device
auth and other BYOK providers (Anthropic, Gemini, OpenRouter) are tracked for
future support under issue #35 and are intentionally rejected at the API
boundary so contributors get a clear error instead of partial behavior.
"""

from __future__ import annotations

import os
from typing import Final

from fastapi import APIRouter
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from api.config import SETTINGS_PROFILE_PATH
from api.config import SETTINGS_RESUME_PATH
from api.errors import _raise_api_error
from api.services.env_keys import _write_env_key

router = APIRouter(prefix="/api/settings", tags=["settings-provider"])

# Provider identifier for the only currently supported BYOK provider.
PROVIDER_OPENAI: Final[str] = "openai"

# Environment variable that stores the OpenAI BYOK key on disk.
OPENAI_ENV_KEY_NAME: Final[str] = "OPENAI_API_KEY"

# Providers that the API explicitly rejects in this release.
UNSUPPORTED_PROVIDERS: Final[frozenset[str]] = frozenset(
    {
        "anthropic",
        "gemini",
        "openrouter",
        "codex",
    }
)

# Stable, user-facing message returned for any non-OpenAI provider request.
UNSUPPORTED_PROVIDER_MESSAGE: Final[str] = (
    "Only OpenAI is supported in this release. "
    "Track issue #35 for wider BYOK support."
)


class ProviderWriteRequest(BaseModel):
    """Request body for the OpenAI-only provider write endpoint.

    Attributes:
        provider_type: Provider identifier; must be "openai" for this release.
        api_key: BYOK secret to persist to the project .env file.
    """

    model_config = ConfigDict(extra="ignore")

    provider_type: str = Field(
        default=PROVIDER_OPENAI,
        description="Currently must be 'openai'; see issue #35.",
    )
    api_key: str | None = Field(
        default=None,
        description="OpenAI BYOK key, e.g. 'sk-...'.",
    )


@router.get("/ai-provider")
async def get_ai_provider() -> dict[str, object]:
    """Return the current AI provider configuration.

    Purpose:
        Drive the settings UI's provider status row so the user can see whether
        an OpenAI BYOK key is currently configured.
    Args:
        None.
    Returns:
        JSON describing the active provider and whether an OpenAI key is set.
    """

    has_openai = bool(os.environ.get(OPENAI_ENV_KEY_NAME))
    return {
        "ok": True,
        "config": {
            "mode": "byok",
            "providerType": PROVIDER_OPENAI if has_openai else "none",
            "hasOpenaiKey": has_openai,
        },
    }


@router.post("/provider")
async def post_provider(payload: ProviderWriteRequest) -> dict[str, object]:
    """Persist a BYOK API key for the requested provider type.

    Purpose:
        Accept the OpenAI BYOK key from onboarding and write it to the project
        .env file. All other provider types are rejected with a stable error
        body so contributors and frontend agents get a clear signal.
    Args:
        payload: Provider configuration submitted by the settings UI.
    Returns:
        JSON confirming the configuration update on success.
    Raises:
        HTTPException: 400 when provider_type is not "openai" or api_key is
            missing.
    """

    provider_type = (payload.provider_type or "").strip().lower()
    if provider_type != PROVIDER_OPENAI:
        _raise_api_error(
            status_code=400,
            code="UNSUPPORTED_PROVIDER",
            message=UNSUPPORTED_PROVIDER_MESSAGE,
            details={"provider_type": provider_type},
        )

    api_key = (payload.api_key or "").strip()
    if not api_key:
        _raise_api_error(
            status_code=400,
            code="MISSING_API_KEY",
            message="api_key is required when provider_type is 'openai'.",
        )

    _write_env_key(OPENAI_ENV_KEY_NAME, api_key)

    return {
        "ok": True,
        "mode": "byok",
        "provider": PROVIDER_OPENAI,
    }


@router.get("/onboarding-status")
async def get_onboarding_status() -> dict[str, object]:
    """Check whether the user has completed initial onboarding.

    Purpose:
        Tell the dashboard whether the profile and resume seed steps are done
        so it can show the onboarding wizard or main UI accordingly.
    Args:
        None.
    Returns:
        JSON with completion state and per-step details.
    """

    profile_has_content = _profile_has_content()

    completed_steps: list[str] = []
    missing_steps: list[str] = []

    if profile_has_content:
        completed_steps.append("profile")
    else:
        missing_steps.append("profile")

    if SETTINGS_RESUME_PATH.exists():
        completed_steps.append("resume")
    else:
        missing_steps.append("resume")

    is_complete = "profile" in completed_steps and "resume" in completed_steps

    return {
        "ok": True,
        "is_complete": is_complete,
        "completed_steps": completed_steps,
        "missing_steps": missing_steps,
    }


def _profile_has_content() -> bool:
    """Return True when the candidate profile YAML has substantive content.

    Purpose:
        Avoid treating an empty placeholder profile YAML as a completed step.
    Args:
        None.
    Returns:
        True when the profile file exists and contains more than 50 bytes of
        non-whitespace text; False otherwise.
    """

    if not SETTINGS_PROFILE_PATH.exists():
        return False
    try:
        content = SETTINGS_PROFILE_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    return len(content) > 50
