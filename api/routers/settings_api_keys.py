"""Settings router for API keys and service tier configuration."""

from __future__ import annotations

from fastapi import APIRouter

from src.database.db_manager import DatabaseManager

from api.config import ALLOWED_API_KEY_NAMES
from api.config import ALLOWED_SERVICE_TIERS
from api.errors import _raise_api_error
from api.schemas.common import ApiKeyUpsertRequest
from api.schemas.common import ServiceTierUpdateRequest
from api.services.env_keys import _build_api_keys_response
from api.services.env_keys import _delete_env_key
from api.services.env_keys import _write_env_key

router = APIRouter(prefix="/api/settings", tags=["settings-api-keys"])


@router.get("/api-keys")
async def get_api_keys() -> dict[str, object]:
    """Return configured status for all allowed API key names.

    Purpose:
        Drive the settings UI key list without exposing secret values.
    Args:
        None.
    Output:
        Returns ok + keys list with name and configured flag per entry.
    """

    return _build_api_keys_response()


@router.put("/api-keys/{key_name}")
async def upsert_api_key(
    key_name: str, payload: ApiKeyUpsertRequest
) -> dict[str, object]:
    """Add or replace one API key secret in the project .env file.

    Purpose:
        Persist user-supplied API key secrets durably so the pipeline worker
        picks them up on next run.
    Args:
        key_name: Environment variable name from the URL path.
        payload: Parsed request body with the new secret value.
    Output:
        Returns updated API key status payload.
    Raises:
        HTTPException 400: When key_name is not in the allowed set.
    """

    if key_name not in ALLOWED_API_KEY_NAMES:
        _raise_api_error(
            status_code=400,
            code="UNKNOWN_API_KEY",
            message=f"'{key_name}' is not a supported API key name.",
        )
    _write_env_key(key_name, payload.value.strip())
    return _build_api_keys_response()


@router.delete("/api-keys/{key_name}")
async def delete_api_key(key_name: str) -> dict[str, object]:
    """Remove one API key entry from the project .env file.

    Purpose:
        Allow users to fully revoke a stored key from the settings UI.
    Args:
        key_name: Environment variable name from the URL path.
    Output:
        Returns updated API key status payload.
    Raises:
        HTTPException 400: When key_name is not in the allowed set.
    """

    if key_name not in ALLOWED_API_KEY_NAMES:
        _raise_api_error(
            status_code=400,
            code="UNKNOWN_API_KEY",
            message=f"'{key_name}' is not a supported API key name.",
        )
    _delete_env_key(key_name)
    return _build_api_keys_response()


@router.get("/service-tier")
async def get_service_tier() -> dict[str, object]:
    """Return the currently active service tier.

    Purpose:
        Let the settings UI pre-select the correct tier card on load.
    Args:
        None.
    Output:
        Returns ok + tier string.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    db_path = str(_main.resolve_database_path())
    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        await db.migrate_cost_schema()
        tier = await db.get_service_tier()
    return {"ok": True, "tier": tier}


@router.put("/service-tier")
async def update_service_tier(payload: ServiceTierUpdateRequest) -> dict[str, object]:
    """Persist the selected service tier.

    Purpose:
        Keep the active pipeline tier durable so worker scripts respect the
        user's chosen automation level on their next run.
    Args:
        payload: Parsed request body with the new tier identifier.
    Output:
        Returns ok + updated tier string.
    Raises:
        HTTPException 400: When the requested tier is not a valid identifier.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    if payload.tier not in ALLOWED_SERVICE_TIERS:
        _raise_api_error(
            status_code=400,
            code="UNKNOWN_SERVICE_TIER",
            message=f"'{payload.tier}' is not a valid service tier.",
        )
    db_path = str(_main.resolve_database_path())
    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        await db.migrate_cost_schema()
        tier = await db.set_service_tier(payload.tier)
    return {"ok": True, "tier": tier}
