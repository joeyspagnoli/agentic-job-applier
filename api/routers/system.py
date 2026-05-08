"""System lifecycle router (stop, restart, fetch-jobs, health)."""

from __future__ import annotations

import os

from fastapi import APIRouter
from pydantic import BaseModel
from pydantic import Field

from api.config import SYSTEM_ACTION_FETCH_JOBS
from api.config import SYSTEM_ACTION_RESTART
from api.config import SYSTEM_ACTION_STATUS_ACCEPTED
from api.config import SYSTEM_ACTION_STOP
from api.errors import _raise_api_error
from api.services.env_keys import ENV_KEY_PLACEHOLDER_VALUES

router = APIRouter(prefix="/api/system", tags=["system"])


class SystemHealthResponse(BaseModel):
    """Response payload for `GET /api/system/health`.

    Purpose:
        Surface lightweight runtime configuration signals that the dashboard
        can use to render banners and disable broken actions when the
        environment is mis-configured.
    """

    ok: bool = Field(
        default=True,
        description="True when the API process is running and able to answer.",
    )
    openai_key_configured: bool = Field(
        ...,
        description=(
            "True when the `OPENAI_API_KEY` environment variable is non-empty. "
            "When false, the gate, tailor, and review workers idle and the "
            "dashboard renders a missing-key banner."
        ),
    )


def _is_openai_key_configured() -> bool:
    """Return True when `OPENAI_API_KEY` is set to a non-placeholder value.

    Purpose:
        Centralize the "is the key set" check so the health endpoint, tests,
        and any future caller use one consistent definition. A key counts as
        configured only when it is non-empty after whitespace stripping AND
        not one of the sentinel placeholder strings shipped in `.env.example`.
    Args:
        None.
    Output:
        Returns True when the env var is set and is not a placeholder; False
        otherwise.
    """

    raw_value = os.environ.get("OPENAI_API_KEY", "").strip()
    return raw_value != "" and raw_value not in ENV_KEY_PLACEHOLDER_VALUES


@router.get("/health", response_model=SystemHealthResponse)
async def system_health() -> SystemHealthResponse:
    """Report runtime configuration signals used by the dashboard.

    Purpose:
        Provide a single endpoint the dashboard polls to detect missing
        provider keys so it can render warning banners without coupling
        to the secrets-write API.
    Args:
        None.
    Output:
        Returns a `SystemHealthResponse` with `openai_key_configured` set
        based on the live `OPENAI_API_KEY` environment variable.
    """

    return SystemHealthResponse(
        ok=True,
        openai_key_configured=_is_openai_key_configured(),
    )


@router.post("/stop")
async def stop_system_stack() -> dict[str, object]:
    """Dispatch a non-destructive full stack stop operation.

    Purpose:
        Allow dashboard users to stop the running compose stack through one API
        action instead of manual shell commands.
    Args:
        None.
    Output:
        Returns accepted payload with request identifier.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    try:
        request_id = _main._dispatch_system_lifecycle_action(SYSTEM_ACTION_STOP)
    except OSError as exc:
        _raise_api_error(
            status_code=500,
            code="SYSTEM_ACTION_DISPATCH_FAILED",
            message="Failed to dispatch system stop action.",
            details={"action": SYSTEM_ACTION_STOP, "error": str(exc)},
        )

    return {
        "ok": True,
        "action": SYSTEM_ACTION_STOP,
        "status": SYSTEM_ACTION_STATUS_ACCEPTED,
        "request_id": request_id,
    }


@router.post("/restart")
async def restart_system_stack() -> dict[str, object]:
    """Dispatch a full stack restart operation.

    Purpose:
        Allow dashboard users to restart the compose stack through one API
        action instead of running stop and start commands manually.
    Args:
        None.
    Output:
        Returns accepted payload with request identifier.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    try:
        request_id = _main._dispatch_system_lifecycle_action(SYSTEM_ACTION_RESTART)
    except OSError as exc:
        _raise_api_error(
            status_code=500,
            code="SYSTEM_ACTION_DISPATCH_FAILED",
            message="Failed to dispatch system restart action.",
            details={"action": SYSTEM_ACTION_RESTART, "error": str(exc)},
        )

    return {
        "ok": True,
        "action": SYSTEM_ACTION_RESTART,
        "status": SYSTEM_ACTION_STATUS_ACCEPTED,
        "request_id": request_id,
    }


@router.post("/fetch-jobs")
async def fetch_jobs_now() -> dict[str, object]:
    """Dispatch an immediate discovery run by restarting the discovery container.

    Purpose:
        Allow users to trigger on-demand job discovery without restarting the
        full stack. Restarting only the discovery container causes `run_discovery.sh`
        to execute `main.py` immediately before sleeping, so new jobs appear
        within seconds rather than waiting for the 30-minute polling interval.
    Output:
        Returns accepted payload with request identifier.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    try:
        request_id = _main._dispatch_system_lifecycle_action(SYSTEM_ACTION_FETCH_JOBS)
    except OSError as exc:
        _raise_api_error(
            status_code=500,
            code="SYSTEM_ACTION_DISPATCH_FAILED",
            message="Failed to dispatch discovery fetch action.",
            details={"action": SYSTEM_ACTION_FETCH_JOBS, "error": str(exc)},
        )

    return {
        "ok": True,
        "action": SYSTEM_ACTION_FETCH_JOBS,
        "status": SYSTEM_ACTION_STATUS_ACCEPTED,
        "request_id": request_id,
    }
