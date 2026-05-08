"""Centralized API error helpers and HTTPException handler body.

These helpers keep error response shape consistent across all routers and
centralize FastAPI HTTPException raising. The actual `@app.exception_handler`
decorator registration lives in `api.main`; this module exposes the handler
function body so it can be wired up there.
"""

from __future__ import annotations

from typing import NoReturn

from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import JSONResponse


def _error_response(
    *,
    code: str,
    message: str,
    details: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build one deterministic API error payload.

    Purpose:
        Keep every endpoint error response shape consistent for frontend
        consumers and deterministic integration tests.
    Args:
        code: Stable machine-readable error code.
        message: Human-readable error summary.
        details: Optional structured details for debugging or UI hints.
    Output:
        Returns a dictionary payload with `ok`, `code`, `message`, and `details`.
    """

    return {
        "ok": False,
        "code": code,
        "message": message,
        "details": details or {},
    }


def _raise_api_error(
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, object] | None = None,
) -> NoReturn:
    """Raise an HTTPException with the project's standard error payload.

    Purpose:
        Centralize FastAPI error raising so route handlers stay focused on
        business logic and all errors share the same response contract.
    Args:
        status_code: HTTP status code for the response.
        code: Stable machine-readable error code.
        message: Human-readable error message.
        details: Optional structured details payload.
    Output:
        Raises `HTTPException` and does not return.
    """

    raise HTTPException(
        status_code=status_code,
        detail=_error_response(code=code, message=message, details=details),
    )


async def _http_exception_handler(
    _request: Request,
    exc: HTTPException,
) -> JSONResponse:
    """Render HTTP exceptions in the project's deterministic JSON format.

    Purpose:
        Normalize route-raised HTTP exceptions so frontend consumers always
        receive consistent error payload keys.
    Args:
        _request: Starlette request object supplied by the framework.
        exc: HTTPException raised by a route handler.
    Output:
        Returns JSONResponse containing the normalized error payload.
    """

    if isinstance(exc.detail, dict):
        detail_payload = exc.detail
    else:
        detail_payload = _error_response(
            code="HTTP_ERROR",
            message=str(exc.detail),
            details={},
        )
    return JSONResponse(status_code=exc.status_code, content=detail_payload)
