"""Jobs router (list, tailored-resume download, manual import)."""

from __future__ import annotations

import secrets
from datetime import UTC
from datetime import datetime

from fastapi import APIRouter
from fastapi import Query
from fastapi import Request
from fastapi.responses import FileResponse

from src.database.db_manager import DatabaseManager

from api.config import DEFAULT_PAGE_SIZE
from api.config import MAX_PAGE_SIZE
from api.config import TAILORED_RESUME_DIR
from api.config import TAILORED_RESUME_FILENAME
from api.errors import _raise_api_error
from api.schemas.common import JobImportRequest
from api.services.salary import _build_pipeline_steps
from api.services.salary import _parse_gate_result
from api.services.salary import _salary_display
from api.services.sources import _source_filter_sql
from api.services.sources import _source_label
from api.services.tailored_resume import _is_safe_tailored_resume_path
from api.services.tailored_resume import _require_tailored_resume_access
from api.services.tailored_resume import _resolve_latest_tailored_resume_pdf_path
from api.services.tailored_resume import _validate_job_hash

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
async def get_jobs(
    search: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    status: str | None = Query(default=None),
    source: str | None = Query(default=None),
) -> dict[str, object]:
    """Return paginated jobs table rows with expandable-detail metadata.

    Purpose:
        Replace mock jobs data with live SQL-backed rows supporting search,
        pagination, and basic status/source filtering.
    Args:
        search: Optional text filter for company/title matching.
        page: 1-based page number.
        page_size: Number of rows per page.
        status: Optional exact status filter.
        source: Optional exact source filter.
    Output:
        Returns paginated jobs envelope with normalized row payloads.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    offset = (page - 1) * page_size
    search_like = f"%{search.strip()}%"

    filters: list[str] = []
    params: list[object] = []

    if search.strip():
        filters.append("(jp.company LIKE ? OR jp.title LIKE ?)")
        params.extend([search_like, search_like])
    if status is not None and status.strip() != "":
        filters.append("jp.status = ?")
        params.append(status.strip().upper())
    if source is not None and source.strip() != "":
        source_clause, source_params = _source_filter_sql(source)
        filters.append(source_clause)
        params.extend(source_params)

    where_clause = ""
    if filters:
        where_clause = "WHERE " + " AND ".join(filters)

    db_path = str(_main.resolve_database_path())
    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        await db.migrate_apply_schema()

        assert db.conn is not None
        conn = db.conn

        count_cursor = await conn.execute(
            f"""
            SELECT COUNT(*) AS total_count
            FROM job_postings jp
            {where_clause}
            """,
            params,
        )
        count_row = await count_cursor.fetchone()
        assert count_row is not None  # SELECT COUNT(*) always returns a row
        total_items = int(count_row["total_count"] or 0)

        jobs_cursor = await conn.execute(
            f"""
            SELECT
                jp.id,
                jp.job_hash,
                jp.company,
                jp.title,
                jp.location,
                jp.is_remote,
                jp.job_type,
                jp.source,
                jp.status,
                jp.source_url,
                jp.fetched_at,
                jp.salary_min,
                jp.salary_max,
                jp.salary_currency,
                jp.agent_result,
                (
                    SELECT tr.artifact_pdf_path
                    FROM tailor_runs tr
                    WHERE tr.job_hash = jp.job_hash
                      AND tr.status = 'SUCCESS'
                    ORDER BY COALESCE(tr.completed_at, tr.started_at) DESC, tr.id DESC
                    LIMIT 1
                ) AS tailored_resume_path,
                EXISTS(
                    SELECT 1 FROM tailor_runs tr
                    WHERE tr.job_hash = jp.job_hash
                      AND tr.status = 'SUCCESS'
                ) AS has_tailor_success,
                EXISTS(
                    SELECT 1 FROM review_runs rr
                    WHERE rr.job_hash = jp.job_hash
                      AND rr.status = 'SUCCESS'
                ) AS has_review_success,
                EXISTS(
                    SELECT 1 FROM apply_runs ar
                    WHERE ar.job_hash = jp.job_hash
                      AND ar.status = 'SUCCESS'
                ) AS has_apply_success,
                EXISTS(
                    SELECT 1 FROM apply_handoffs ah
                    WHERE ah.job_hash = jp.job_hash
                      AND ah.handoff_status = 'PENDING_REVIEW'
                ) AS has_pending_handoff
            FROM job_postings jp
            {where_clause}
            ORDER BY jp.fetched_at DESC, jp.id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        )
        rows = await jobs_cursor.fetchall()

    job_items: list[dict[str, object]] = []
    for row in rows:
        gate_decision, gate_reasoning = _parse_gate_result(
            str(row["agent_result"] or "")
        )
        pipeline_steps = _build_pipeline_steps(
            job_status=str(row["status"]),
            has_tailor_success=bool(row["has_tailor_success"]),
            has_review_success=bool(row["has_review_success"]),
            has_apply_success=bool(row["has_apply_success"]),
            has_pending_handoff=bool(row["has_pending_handoff"]),
        )

        job_items.append(
            {
                "id": int(row["id"]),
                "job_hash": str(row["job_hash"]),
                "company": str(row["company"]),
                "position": str(row["title"]),
                "location": str(row["location"] or "—"),
                "pay": _salary_display(
                    salary_min=row["salary_min"],
                    salary_max=row["salary_max"],
                    salary_currency=row["salary_currency"],
                ),
                "work_type": "REMOTE"
                if bool(row["is_remote"])
                else "HYBRID"
                if str(row["job_type"] or "").lower().find("hybrid") >= 0
                else "IN_PERSON",
                "source": _source_label(str(row["source"])),
                "status": str(row["status"]),
                "discovered": str(row["fetched_at"]),
                "pipeline": pipeline_steps,
                "gate_verdict": gate_decision,
                "gate_reasoning": gate_reasoning,
                "tailored_resume": row["tailored_resume_path"],
                "job_posting_url": str(row["source_url"]),
            }
        )

    total_pages = max((total_items + page_size - 1) // page_size, 1)
    return {
        "ok": True,
        "page": page,
        "page_size": page_size,
        "total_items": total_items,
        "total_pages": total_pages,
        "items": job_items,
    }


@router.get("/{job_hash}/resume")
async def download_tailored_resume(job_hash: str, request: Request) -> FileResponse:
    """Download one tailored resume PDF by job hash.

    Purpose:
        Provide the jobs table with a safe file-download endpoint for tailored
        PDFs generated by the tailor worker.
    Args:
        job_hash: Job-hash path parameter for tailored artifact lookup.
        request: Request object used for access control enforcement.
    Output:
        Returns a PDF `FileResponse` when the artifact exists.
    Raises:
        HTTPException: When hash format is invalid or the PDF is missing.
    """

    validated_hash = _validate_job_hash(job_hash)
    _require_tailored_resume_access(request)

    resume_pdf_path = await _resolve_latest_tailored_resume_pdf_path(validated_hash)
    if resume_pdf_path is None:
        legacy_path = TAILORED_RESUME_DIR / validated_hash / TAILORED_RESUME_FILENAME
        if legacy_path.exists() and _is_safe_tailored_resume_path(
            job_hash=validated_hash,
            candidate_path=legacy_path,
        ):
            resume_pdf_path = legacy_path.resolve()

    if resume_pdf_path is None:
        _raise_api_error(
            status_code=404,
            code="FILE_NOT_FOUND",
            message="Tailored resume PDF does not exist for this job.",
            details={
                "job_hash": validated_hash,
                "path": str(
                    TAILORED_RESUME_DIR / validated_hash / TAILORED_RESUME_FILENAME
                ),
            },
        )
    assert resume_pdf_path is not None

    return FileResponse(
        resume_pdf_path,
        media_type="application/pdf",
        filename=f"resume_tailored_{validated_hash}.pdf",
    )


@router.post("/import")
async def import_job_manually(payload: JobImportRequest) -> dict[str, object]:
    """Import a job posting manually from URL or pasted text.

    Args:
        payload: Import request with mode and associated data.

    Returns:
        JSON with created job identifier.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    if payload.mode == "url" and not payload.url:
        _raise_api_error(
            status_code=422,
            code="MISSING_URL",
            message="URL is required when mode is 'url'.",
        )

    if payload.mode == "text" and not payload.title:
        _raise_api_error(
            status_code=422,
            code="MISSING_TITLE",
            message="Title is required when mode is 'text'.",
        )

    job_hash = secrets.token_hex(16)
    db_path = str(_main.resolve_database_path())

    async with DatabaseManager(db_path) as db:
        conn = db._require_conn()
        cursor = await conn.execute(
            """
            INSERT INTO job_postings (
                job_hash, company, position, location, pay,
                work_type, source, status, discovered, job_posting_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_hash,
                payload.company or "Unknown",
                payload.title or "Imported Job",
                payload.location or "",
                "",
                "",
                "manual_import",
                "new",
                datetime.now(tz=UTC).isoformat(),
                payload.url or "",
            ),
        )
        await conn.commit()
        job_id = cursor.lastrowid

    return {"ok": True, "job_id": job_id}
