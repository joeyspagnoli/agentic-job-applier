"""YAML file read/write/backup helpers for settings endpoints."""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from datetime import UTC
from datetime import datetime
from pathlib import Path
from typing import cast

import yaml
from fastapi import UploadFile
from pydantic import ValidationError

from src.agents.resume_tailor_adk.schemas import ResumeContent
from src.agents.resume_tailor_adk.schemas import validate_locked_structure

from api.config import SETTINGS_BACKUP_FILE_LIMIT
from api.config import SETTINGS_BACKUP_TIMESTAMP_FORMAT
from api.errors import _raise_api_error
from api.schemas.candidate import CandidateProfileDocumentPayload


def _resolve_backups_dir() -> Path:
    """Resolve the active settings-backups directory, honoring test overrides.

    Purpose:
        Look up `SETTINGS_BACKUPS_DIR` from `api.main` at call time so tests
        that monkeypatch the value on the main module continue to control
        backup file placement.
    Args:
        None.
    Output:
        Returns the current absolute backups directory path.
    """

    from api import main as _api_main

    return _api_main.SETTINGS_BACKUPS_DIR


def _resolve_settings_file_metadata(path: Path) -> dict[str, object]:
    """Build file metadata payload for one settings-managed YAML file.

    Purpose:
        Provide the settings panel with file existence and timestamp details
        without exposing arbitrary filesystem reads.
    Args:
        path: Absolute filesystem path for the managed settings file.
    Output:
        Returns file metadata dictionary with deterministic keys.
    """

    exists = path.exists()
    stat_result = path.stat() if exists else None
    modified_at = (
        datetime.fromtimestamp(stat_result.st_mtime, tz=UTC).isoformat()
        if stat_result is not None
        else None
    )
    size_bytes = stat_result.st_size if stat_result is not None else 0

    return {
        "filename": path.name,
        "path": str(path),
        "exists": exists,
        "size_bytes": size_bytes,
        "modified_at": modified_at,
    }


def _read_settings_text(path: Path, *, file_label: str) -> str:
    """Read one settings-managed text file from disk.

    Purpose:
        Centralize settings file reads so endpoints return consistent errors
        when the canonical file is missing or unreadable.
    Args:
        path: Absolute filesystem path to read.
        file_label: Human-readable file label for error messages.
    Output:
        Returns decoded UTF-8 file text.
    Raises:
        HTTPException: When file does not exist or cannot be read as UTF-8.
    """

    if not path.exists():
        _raise_api_error(
            status_code=404,
            code="FILE_NOT_FOUND",
            message=f"{file_label} file does not exist.",
            details={"path": str(path)},
        )
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        _raise_api_error(
            status_code=500,
            code="FILE_READ_ERROR",
            message=f"Failed to read {file_label} file.",
            details={"path": str(path), "error": str(exc)},
        )
    raise AssertionError("Unreachable: _raise_api_error always raises HTTPException.")


def _parse_yaml_mapping(*, yaml_text: str, context: str) -> dict[str, object]:
    """Parse YAML text and assert a mapping root value.

    Purpose:
        Keep YAML parsing behavior deterministic for all settings endpoints and
        surface field-level validation with stable API error payloads.
    Args:
        yaml_text: Raw YAML text submitted by request or loaded from disk.
        context: Context label used in error details.
    Output:
        Returns parsed root mapping payload.
    Raises:
        HTTPException: When YAML is invalid or the root is not a mapping.
    """

    parsed_payload: object
    try:
        parsed_payload = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        _raise_api_error(
            status_code=400,
            code="INVALID_YAML",
            message="YAML payload is invalid.",
            details={"context": context, "error": str(exc)},
        )

    if not isinstance(parsed_payload, dict):
        _raise_api_error(
            status_code=422,
            code="INVALID_SETTINGS_ROOT",
            message="YAML root must be a mapping.",
            details={"context": context},
        )
    return cast(dict[str, object], parsed_payload)


def _validate_candidate_profile_document(
    payload: Mapping[str, object],
) -> CandidateProfileDocumentPayload:
    """Validate candidate profile mapping payload.

    Purpose:
        Enforce one structured shape for profile fields so guided settings
        forms and prompt-context rendering always receive deterministic types.
    Args:
        payload: Parsed candidate-profile YAML mapping.
    Output:
        Returns validated `CandidateProfileDocumentPayload`.
    Raises:
        HTTPException: When payload shape or field types are invalid.
    """

    try:
        return CandidateProfileDocumentPayload.model_validate(payload)
    except ValidationError as exc:
        _raise_api_error(
            status_code=422,
            code="INVALID_PROFILE_SHAPE",
            message="Candidate profile settings payload is invalid.",
            details={"errors": exc.errors()},
        )
    raise AssertionError("Unreachable: _raise_api_error always raises HTTPException.")


def _normalize_candidate_profile_output(
    payload: CandidateProfileDocumentPayload,
) -> dict[str, object]:
    """Build API-friendly candidate-profile payload from validated document.

    Purpose:
        Return one stable response shape for candidate profile settings reads
        and writes, independent of how data was supplied.
    Args:
        payload: Validated candidate profile document model.
    Output:
        Returns JSON-serializable profile payload for API responses.
    """

    return {
        "profile": payload.profile.model_dump(mode="json"),
        "search_defaults": payload.search_defaults.model_dump(mode="json"),
        "prompt_context": payload.prompt_context,
    }


