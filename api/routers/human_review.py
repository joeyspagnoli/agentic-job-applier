"""Human-review router (queue list + per-handoff complete/dismiss actions)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi import Body
from fastapi import Query

from src.database.db_manager import DatabaseManager

from api.config import DEFAULT_PAGE_SIZE
from api.config import MAX_PAGE_SIZE
from api.errors import _raise_api_error
from api.schemas.common import ReviewerActionRequest
from api.services.salary import _parse_unresolved_fields

router = APIRouter(prefix="/api/human-review", tags=["human-review"])


@router.get("")
async def get_human_review_queue(
    search: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    status: str | None = Query(default=None),
) -> dict[str, object]:
    """Return paginated human-review queue entries from apply handoffs.

    Purpose:
        Feed the human-review table with persisted pending/resolved handoff
        records and expandable unresolved-field recommendations.
    Args:
        search: Optional text filter across company and position.
        page: 1-based page number.
        page_size: Number of rows per page.
        status: Optional handoff status filter.
    Output:
        Returns paginated queue envelope with normalized records.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    offset = (page - 1) * page_size
    filters: list[str] = []
    params: list[object] = []

    if search.strip():
        query_like = f"%{search.strip()}%"
        filters.append("(jp.company LIKE ? OR jp.title LIKE ?)")
        params.extend([query_like, query_like])

    if status is not None and status.strip() != "":
        filters.append("ah.handoff_status = ?")
        params.append(status.strip().upper())

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
            FROM apply_handoffs ah
            JOIN job_postings jp ON jp.job_hash = ah.job_hash
            {where_clause}
            """,
            params,
        )
        count_row = await count_cursor.fetchone()
        assert count_row is not None  # SELECT COUNT(*) always returns a row
        total_items = int(count_row["total_count"] or 0)

        rows_cursor = await conn.execute(
            f"""
            SELECT
                ah.id,
                ah.handoff_status,
                ah.confidence_score,
                ah.apply_outcome,
                ah.unresolved_fields_json,
                ah.reviewer_notes,
                ah.resume_pdf_path,
                ah.ats_platform,
                ah.created_at,
                ah.reviewed_at,
                jp.company,
                jp.title,
                jp.source_url
            FROM apply_handoffs ah
            JOIN job_postings jp ON jp.job_hash = ah.job_hash
            {where_clause}
            ORDER BY COALESCE(ah.updated_at, ah.created_at) DESC, ah.id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        )
        rows = await rows_cursor.fetchall()

    items: list[dict[str, object]] = []
    for row in rows:
        unresolved_fields = _parse_unresolved_fields(
            str(row["unresolved_fields_json"] or "")
        )
        confidence_score = float(row["confidence_score"] or 0.0)
        confidence_pct = int(round(confidence_score * 100.0))
        items.append(
            {
                "id": int(row["id"]),
                "company_name": str(row["company"]),
                "position": str(row["title"]),
                "status": str(row["handoff_status"]),
                "confidence_pct": max(0, min(100, confidence_pct)),
                "applied_date": str(row["created_at"]),
                "agent_diagnostic": (
                    f"Apply outcome: {row['apply_outcome']}"
                    + (f" on {row['ats_platform']}" if row["ats_platform"] else "")
                ),
                "job_posting_url": str(row["source_url"]),
                "resume_file_name": Path(
                    str(row["resume_pdf_path"] or "resume.pdf")
                ).name,
                "unresolved_fields": unresolved_fields,
            }
        )

    total_pages = max((total_items + page_size - 1) // page_size, 1)
    return {
        "ok": True,
        "page": page,
        "page_size": page_size,
        "total_items": total_items,
        "total_pages": total_pages,
        "items": items,
    }


@router.post("/{handoff_id}/complete")
async def complete_human_review(
    handoff_id: int,
    payload: ReviewerActionRequest = Body(default=ReviewerActionRequest()),
) -> dict[str, object]:
    """Mark one human-review handoff as approved and applied.

    Purpose:
        Resolve pending handoffs through explicit reviewer action and update the
        linked job status to `APPLIED`.
    Args:
        handoff_id: Primary key of the target `apply_handoffs` row.
        payload: Optional reviewer-notes payload.
    Output:
        Returns canonical mutation success payload with resolved handoff data.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    db_path = str(_main.resolve_database_path())
    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        await db.migrate_apply_schema()
        try:
            updated_row = await db.transition_handoff_status(
                handoff_id=handoff_id,
                target_status="APPROVED",
                reviewer_notes=payload.reviewer_notes,
            )
        except ValueError as exc:
            reason = str(exc)
            if reason == "handoff_not_found":
                _raise_api_error(
                    status_code=404,
                    code="HANDOFF_NOT_FOUND",
                    message=f"Handoff {handoff_id} does not exist.",
                )
            if reason == "handoff_already_resolved":
                _raise_api_error(
                    status_code=409,
                    code="HANDOFF_ALREADY_RESOLVED",
                    message="This handoff has already been resolved.",
                )
            _raise_api_error(
                status_code=400,
                code="INVALID_HANDOFF_TRANSITION",
                message=reason,
            )

    return {
        "ok": True,
        "handoff": updated_row,
    }


@router.post("/{handoff_id}/dismiss")
async def dismiss_human_review(
    handoff_id: int,
    payload: ReviewerActionRequest = Body(default=ReviewerActionRequest()),
) -> dict[str, object]:
    """Mark one human-review handoff as rejected.

    Purpose:
        Resolve pending handoffs through explicit reviewer dismissal and update
        the linked job status to `REJECTED`.
    Args:
        handoff_id: Primary key of the target `apply_handoffs` row.
        payload: Optional reviewer-notes payload.
    Output:
        Returns canonical mutation success payload with resolved handoff data.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    db_path = str(_main.resolve_database_path())
    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        await db.migrate_apply_schema()
        try:
            updated_row = await db.transition_handoff_status(
                handoff_id=handoff_id,
                target_status="REJECTED",
                reviewer_notes=payload.reviewer_notes,
            )
        except ValueError as exc:
            reason = str(exc)
            if reason == "handoff_not_found":
                _raise_api_error(
                    status_code=404,
                    code="HANDOFF_NOT_FOUND",
                    message=f"Handoff {handoff_id} does not exist.",
                )
            if reason == "handoff_already_resolved":
                _raise_api_error(
                    status_code=409,
                    code="HANDOFF_ALREADY_RESOLVED",
                    message="This handoff has already been resolved.",
                )
            _raise_api_error(
                status_code=400,
                code="INVALID_HANDOFF_TRANSITION",
                message=reason,
            )

    return {
        "ok": True,
        "handoff": updated_row,
    }
