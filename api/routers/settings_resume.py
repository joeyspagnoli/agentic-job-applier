"""Resume-related settings router (read/write/upload/PDF/TeX/download)."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi import File
from fastapi import UploadFile
from fastapi.responses import FileResponse

from src.agents.resume_tailor_adk.schemas import validate_locked_structure
from src.agents.resume_tailor_adk.yaml_io import save_resume_yaml

from scripts.migrate_resume_tex_to_yaml import ResumeMigrationError

from api.errors import _raise_api_error
from api.schemas.candidate import ResumeStructuredUpdateRequest
from api.schemas.common import YamlTextUpdateRequest
from api.services.resume_uploads import build_stub_resume_content
from api.services.resume_uploads import read_candidate_contact_from_profile_yaml
from api.services.resume_uploads import read_pdf_pages
from api.services.tex_migration import _normalize_tex_section_headings
from api.services.tex_migration import _prepare_resume_tex_for_migration
from api.services.yaml_files import _parse_yaml_mapping
from api.services.yaml_files import _read_settings_text
from api.services.yaml_files import _read_uploaded_text
from api.services.yaml_files import _resolve_settings_file_metadata
from api.services.yaml_files import _resume_counts
from api.services.yaml_files import _validate_resume_document

router = APIRouter(prefix="/api/settings", tags=["settings-resume"])


@router.post("/resume")
async def upload_resume_file(file: UploadFile = File(...)) -> dict[str, object]:
    """Replace the canonical base resume YAML from settings upload.

    Purpose:
        Persist resume YAML updates from the settings panel.
    Args:
        file: Uploaded resume YAML file.
    Output:
        Returns canonical mutation success payload with updated metadata.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    resume_path = _main.SETTINGS_RESUME_PATH
    text = await _read_uploaded_text(file)
    parsed_payload = _parse_yaml_mapping(yaml_text=text, context="resume")
    resume_document = _validate_resume_document(parsed_payload)
    _main._backup_settings_file(resume_path, file_label="Resume")
    save_resume_yaml(path=resume_path, resume_content=resume_document)

    return {
        "ok": True,
        "resume": _resolve_settings_file_metadata(resume_path),
    }


@router.post("/resume/pdf")
async def upload_resume_pdf(file: UploadFile = File(...)) -> dict[str, object]:
    """Upload a PDF resume and convert it to a minimal canonical YAML stub.

    Purpose:
        Allow users to upload a standard PDF resume during onboarding without
        being blocked by YAML authoring. Extracts text and saves a placeholder
        resume_content.yaml so onboarding can complete. The user refines the
        structured content in Settings afterward.
    Args:
        file: Uploaded PDF file (binary).
    Output:
        Returns canonical mutation success payload with updated metadata and
        extracted page count.
    Raises:
        HTTPException: When the file is not a valid PDF or text extraction fails.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    resume_path = _main.SETTINGS_RESUME_PATH
    profile_path = _main.SETTINGS_PROFILE_PATH
    raw_bytes = await file.read()
    try:
        reader, extracted_pages = read_pdf_pages(raw_bytes)
    except Exception as exc:
        _raise_api_error(
            status_code=400,
            code="INVALID_PDF",
            message=f"Could not read PDF file: {exc}",
        )
        raise AssertionError("Unreachable")

    extracted_text = "\n".join(extracted_pages).strip()

    raw_pdf_path = resume_path.parent / "resume_raw.pdf"
    raw_pdf_path.parent.mkdir(parents=True, exist_ok=True)
    raw_pdf_path.write_bytes(raw_bytes)

    candidate_name, candidate_phone, candidate_email = (
        read_candidate_contact_from_profile_yaml(profile_path)
    )
    stub_resume = build_stub_resume_content(
        candidate_name=candidate_name,
        candidate_phone=candidate_phone,
        candidate_email=candidate_email,
    )

    _main._backup_settings_file(resume_path, file_label="Resume")
    save_resume_yaml(path=resume_path, resume_content=stub_resume)

    return {
        "ok": True,
        "resume": _resolve_settings_file_metadata(resume_path),
        "pdf_pages": len(reader.pages),
        "extracted_chars": len(extracted_text),
    }


@router.get("/resume")
async def get_resume_settings() -> dict[str, object]:
    """Return resume settings with raw YAML text and parsed canonical payload.

    Purpose:
        Provide one read endpoint for guided resume editing, advanced YAML
        editing, and post-conversion refresh flows.
    Args:
        None.
    Output:
        Returns metadata, raw YAML text, and parsed resume payload.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    resume_path = _main.SETTINGS_RESUME_PATH
    yaml_text = _read_settings_text(resume_path, file_label="Resume")
    parsed_payload = _parse_yaml_mapping(yaml_text=yaml_text, context="resume")
    resume_document = _validate_resume_document(parsed_payload)

    return {
        "ok": True,
        "metadata": _resolve_settings_file_metadata(resume_path),
        "yaml_text": yaml_text,
        "resume": resume_document.model_dump(mode="json"),
        "counts": _resume_counts(resume_document),
    }


