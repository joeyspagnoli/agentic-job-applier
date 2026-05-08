"""System lifecycle router (stop, restart, fetch-jobs)."""

from __future__ import annotations

from fastapi import APIRouter

from api.config import SYSTEM_ACTION_FETCH_JOBS
from api.config import SYSTEM_ACTION_RESTART
from api.config import SYSTEM_ACTION_STATUS_ACCEPTED
from api.config import SYSTEM_ACTION_STOP
from api.errors import _raise_api_error

router = APIRouter(prefix="/api/system", tags=["system"])


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
