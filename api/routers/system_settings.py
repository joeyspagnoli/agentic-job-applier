"""System settings router (per-stage automation modes).

Backs the Settings page Automation card. Reads and writes
`automation.tailor_mode` in the `system_settings` table; the worker
re-reads it on every poll cycle so flips here take effect without a
process restart.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.database._mixins.system_settings import (
    AUTOMATION_MODES,
    TAILOR_MODE_KEY,
)
from src.database.db_manager import DatabaseManager

from api.errors import _raise_api_error

router = APIRouter(prefix="/api/system-settings", tags=["system-settings"])

_VALID_MODES: frozenset[str] = frozenset(AUTOMATION_MODES)


class AutomationModePatch(BaseModel):
    """Optional patch payload for the automation-mode endpoint.

    Purpose:
        Allow callers to update the tailor automation mode without
        forcing them to re-send the unchanged value.
    """

    tailor_mode: Optional[str] = Field(default=None)


def _validate_mode(field: str, value: str) -> str:
    """Validate one automation-mode field or raise an API error.

    Purpose:
        Guard the PATCH path so a typo in the request body cannot leak
        an unsupported value into the database.
    Args:
        field: Field name surfaced in error messages.
        value: Candidate mode string from the request body.
    Output:
        Returns the normalized lowercased mode string.
    Raises:
        HTTPException: 422 when the mode is not in the allowed set.
    """

    normalized = value.strip().lower()
    if normalized not in _VALID_MODES:
        _raise_api_error(
            status_code=422,
            code="INVALID_AUTOMATION_MODE",
            message=f"Invalid value for {field}; must be one of {sorted(_VALID_MODES)}",
            details={"field": field, "value": value},
        )
    return normalized


@router.get("/automation")
async def get_automation_settings() -> dict[str, object]:
    """Return the current tailor automation mode.

    Purpose:
        Render the Settings page Automation card and let the dashboard
        decide whether to show the JobsPage `[Tailor resume]` button.
    Args:
        None.
    Output:
        Returns `{ok: True, tailor_mode}`.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    db_path = str(_main.resolve_database_path())
    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        tailor_mode = await db.get_automation_mode(TAILOR_MODE_KEY)

    return {
        "ok": True,
        "tailor_mode": tailor_mode,
    }


@router.patch("/automation")
async def patch_automation_settings(payload: AutomationModePatch) -> dict[str, object]:
    """Update the tailor automation mode.

    Purpose:
        Persist the user's Automation-card choice. A request that sets
        no fields is a no-op and returns the current snapshot.
    Args:
        payload: Optional new value for `tailor_mode`.
    Output:
        Returns `{ok: True, tailor_mode}` reflecting the post-write
        state.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    db_path = str(_main.resolve_database_path())
    async with DatabaseManager(db_path) as db:
        await db.create_tables()

        if payload.tailor_mode is not None:
            normalized = _validate_mode("tailor_mode", payload.tailor_mode)
            await db.set_automation_mode(TAILOR_MODE_KEY, normalized)

        tailor_mode = await db.get_automation_mode(TAILOR_MODE_KEY)

    return {
        "ok": True,
        "tailor_mode": tailor_mode,
    }
