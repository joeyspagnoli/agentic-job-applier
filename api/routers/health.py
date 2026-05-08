"""Health-check router for runtime liveness validation."""

from __future__ import annotations

from fastapi import APIRouter

from api.config import DEFAULT_POLLING_SECONDS

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health_check() -> dict[str, object]:
    """Return a lightweight health payload for runtime checks.

    Purpose:
        Provide a stable API liveness endpoint for local validation.
    Args:
        None.
    Output:
        Returns health status and dashboard polling interval defaults.
    """

    return {
        "ok": True,
        "status": "healthy",
        "polling_seconds": DEFAULT_POLLING_SECONDS,
    }
