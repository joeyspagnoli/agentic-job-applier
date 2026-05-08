"""Settings files-metadata router."""

from __future__ import annotations

from fastapi import APIRouter

from api.services.yaml_files import _resolve_settings_file_metadata

router = APIRouter(prefix="/api/settings", tags=["settings-files"])


@router.get("/files")
async def get_settings_files() -> dict[str, object]:
    """Return metadata for settings-managed resume and profile files.

    Purpose:
        Populate settings panel cards with real file names, timestamps, and
        size metadata.
    Args:
        None.
    Output:
        Returns metadata for resume and profile YAML files.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    return {
        "ok": True,
        "resume": _resolve_settings_file_metadata(_main.SETTINGS_RESUME_PATH),
        "profile": _resolve_settings_file_metadata(_main.SETTINGS_PROFILE_PATH),
    }