@router.put("/resume")
async def update_resume_yaml(payload: YamlTextUpdateRequest) -> dict[str, object]:
    """Persist resume settings from raw YAML text with full schema validation.

    Purpose:
        Support advanced YAML editing while enforcing canonical resume schema
        and lock constraints before writing persisted YAML.
    Args:
        payload: Raw YAML payload wrapper.
    Output:
        Returns metadata, canonical YAML text, and parsed resume payload.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    resume_path = _main.SETTINGS_RESUME_PATH
    parsed_payload = _parse_yaml_mapping(yaml_text=payload.yaml_text, context="resume")
    resume_document = _validate_resume_document(parsed_payload)
    _main._backup_settings_file(resume_path, file_label="Resume")
    save_resume_yaml(path=resume_path, resume_content=resume_document)
    persisted_yaml = _read_settings_text(resume_path, file_label="Resume")

    return {
        "ok": True,
        "metadata": _resolve_settings_file_metadata(resume_path),
        "yaml_text": persisted_yaml,
        "resume": resume_document.model_dump(mode="json"),
        "counts": _resume_counts(resume_document),
    }


@router.put("/resume/structured")
async def update_resume_structured(
    payload: ResumeStructuredUpdateRequest,
) -> dict[str, object]:
    """Persist resume settings from guided structured payload.

    Purpose:
        Support form-first resume editing while preserving strict resume schema
        and lock validations on every save.
    Args:
        payload: Structured resume payload wrapper.
    Output:
        Returns metadata, canonical YAML text, and parsed resume payload.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    resume_path = _main.SETTINGS_RESUME_PATH
    resume_document = _validate_resume_document(payload.resume)
    _main._backup_settings_file(resume_path, file_label="Resume")
    save_resume_yaml(path=resume_path, resume_content=resume_document)
    persisted_yaml = _read_settings_text(resume_path, file_label="Resume")

    return {
        "ok": True,
        "metadata": _resolve_settings_file_metadata(resume_path),
        "yaml_text": persisted_yaml,
        "resume": resume_document.model_dump(mode="json"),
        "counts": _resume_counts(resume_document),
    }


@router.post("/resume/tex")
async def upload_resume_tex(file: UploadFile = File(...)) -> dict[str, object]:
    """Upload a LaTeX resume source and migrate it into canonical YAML.

    Purpose:
        Provide a settings-native conversion flow so users can update resume
        content from `.tex` without manual YAML authoring.
    Args:
        file: Uploaded LaTeX `.tex` file.
    Output:
        Returns canonical resume payload, metadata, and migration counts.
    Raises:
        HTTPException: When conversion fails or produced invalid resume YAML.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    resume_path = _main.SETTINGS_RESUME_PATH
    resume_tex_path = _main.SETTINGS_RESUME_TEX_PATH
    tex_text = await _read_uploaded_text(file)
    prepared_tex_text = tex_text
    if resume_path.exists():
        fallback_yaml_text = _read_settings_text(resume_path, file_label="Resume")
        fallback_payload = _parse_yaml_mapping(
            yaml_text=fallback_yaml_text,
            context="resume",
        )
        fallback_resume = _validate_resume_document(fallback_payload)
        prepared_tex_text = _prepare_resume_tex_for_migration(
            uploaded_tex_text=tex_text,
            fallback_resume=fallback_resume,
        )
    else:
        prepared_tex_text = _normalize_tex_section_headings(tex_text)

    resume_tex_path.parent.mkdir(parents=True, exist_ok=True)
    resume_tex_path.write_text(prepared_tex_text, encoding="utf-8")
    migrated_output_path = resume_path.with_name(
        f"{resume_path.stem}.migrated.tmp{resume_path.suffix}"
    )

    try:
        migrated_resume = _main.migrate_resume_tex_to_yaml(
            resume_tex_path=resume_tex_path,
            output_yaml_path=migrated_output_path,
        )
        validate_locked_structure(migrated_resume)
    except ResumeMigrationError as exc:
        migrated_output_path.unlink(missing_ok=True)
        _raise_api_error(
            status_code=422,
            code="RESUME_TEX_MIGRATION_FAILED",
            message="LaTeX resume conversion failed.",
            details={"error": str(exc)},
        )
    except ValueError as exc:
        migrated_output_path.unlink(missing_ok=True)
        _raise_api_error(
            status_code=422,
            code="INVALID_RESUME_SHAPE",
            message="Converted resume YAML did not satisfy lock constraints.",
            details={"error": str(exc)},
        )
    _main._backup_settings_file(resume_path, file_label="Resume")
    try:
        migrated_output_path.replace(resume_path)
    except OSError as exc:
        _raise_api_error(
            status_code=500,
            code="RESUME_REPLACE_FAILED",
            message="Failed to persist converted resume YAML file.",
            details={
                "output_yaml_path": str(resume_path),
                "temporary_yaml_path": str(migrated_output_path),
                "error": str(exc),
            },
        )

    persisted_yaml = _read_settings_text(resume_path, file_label="Resume")
    return {
        "ok": True,
        "metadata": _resolve_settings_file_metadata(resume_path),
        "yaml_text": persisted_yaml,
        "resume": migrated_resume.model_dump(mode="json"),
        "counts": _resume_counts(migrated_resume),
        "migration": {
            "source_tex_path": str(resume_tex_path),
            "output_yaml_path": str(resume_path),
            "normalized_input": prepared_tex_text != tex_text,
            **_resume_counts(migrated_resume),
        },
    }


@router.get("/resume/download")
async def download_resume_file() -> FileResponse:
    """Download the canonical base resume YAML file.

    Purpose:
        Provide settings-panel download action for current resume YAML.
    Args:
        None.
    Output:
        Returns FileResponse for `config/resume_content.yaml`.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    resume_path = _main.SETTINGS_RESUME_PATH
    if not resume_path.exists():
        _raise_api_error(
            status_code=404,
            code="FILE_NOT_FOUND",
            message="Resume file does not exist.",
        )
    return FileResponse(
        resume_path,
        media_type="application/x-yaml",
        filename=resume_path.name,
    )
