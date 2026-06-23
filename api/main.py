"""Expose FastAPI endpoints and static dashboard serving for the project.

This module provides the unified runtime boundary for the dashboard product:
- `/api/*` JSON endpoints backed by SQLite (delegated to `api.routers.*`)
- Static serving for built React assets in `dashboard/dist`
- SPA fallback for client-side routing
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse

from src.utils.llm_pricing import register_custom_prices
from src.utils.paths import resolve_database_path

# Ensure litellm.cost_per_token() returns this codebase's authoritative
# per-model rates regardless of the installed litellm version.
register_custom_prices()

from api.config import DASHBOARD_ASSETS_DIR
from api.config import DASHBOARD_INDEX_FILE
from api.config import SETTINGS_BACKUPS_DIR
from api.config import SETTINGS_PROFILE_PATH
from api.config import SETTINGS_RESUME_PATH
from api.errors import _error_response
from api.errors import _raise_api_error
from api.services.migrations import _lifespan
from api.services.sources import _source_label
from api.services.system_scripts import _dispatch_system_lifecycle_action
from api.services.yaml_files import _backup_settings_file

from api.routers import costs as costs_router
from api.routers import digest as digest_router
from api.routers import dashboard as dashboard_router
from api.routers import failures as failures_router
from api.routers import health as health_router
from api.routers import human_review as human_review_router
from api.routers import jobs as jobs_router
from api.routers import pipeline as pipeline_router
from api.routers import settings_api_keys as settings_api_keys_router
from api.routers import settings_budget as settings_budget_router
from api.routers import settings_files as settings_files_router
from api.routers import settings_filters as settings_filters_router
from api.routers import settings_profile as settings_profile_router
from api.routers import settings_provider as settings_provider_router
from api.routers import settings_resume as settings_resume_router
from api.routers import status as status_router
from api.routers import system as system_router
from api.routers import system_settings as system_settings_router
from api.routers import apply_runs as apply_runs_router
from api.routers import tailor_runs as tailor_runs_router

logger = logging.getLogger(__name__)


_DIGEST_HOST_MARKER = "jobs.joeyspagnoli-cloud"
_DIGEST_ALLOWED_PREFIXES = ("/subscribe", "/manage", "/api/digest/", "/favicon", "/apple-touch-icon")


class _DigestSubdomainGuard(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: object
    ) -> StarletteResponse:
        host = request.headers.get("host", "")
        if _DIGEST_HOST_MARKER in host:
            path = request.url.path
            if path == "/":
                return RedirectResponse("/subscribe", status_code=302)
            if not any(path.startswith(p) for p in _DIGEST_ALLOWED_PREFIXES):
                return JSONResponse(status_code=404, content={"detail": "Not found"})
        return await call_next(request)


app = FastAPI(lifespan=_lifespan)
app.add_middleware(_DigestSubdomainGuard)

if DASHBOARD_ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=DASHBOARD_ASSETS_DIR), name="assets")

app.include_router(digest_router.router)
app.include_router(digest_router.pages_router)
app.include_router(health_router.router)
app.include_router(system_router.router)
app.include_router(costs_router.router)
app.include_router(dashboard_router.router)
app.include_router(failures_router.router)
app.include_router(human_review_router.router)
app.include_router(jobs_router.router)
app.include_router(pipeline_router.router)
app.include_router(settings_api_keys_router.router)
app.include_router(settings_budget_router.router)
app.include_router(settings_files_router.router)
app.include_router(settings_filters_router.router)
app.include_router(settings_profile_router.router)
app.include_router(settings_provider_router.router)
app.include_router(settings_resume_router.router)
app.include_router(status_router.router)
app.include_router(system_settings_router.router)
app.include_router(apply_runs_router.router)
app.include_router(tailor_runs_router.router)


@app.exception_handler(HTTPException)
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


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str) -> FileResponse:
    """Serve React dashboard index for all non-API browser routes.

    Purpose:
        Support direct deep-link navigation for SPA routes while keeping API
        endpoints under `/api/*` untouched.
    Args:
        full_path: Arbitrary browser path requested by client.
    Output:
        Returns `dashboard/dist/index.html` when available.
    Raises:
        HTTPException: When dashboard assets have not been built yet.
    """

    if full_path.startswith("api/"):
        _raise_api_error(
            status_code=404,
            code="API_ROUTE_NOT_FOUND",
            message="Requested API route was not found.",
        )

    if not DASHBOARD_INDEX_FILE.exists():
        _raise_api_error(
            status_code=404,
            code="DASHBOARD_BUILD_MISSING",
            message=(
                "Dashboard build is missing. Run 'npm run build' in the "
                "dashboard directory first."
            ),
        )

    return FileResponse(DASHBOARD_INDEX_FILE)


__all__ = [
    "SETTINGS_BACKUPS_DIR",
    "SETTINGS_PROFILE_PATH",
    "SETTINGS_RESUME_PATH",
    "_backup_settings_file",
    "_dispatch_system_lifecycle_action",
    "_source_label",
    "app",
    "resolve_database_path",
]
