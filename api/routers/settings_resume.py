"""Resume-related settings router — `.tex`-only upload + download (Phase 3).

Phase 3 (#60) replaced the YAML / structured / PDF upload endpoints
with a single `POST /api/settings/resume` that accepts a `.tex` file
and validates it against `docs/resume-tex-contract.md`. The old
endpoints respond 410 GONE with a structured error envelope pointing
at the new endpoint and the contract doc.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi import File
from fastapi import UploadFile
from fastapi.responses import FileResponse, JSONResponse

from src.agents.resume_tailor.validator import validate_resume_tex

from api.errors import _raise_api_error
from api.services.yaml_files import (
    _read_settings_text,
    _read_uploaded_text,
    _resolve_settings_file_metadata,
)

router = APIRouter(prefix="/api/settings", tags=["settings-resume"])

# Stable error code emitted when a removed endpoint is hit. The
# frontend renders the included `new_endpoint` field as a link.
_ENDPOINT_REMOVED_CODE = "ENDPOINT_REMOVED"
_INVALID_RESUME_TEX_CODE = "INVALID_RESUME_TEX"
_NEW_RESUME_ENDPOINT = "POST /api/settings/resume"
_CONTRACT_DOCS_URL = "/docs/resume-tex-contract.md"


def _gone_response(detail: str) -> JSONResponse:
    """Render the 410 GONE envelope used by every retired endpoint.

    Purpose:
        Plan §5.1 specifies a uniform error shape so the frontend can
        rerender retired-endpoint hits as "this moved" notices without
        per-endpoint branching.
    Args:
        detail: Short description of which endpoint was retired.
    Output:
        JSONResponse with status 410 and the structured payload.
    """

    return JSONResponse(
        status_code=410,
        content={
            "ok": False,
            "code": _ENDPOINT_REMOVED_CODE,
            "message": (
                f"This endpoint was retired in the .tex-only upload "
                f"redesign (#60). Use {_NEW_RESUME_ENDPOINT}. ({detail})"
            ),
            "new_endpoint": _NEW_RESUME_ENDPOINT,
            "docs_url": _CONTRACT_DOCS_URL,
        },
    )


@router.post("/resume")
async def upload_resume_tex(file: UploadFile = File(...)) -> JSONResponse:
    """Validate + persist a user-supplied `.tex` resume.

    Purpose:
        Single entry point for resume uploads in the `.tex`-only world.
        Runs `validate_resume_tex` before committing the file so
        non-conforming uploads are rejected with line-numbered errors
        the frontend can render inline.
    Args:
        file: Multipart `.tex` upload.
    Output:
        200 + manifest preview on success; 422 with `ValidatorError`
        list on contract violations.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    resume_path = _main.SETTINGS_RESUME_PATH
    tex_text = await _read_uploaded_text(file)
    report = validate_resume_tex(tex_text, run_compile_check=False)
    if not report.ok:
        return JSONResponse(
            status_code=422,
            content={
                "ok": False,
                "code": _INVALID_RESUME_TEX_CODE,
                "message": "Resume does not conform to the .tex contract.",
                "errors": [error.model_dump() for error in report.errors],
                "docs_url": _CONTRACT_DOCS_URL,
            },
        )

    _main._backup_settings_file(resume_path, file_label="Resume")
    resume_path.parent.mkdir(parents=True, exist_ok=True)
    resume_path.write_text(tex_text, encoding="utf-8")

    manifest_preview = (
        report.manifest_preview.model_dump(mode="json")
        if report.manifest_preview is not None
        else None
    )
    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "resume": _resolve_settings_file_metadata(resume_path),
            "manifest_preview": manifest_preview,
        },
    )


@router.get("/resume")
async def get_resume_settings() -> JSONResponse:
    """Return resume settings — raw `.tex` text + manifest preview.

    Purpose:
        Power the single resume view on the Settings page now that
        the guided / YAML / structured tabs are gone (plan §5.2).
    Output:
        200 with `tex_text`, `metadata`, and `manifest_preview` when
        the file exists; 404 when no resume is on disk.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    resume_path = _main.SETTINGS_RESUME_PATH
    if not resume_path.exists():
        _raise_api_error(
            status_code=404,
            code="FILE_NOT_FOUND",
            message="Resume file does not exist.",
        )

    tex_text = _read_settings_text(resume_path, file_label="Resume")
    report = validate_resume_tex(tex_text, run_compile_check=False)
    manifest_preview = (
        report.manifest_preview.model_dump(mode="json")
        if report.manifest_preview is not None
        else None
    )
    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "metadata": _resolve_settings_file_metadata(resume_path),
            "tex_text": tex_text,
            "contract_pass": report.ok,
            "manifest_preview": manifest_preview,
        },
    )


@router.put("/resume")
async def update_resume_yaml() -> JSONResponse:
    """410 GONE — YAML text update was retired in the .tex redesign.

    Purpose:
        Surface a structured "endpoint moved" envelope so older
        dashboard builds don't silently break.
    """

    return _gone_response("PUT /api/settings/resume (YAML text update) was retired.")


@router.put("/resume/structured")
async def update_resume_structured() -> JSONResponse:
    """410 GONE — structured-form update was retired in the .tex redesign.

    Purpose:
        Surface a structured "endpoint moved" envelope so older
        dashboard builds don't silently break.
    """

    return _gone_response("PUT /api/settings/resume/structured was retired.")


@router.post("/resume/pdf")
async def upload_resume_pdf() -> JSONResponse:
    """410 GONE — PDF upload was retired (see onboarding migration skill).

    Purpose:
        Surface a structured "endpoint moved" envelope and direct
        PDF users at the (separate-issue) onboarding skill.
    """

    return _gone_response(
        "POST /api/settings/resume/pdf was retired. PDF/DOCX users use "
        "the onboarding migration skill to produce a .tex resume."
    )


@router.post("/resume/tex")
async def upload_resume_tex_migration_alias() -> JSONResponse:
    """410 GONE — TeX→YAML migration endpoint collapsed into POST /resume.

    Purpose:
        The split tex-vs-yaml endpoint is gone; one upload path now.
    """

    return _gone_response(
        "POST /api/settings/resume/tex was collapsed into POST /api/settings/resume."
    )


@router.get("/resume/download")
async def download_resume_file() -> FileResponse:
    """Download the canonical resume `.tex` file.

    Purpose:
        Provide settings-panel download action for the current
        `.tex` source (Phase 3 — no longer YAML).
    Output:
        FileResponse for `config/resume.tex` with `application/x-tex`.
    Raises:
        HTTPException: 404 when the resume file does not exist.
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
        media_type="application/x-tex",
        filename=resume_path.name,
    )
