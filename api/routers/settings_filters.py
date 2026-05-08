"""Filters and sources YAML settings router."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
import yaml

from api.config import SETTINGS_COMPANIES_PATH
from api.config import SETTINGS_FILTERS_PATH
from api.errors import _raise_api_error
from api.schemas.common import YamlPayload
from api.services.yaml_files import _backup_settings_file
from api.services.yaml_files import _resolve_settings_file_metadata

router = APIRouter(prefix="/api/settings", tags=["settings-filters"])


@router.get("/filters")
async def get_filters() -> JSONResponse:
    """Read the current filters.yaml configuration.

    Returns:
        JSON with the parsed filters config and file metadata.
    """
    if not SETTINGS_FILTERS_PATH.exists():
        return JSONResponse({"ok": True, "yaml_text": "", "data": {}})

    yaml_text = SETTINGS_FILTERS_PATH.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError:
        data = {}

    return JSONResponse(
        {
            "ok": True,
            "yaml_text": yaml_text,
            "data": data,
            "metadata": _resolve_settings_file_metadata(SETTINGS_FILTERS_PATH),
        }
    )


@router.put("/filters")
async def put_filters(payload: YamlPayload) -> JSONResponse:
    """Write the filters.yaml configuration.

    Args:
        payload: Contains the raw YAML text to persist.

    Returns:
        JSON confirming the write with updated metadata.
    """
    # Validate that the YAML is parseable before saving.
    try:
        data = yaml.safe_load(payload.yaml_text)
        if data is not None and not isinstance(data, dict):
            _raise_api_error(
                status_code=400,
                code="INVALID_YAML",
                message="Filters config must be a YAML mapping.",
            )
    except yaml.YAMLError as exc:
        _raise_api_error(
            status_code=400,
            code="INVALID_YAML",
            message=f"Invalid YAML: {exc}",
        )

    _backup_settings_file(SETTINGS_FILTERS_PATH, file_label="Filters")
    SETTINGS_FILTERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILTERS_PATH.write_text(payload.yaml_text, encoding="utf-8")

    return JSONResponse(
        {
            "ok": True,
            "metadata": _resolve_settings_file_metadata(SETTINGS_FILTERS_PATH),
        }
    )


@router.get("/sources")
async def get_sources() -> JSONResponse:
    """Read the current companies.yaml source configuration.

    Returns:
        JSON with the parsed sources config and file metadata.
    """
    if not SETTINGS_COMPANIES_PATH.exists():
        return JSONResponse({"ok": True, "yaml_text": "", "data": {}})

    yaml_text = SETTINGS_COMPANIES_PATH.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError:
        data = {}

    return JSONResponse(
        {
            "ok": True,
            "yaml_text": yaml_text,
            "data": data,
            "metadata": _resolve_settings_file_metadata(SETTINGS_COMPANIES_PATH),
        }
    )


@router.put("/sources")
async def put_sources(payload: YamlPayload) -> JSONResponse:
    """Write the companies.yaml source configuration.

    Args:
        payload: Contains the raw YAML text to persist.

    Returns:
        JSON confirming the write with updated metadata.
    """
    try:
        data = yaml.safe_load(payload.yaml_text)
        if data is not None and not isinstance(data, dict):
            _raise_api_error(
                status_code=400,
                code="INVALID_YAML",
                message="Sources config must be a YAML mapping.",
            )
    except yaml.YAMLError as exc:
        _raise_api_error(
            status_code=400,
            code="INVALID_YAML",
            message=f"Invalid YAML: {exc}",
        )

    _backup_settings_file(SETTINGS_COMPANIES_PATH, file_label="Sources")
    SETTINGS_COMPANIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_COMPANIES_PATH.write_text(payload.yaml_text, encoding="utf-8")

    return JSONResponse(
        {
            "ok": True,
            "metadata": _resolve_settings_file_metadata(SETTINGS_COMPANIES_PATH),
        }
    )
