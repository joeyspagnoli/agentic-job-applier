"""Profile-related settings router (read/write/upload/download)."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi import File
from fastapi import UploadFile
from fastapi.responses import FileResponse

from src.agents.root_apply_decider.prompts import load_candidate_context

from api.errors import _raise_api_error
from api.schemas.candidate import ProfileStructuredUpdateRequest
from api.schemas.common import YamlTextUpdateRequest
from api.services.yaml_files import _normalize_candidate_profile_output
from api.services.yaml_files import _parse_yaml_mapping
from api.services.yaml_files import _persist_yaml_mapping
from api.services.yaml_files import _read_settings_text
from api.services.yaml_files import _read_uploaded_text
from api.services.yaml_files import _resolve_settings_file_metadata
from api.services.yaml_files import _validate_candidate_profile_document

router = APIRouter(prefix="/api/settings", tags=["settings-profile"])


@router.get("/profile")
async def get_profile_settings() -> dict[str, object]:
    """Return candidate profile settings with raw YAML and parsed fields.

    Purpose:
        Power guided and advanced profile editors from one read endpoint.
    Args:
        None.
    Output:
        Returns metadata, raw YAML text, and parsed profile payload.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    profile_path = _main.SETTINGS_PROFILE_PATH
    yaml_text = _read_settings_text(profile_path, file_label="Profile")
    parsed_payload = _parse_yaml_mapping(yaml_text=yaml_text, context="profile")
    profile_document = _validate_candidate_profile_document(parsed_payload)

    return {
        "ok": True,
        "metadata": _resolve_settings_file_metadata(profile_path),
        "yaml_text": yaml_text,
        **_normalize_candidate_profile_output(profile_document),
    }


@router.put("/profile")
async def update_profile_yaml(payload: YamlTextUpdateRequest) -> dict[str, object]:
    """Persist candidate profile settings from raw YAML text.

    Purpose:
        Support advanced YAML editing while enforcing candidate profile shape
        validation before writing config to disk.
    Args:
        payload: Raw YAML payload wrapper.
    Output:
        Returns metadata, canonical YAML text, and parsed profile payload.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    profile_path = _main.SETTINGS_PROFILE_PATH
    parsed_payload = _parse_yaml_mapping(yaml_text=payload.yaml_text, context="profile")
    profile_document = _validate_candidate_profile_document(parsed_payload)

    _main._backup_settings_file(profile_path, file_label="Profile")
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(payload.yaml_text, encoding="utf-8")
    load_candidate_context.cache_clear()

    return {
        "ok": True,
        "metadata": _resolve_settings_file_metadata(profile_path),
        "yaml_text": payload.yaml_text,
        **_normalize_candidate_profile_output(profile_document),
    }


@router.put("/profile/structured")
async def update_profile_structured(
    payload: ProfileStructuredUpdateRequest,
) -> dict[str, object]:
    """Persist candidate profile settings from guided structured fields.

    Purpose:
        Support form-first editing while preserving unknown top-level YAML keys
        outside profile/search-defaults/prompt-context.
    Args:
        payload: Structured profile update payload.
    Output:
        Returns metadata, canonical YAML text, and parsed profile payload.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    profile_path = _main.SETTINGS_PROFILE_PATH
    existing_payload: dict[str, object]
    if profile_path.exists():
        existing_text = _read_settings_text(profile_path, file_label="Profile")
        existing_payload = _parse_yaml_mapping(
            yaml_text=existing_text,
            context="profile",
        )
    else:
        existing_payload = {}

    merged_payload = dict(existing_payload)
    merged_payload["profile"] = payload.profile.model_dump(mode="json")
    merged_payload["search_defaults"] = payload.search_defaults.model_dump(mode="json")
    if payload.prompt_context is None:
        merged_payload.pop("prompt_context", None)
    else:
        merged_payload["prompt_context"] = payload.prompt_context

    profile_document = _validate_candidate_profile_document(merged_payload)
    _main._backup_settings_file(profile_path, file_label="Profile")
    persisted_yaml = _persist_yaml_mapping(
        profile_path,
        payload=merged_payload,
    )
    load_candidate_context.cache_clear()

    return {
        "ok": True,
        "metadata": _resolve_settings_file_metadata(profile_path),
        "yaml_text": persisted_yaml,
        **_normalize_candidate_profile_output(profile_document),
    }


@router.post("/profile")
async def upload_profile_file(file: UploadFile = File(...)) -> dict[str, object]:
    """Replace the candidate profile YAML and clear prompt cache.

    Purpose:
        Persist profile updates and invalidate cached candidate context used by
        gate-decider prompts.
    Args:
        file: Uploaded candidate profile YAML file.
    Output:
        Returns canonical mutation success payload with updated metadata.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    profile_path = _main.SETTINGS_PROFILE_PATH
    text = await _read_uploaded_text(file)
    parsed_payload = _parse_yaml_mapping(yaml_text=text, context="profile")
    _validate_candidate_profile_document(parsed_payload)
    _main._backup_settings_file(profile_path, file_label="Profile")
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(text, encoding="utf-8")

    load_candidate_context.cache_clear()

    return {
        "ok": True,
        "profile": _resolve_settings_file_metadata(profile_path),
    }


@router.get("/profile/download")
async def download_profile_file() -> FileResponse:
    """Download the candidate profile YAML file.

    Purpose:
        Provide settings-panel download action for current profile YAML.
    Args:
        None.
    Output:
        Returns FileResponse for `config/candidate_profile.yaml`.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    profile_path = _main.SETTINGS_PROFILE_PATH
    if not profile_path.exists():
        _raise_api_error(
            status_code=404,
            code="FILE_NOT_FOUND",
            message="Profile file does not exist.",
        )
    return FileResponse(
        profile_path,
        media_type="application/x-yaml",
        filename=profile_path.name,
    )
