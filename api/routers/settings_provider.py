"""AI provider, Codex device auth, and onboarding-status settings router."""

from __future__ import annotations

import os

from fastapi import APIRouter

from api.config import SETTINGS_PROFILE_PATH
from api.config import SETTINGS_RESUME_PATH
from api.errors import _raise_api_error
from api.schemas.common import ProviderConfigRequest
from api.services.env_keys import _write_env_key

router = APIRouter(prefix="/api/settings", tags=["settings-provider"])


@router.get("/ai-provider")
async def get_ai_provider() -> dict[str, object]:
    """Return the current AI provider configuration.

    Returns:
        JSON with the current provider mode, type, and auth status.
    """
    from src.providers.factory import get_codex_provider

    codex = get_codex_provider()
    codex_authenticated = codex.is_authenticated

    # Read stored config from env or defaults.
    current_mode = "codex" if codex_authenticated else "byok"

    # Detect which BYOK key is configured.
    byok_provider = "none"
    has_openai = bool(os.environ.get("OPENAI_API_KEY"))
    has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))
    has_google = bool(os.environ.get("GOOGLE_API_KEY"))
    if has_openai:
        byok_provider = "openai"
    elif has_anthropic:
        byok_provider = "anthropic"
    elif has_google:
        byok_provider = "gemini"

    return {
        "ok": True,
        "config": {
            "mode": current_mode,
            "providerType": byok_provider if current_mode == "byok" else "codex",
            "codexAuthenticated": codex_authenticated,
            "hasOpenaiKey": has_openai,
            "hasAnthropicKey": has_anthropic,
            "hasGoogleKey": has_google,
        },
    }


@router.put("/ai-provider")
async def put_ai_provider(payload: ProviderConfigRequest) -> dict[str, object]:
    """Update the AI provider configuration.

    For BYOK mode, persists the API key to the .env file.
    For Codex mode, verifies that device auth is complete.

    Args:
        payload: New provider configuration.

    Returns:
        JSON confirming the configuration update.
    """
    from src.providers.types import ProviderMode

    if payload.mode == ProviderMode.CODEX.value:
        from src.providers.factory import get_codex_provider

        codex = get_codex_provider()
        if not codex.is_authenticated:
            _raise_api_error(
                status_code=400,
                code="CODEX_NOT_AUTHENTICATED",
                message="Complete Codex device auth before selecting Codex mode.",
            )
        return {"ok": True, "mode": "codex", "provider": "codex"}

    # BYOK mode — persist the key to .env.
    key_env_map = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "gemini": "GOOGLE_API_KEY",
        "openrouter": "OPENAI_API_KEY",
    }
    env_key_name = key_env_map.get(payload.provider_type)
    if not env_key_name:
        _raise_api_error(
            status_code=400,
            code="INVALID_PROVIDER",
            message=f"Unsupported provider type: {payload.provider_type}",
        )

    if not payload.api_key:
        _raise_api_error(
            status_code=400,
            code="MISSING_API_KEY",
            message="API key is required for BYOK mode.",
        )

    _write_env_key(env_key_name, payload.api_key.strip())

    # For OpenRouter, also persist the base URL.
    if payload.provider_type == "openrouter" and payload.base_url:
        _write_env_key("OPENROUTER_BASE_URL", payload.base_url.strip())

    return {
        "ok": True,
        "mode": "byok",
        "provider": payload.provider_type,
    }


@router.post("/codex-auth/start")
async def start_codex_auth() -> dict[str, object]:
    """Initiate the Codex OAuth device authorization flow.

    Returns:
        JSON with the verification URL and one-time user code.
    """
    from src.providers.factory import get_codex_provider

    codex = get_codex_provider()

    try:
        snapshot = await codex.start_device_auth()
        return {"ok": True, "auth": snapshot.to_dict()}
    except Exception as exc:
        _raise_api_error(
            status_code=500,
            code="CODEX_AUTH_FAILED",
            message=str(exc),
        )


@router.get("/codex-auth/status")
async def get_codex_auth_status() -> dict[str, object]:
    """Return the current Codex device auth session status.

    Returns:
        JSON with the auth snapshot (status, URL, code, expiry).
    """
    from src.providers.factory import get_codex_provider

    codex = get_codex_provider()
    snapshot = codex.get_auth_snapshot()
    return {"ok": True, "auth": snapshot.to_dict()}


@router.post("/codex-auth/disconnect")
async def disconnect_codex_auth() -> dict[str, object]:
    """Log out of Codex and clear the active session.

    Returns:
        JSON confirming the logout with an idle auth snapshot.
    """
    from src.providers.factory import get_codex_provider

    codex = get_codex_provider()

    try:
        snapshot = await codex.disconnect()
        return {"ok": True, "auth": snapshot.to_dict()}
    except Exception as exc:
        _raise_api_error(
            status_code=500,
            code="CODEX_DISCONNECT_FAILED",
            message=str(exc),
        )


@router.get("/onboarding-status")
async def get_onboarding_status() -> dict[str, object]:
    """Check whether the user has completed initial onboarding.

    Returns:
        JSON with completion state and step details.
    """
    profile_path = SETTINGS_PROFILE_PATH
    profile_exists = profile_path.exists()
    profile_has_content = False

    if profile_exists:
        try:
            content = profile_path.read_text(encoding="utf-8").strip()
            profile_has_content = len(content) > 50
        except OSError:
            pass

    completed_steps: list[str] = []
    missing_steps: list[str] = []

    if profile_has_content:
        completed_steps.append("profile")
    else:
        missing_steps.append("profile")

    resume_path = SETTINGS_RESUME_PATH
    if resume_path.exists():
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