def _validate_resume_document(payload: Mapping[str, object]) -> ResumeContent:
    """Validate one resume mapping against canonical schema and lock rules.

    Purpose:
        Ensure every resume write path enforces the same Pydantic schema and
        immutable section lock constraints before persistence.
    Args:
        payload: Parsed resume mapping payload from YAML or structured request.
    Output:
        Returns validated `ResumeContent` model.
    Raises:
        HTTPException: When schema or lock validation fails.
    """

    try:
        resume_document = ResumeContent.model_validate(payload)
        validate_locked_structure(resume_document)
        return resume_document
    except (ValidationError, ValueError) as exc:
        details: dict[str, object]
        if isinstance(exc, ValidationError):
            details = {"errors": exc.errors()}
        else:
            details = {"error": str(exc)}
        _raise_api_error(
            status_code=422,
            code="INVALID_RESUME_SHAPE",
            message="Resume settings payload is invalid.",
            details=details,
        )
    raise AssertionError("Unreachable: _raise_api_error always raises HTTPException.")


def _persist_yaml_mapping(path: Path, *, payload: Mapping[str, object]) -> str:
    """Persist mapping payload to YAML with deterministic serialization.

    Purpose:
        Keep profile settings writes stable and diff-friendly while preserving
        unknown keys included in the top-level payload mapping.
    Args:
        path: Destination YAML file path.
        payload: Mapping to serialize and write.
    Output:
        Returns the serialized YAML text that was written to disk.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    yaml_text = yaml.safe_dump(
        dict(payload),
        sort_keys=False,
        allow_unicode=False,
        width=120,
    )
    path.write_text(yaml_text, encoding="utf-8")
    return yaml_text


def _prune_settings_backups(path: Path, *, file_label: str) -> None:
    """Prune old backup snapshots and keep only the newest files.

    Purpose:
        Bound disk usage for settings backups while preserving recent restore
        points for resume/profile rollback safety.
    Args:
        path: Source settings file path used to derive backup filename pattern.
        file_label: Human-readable label used in API error payloads.
    Output:
        Returns `None` after deleting stale backup files when needed.
    Raises:
        HTTPException: When backup pruning fails.
    """

    backups_dir = _resolve_backups_dir()
    backup_pattern = f"{path.stem}_*{path.suffix}"
    backup_paths = sorted(
        backups_dir.glob(backup_pattern),
        key=lambda candidate: candidate.stat().st_mtime,
        reverse=True,
    )
    stale_paths = backup_paths[SETTINGS_BACKUP_FILE_LIMIT:]
    for stale_path in stale_paths:
        try:
            stale_path.unlink(missing_ok=True)
        except OSError as exc:
            _raise_api_error(
                status_code=500,
                code="BACKUP_PRUNE_ERROR",
                message=f"Failed to prune {file_label} backup file.",
                details={
                    "source_path": str(path),
                    "backup_path": str(stale_path),
                    "error": str(exc),
                },
            )


def _backup_settings_file(path: Path, *, file_label: str) -> None:
    """Create a timestamped backup snapshot before overwriting settings files.

    Purpose:
        Protect against accidental data loss by snapshotting current settings
        files before API endpoints persist updated content.
    Args:
        path: Source settings file path to snapshot when it exists.
        file_label: Human-readable label used in API error payloads.
    Output:
        Returns `None` after writing one backup snapshot or when source is absent.
    Raises:
        HTTPException: When backup write or pruning fails.
    """

    if not path.exists():
        return

    backups_dir = _resolve_backups_dir()
    backups_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=UTC).strftime(SETTINGS_BACKUP_TIMESTAMP_FORMAT)
    backup_path = backups_dir / f"{path.stem}_{timestamp}{path.suffix}"

    # Add a numeric suffix when multiple writes land within one second.
    suffix_index = 1
    while backup_path.exists():
        backup_path = backups_dir / (
            f"{path.stem}_{timestamp}_{suffix_index:02d}{path.suffix}"
        )
        suffix_index += 1

    try:
        shutil.copy2(path, backup_path)
    except OSError as exc:
        _raise_api_error(
            status_code=500,
            code="BACKUP_WRITE_ERROR",
            message=f"Failed to write {file_label} backup file.",
            details={
                "source_path": str(path),
                "backup_path": str(backup_path),
                "error": str(exc),
            },
        )

    _prune_settings_backups(path, file_label=file_label)


def _resume_counts(resume_document: ResumeContent) -> dict[str, int]:
    """Compute lightweight resume section counts for API responses.

    Purpose:
        Return concise migration/save diagnostics that help settings UI confirm
        the persisted resume structure at a glance.
    Args:
        resume_document: Validated resume model.
    Output:
        Returns per-section listing count values.
    """

    return {
        "education_entries": len(resume_document.education.entries),
        "experience_listings": len(resume_document.experience.listings),
        "project_listings": len(resume_document.projects.listings),
        "skill_rows": len(resume_document.skills_achievements.listings),
    }


async def _read_uploaded_text(file: UploadFile) -> str:
    """Read uploaded file bytes and decode to UTF-8 text.

    Purpose:
        Enforce one upload-decoding path for settings file endpoints.
    Args:
        file: FastAPI upload file object.
    Output:
        Returns decoded file text.
    Raises:
        HTTPException: When payload cannot be decoded as UTF-8 text.
    """

    raw_bytes = await file.read()
    try:
        return raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        _raise_api_error(
            status_code=400,
            code="INVALID_FILE_ENCODING",
            message="Uploaded file must be UTF-8 text.",
        )
    raise AssertionError("Unreachable: _raise_api_error always raises HTTPException.")
