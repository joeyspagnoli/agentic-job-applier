"""Human-review router (queue list + per-handoff complete/dismiss actions)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import cast

from fastapi import APIRouter
from fastapi import Body
from fastapi import Query
from pydantic import BaseModel, Field

from src.database._mixins.apply import (
    ApplyRunInFlightError,
    NoReviewRunError,
)
from src.database.db_manager import DatabaseManager
from src.utils.paths import resolve_repo_root

from api.config import DEFAULT_PAGE_SIZE
from api.config import MAX_PAGE_SIZE
from api.errors import _raise_api_error
from api.schemas.common import ReviewerActionRequest
from api.services.answer_cache_seeding import (
    AnswerCacheSeedingError,
    seed_answer_cache_from_handoff,
)
from api.services.salary import _parse_unresolved_fields, _parse_user_answers


# Repo-relative location the apply worker reads from; mirrored from
# ``scripts/process_apply_jobs.ANSWER_CACHE_REL_PATH`` so we keep the
# router decoupled from that worker script.
_ANSWER_CACHE_REL_PATH = "data/answer_cache.yaml"


def _resolve_answer_cache_path() -> Path:
    """Return the absolute path to the finisher's persistent answer cache.

    Purpose:
        Pulled into its own function so tests can monkeypatch the
        module-level symbol and redirect cache writes onto a temp file
        instead of mutating ``data/answer_cache.yaml`` in the working
        tree.
    Returns:
        Absolute path to ``data/answer_cache.yaml`` under the repo root.
    """

    return resolve_repo_root() / _ANSWER_CACHE_REL_PATH

router = APIRouter(prefix="/api/human-review", tags=["human-review"])


class _UserAnswer(BaseModel):
    """One reviewer-supplied answer for a deferred Tier-3 question.

    Attributes:
        field_id: Identifier of the deferred field (e.g. ``"e368"``).
        answer: Reviewer-typed value to persist.
    """

    field_id: str = Field(min_length=1, max_length=128)
    answer: str = Field(max_length=4096)


class _SaveAnswersRequest(BaseModel):
    """Payload for ``POST /api/human-review/{id}/answers``.

    Attributes:
        answers: One entry per question the reviewer answered. The
            list replaces any previously-stored answers wholesale so
            the dashboard can save a partial draft and overwrite it
            cleanly on the next save.
    """

    answers: list[_UserAnswer] = Field(default_factory=list)


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
                ah.deferred_questions_json,
                ah.user_answers_json,
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
        # Prefer the finisher's deferred_questions_json — it carries
        # human-readable labels and reason text. Fall back to the older
        # unresolved_fields_json shape only when the finisher did not run
        # (Lever and older Greenhouse handoffs).
        deferred_raw = str(row["deferred_questions_json"] or "")
        deferred_fields = _parse_unresolved_fields(deferred_raw)
        if deferred_fields:
            unresolved_fields = deferred_fields
        else:
            unresolved_fields = _parse_unresolved_fields(
                str(row["unresolved_fields_json"] or "")
            )

        user_answers = _parse_user_answers(str(row["user_answers_json"] or ""))

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
                "user_answers": user_answers,
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


@router.post("/{handoff_id}/answers")
async def save_human_review_answers(
    handoff_id: int,
    payload: _SaveAnswersRequest = Body(...),
) -> dict[str, object]:
    """Persist reviewer-typed answers for one handoff's deferred questions.

    Purpose:
        Back the per-question textareas the Human Review page renders for
        each finisher-deferred Tier-3 question. The list replaces any
        previously-stored answers wholesale, so the dashboard can save a
        partial draft and overwrite it on the next save. After persisting
        the per-handoff record, every (label, answer) pair is appended to
        the durable answer cache the finisher reads on subsequent runs —
        Bug F (2026-05-25). Without that, every Human Review session was
        throwaway.
    Args:
        handoff_id: Primary key of the target ``apply_handoffs`` row.
        payload: ``{"answers": [{"field_id", "answer"}, ...]}``.
    Output:
        Returns ``{"ok": True, "user_answers": [...], "cache_seeded":
        [...]}``. ``cache_seeded`` summarizes which entries landed in the
        cache vs. which were skipped (with a short reason).
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    answers_payload = [
        {"field_id": entry.field_id, "answer": entry.answer}
        for entry in payload.answers
    ]
    serialized = json.dumps(answers_payload, ensure_ascii=False)

    db_path = str(_main.resolve_database_path())
    deferred_questions_json: str | None = None
    company: str = ""
    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        await db.migrate_apply_schema()
        try:
            await db.save_handoff_user_answers(
                handoff_id=handoff_id,
                user_answers_json=serialized,
            )
        except ValueError as exc:
            if str(exc) == "handoff_not_found":
                _raise_api_error(
                    status_code=404,
                    code="HANDOFF_NOT_FOUND",
                    message=f"Handoff {handoff_id} does not exist.",
                )
            _raise_api_error(
                status_code=400,
                code="HANDOFF_ANSWERS_WRITE_FAILED",
                message=str(exc),
            )

        # Pull the deferred-questions metadata + company in a single
        # round-trip so the cache-seeding step has labels and the
        # company name without touching the worker layer.
        assert db.conn is not None
        cursor = await db.conn.execute(
            """
            SELECT ah.deferred_questions_json, jp.company
            FROM apply_handoffs ah
            JOIN job_postings jp ON jp.job_hash = ah.job_hash
            WHERE ah.id = ?
            """,
            (handoff_id,),
        )
        row = await cursor.fetchone()
        if row is not None:
            deferred_questions_json = (
                str(row["deferred_questions_json"])
                if row["deferred_questions_json"]
                else None
            )
            company = str(row["company"] or "")

    cache_path = _resolve_answer_cache_path()
    try:
        seed_summary = await seed_answer_cache_from_handoff(
            cache_path=cache_path,
            company=company,
            deferred_questions_json=deferred_questions_json,
            answers=answers_payload,
        )
    except AnswerCacheSeedingError as exc:
        # User-typed data is already persisted on the handoff row; the
        # cache append is a downstream optimization, not a write
        # confirmation. Surface a distinct 500-class code so the
        # dashboard can show the cache-seeding warning without losing
        # the user's draft.
        _raise_api_error(
            status_code=500,
            code="ANSWER_CACHE_SEED_FAILED",
            message=str(exc),
            details={"handoff_id": handoff_id},
        )

    return {
        "ok": True,
        "user_answers": answers_payload,
        "cache_seeded": seed_summary,
    }


async def _relaunch_apply_for_handoff_id(
    *, db: DatabaseManager, handoff_id: int
) -> dict[str, object]:
    """Resolve, transition, and re-enqueue the apply for one handoff.

    Purpose:
        Shared body for both the handoff-keyed Human Review endpoint and
        the job-hash-keyed JobsPage variant. Inserts a fresh PENDING
        ``apply_runs`` row, flips the old handoff to APPROVED with a
        "Relaunched via Human Review" note, and returns the merged row
        that ``_spawn_user_apply_task`` consumes.
    Args:
        db: Open database manager.
        handoff_id: Primary key of the target handoff.
    Returns:
        The merged row from ``enqueue_apply_run_for_job`` so the caller
        can spawn the background task with it.
    Raises:
        HTTPException: 404/409/422 mirroring the public endpoint
            contract.
    """

    assert db.conn is not None
    cursor = await db.conn.execute(
        """
        SELECT id, apply_run_id, job_hash, handoff_status
        FROM apply_handoffs
        WHERE id = ?
        """,
        (handoff_id,),
    )
    handoff_row = await cursor.fetchone()
    if handoff_row is None:
        _raise_api_error(
            status_code=404,
            code="HANDOFF_NOT_FOUND",
            message=f"Handoff {handoff_id} does not exist.",
        )

    if str(handoff_row["handoff_status"]) != "PENDING_REVIEW":
        _raise_api_error(
            status_code=409,
            code="HANDOFF_ALREADY_RESOLVED",
            message="This handoff has already been resolved.",
        )

    prior_apply_run = await db.get_apply_run(int(handoff_row["apply_run_id"]))
    if prior_apply_run is None:
        _raise_api_error(
            status_code=404,
            code="APPLY_RUN_DELETED",
            message=(
                "The apply run linked to this handoff was deleted; "
                "cannot relaunch."
            ),
            details={"handoff_id": handoff_id},
        )

    job_hash = str(handoff_row["job_hash"])

    try:
        merged_row = await db.enqueue_apply_run_for_job(job_hash=job_hash)
    except ApplyRunInFlightError as exc:
        _raise_api_error(
            status_code=409,
            code="APPLY_RUN_IN_FLIGHT",
            message="An apply run is already in flight for this job.",
            details={"run_id": exc.run_id, "status": exc.status},
        )
    except NoReviewRunError:
        _raise_api_error(
            status_code=422,
            code="NO_REVIEW_RUN",
            message="Job has no completed review yet.",
            details={"job_hash": job_hash},
        )

    await db.transition_handoff_status(
        handoff_id=handoff_id,
        target_status="APPROVED",
        reviewer_notes="Relaunched via Human Review",
    )

    return merged_row


async def _find_pending_handoff_id_for_job(
    *, db: DatabaseManager, job_hash: str
) -> int | None:
    """Look up the most-recent PENDING_REVIEW handoff for ``job_hash``.

    Args:
        db: Open database manager.
        job_hash: Stable job identifier from the JobsPage row.
    Returns:
        Handoff primary key when one exists, ``None`` otherwise.
    """

    assert db.conn is not None
    cursor = await db.conn.execute(
        """
        SELECT id FROM apply_handoffs
        WHERE job_hash = ? AND handoff_status = 'PENDING_REVIEW'
        ORDER BY COALESCE(updated_at, created_at) DESC, id DESC
        LIMIT 1
        """,
        (job_hash,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return int(row["id"])


@router.post("/{handoff_id}/relaunch-apply", status_code=200)
async def relaunch_apply_from_handoff(handoff_id: int) -> dict[str, object]:
    """Re-enqueue the apply for a PENDING_REVIEW handoff and resolve the old row.

    Purpose:
        After saving answers in Human Review the reviewer needs an
        affordance to actually re-run the apply with those answers
        feeding the finisher's cache (which Bug F already populates).
        Mirrors the tailor-side "Delete & retry" pattern: inserts a new
        PENDING apply_runs row, flips the existing handoff to APPROVED
        with a "Relaunched" reviewer note so it disappears from the
        queue, and kicks off ``_spawn_user_apply_task`` so the browser
        flow starts immediately instead of waiting for the autonomous
        poll loop.
    Args:
        handoff_id: Primary key of the target ``apply_handoffs`` row.
    Returns:
        ``{"ok": True, "apply_run_id", "status", "job_hash"}`` so the
        dashboard can show "Apply queued (run #N)".
    Raises:
        HTTPException: 404 when the handoff is missing or its linked
            apply_run was soft-deleted; 409 when the handoff is already
            resolved or another apply is in flight; 422 when no review
            run exists for the job (should never happen for a handoff,
            but the underlying ``enqueue_apply_run_for_job`` raises it).
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook
    from api.routers.apply_runs import _spawn_user_apply_task  # noqa: PLC0415

    db_path = str(_main.resolve_database_path())
    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        await db.migrate_apply_schema()
        merged_row = await _relaunch_apply_for_handoff_id(
            db=db, handoff_id=handoff_id
        )

    asyncio.create_task(
        _spawn_user_apply_task(db_path=db_path, merged_row=merged_row),
    )

    return {
        "ok": True,
        "apply_run_id": int(cast(int, merged_row["_apply_run_id"])),
        "status": str(merged_row["status"]),
        "job_hash": str(merged_row["job_hash"]),
    }


@router.post("/by-job/{job_hash}/relaunch-apply", status_code=200)
async def relaunch_apply_for_job(job_hash: str) -> dict[str, object]:
    """JobsPage-friendly wrapper that resolves the handoff by job hash.

    Purpose:
        The Jobs page shows the same "Relaunch apply" affordance next
        to the NEEDS_REVIEW badge but does not carry the handoff id in
        local state. This endpoint looks up the most-recent
        PENDING_REVIEW handoff for ``job_hash`` and delegates to the
        same internal logic the handoff-keyed endpoint runs.
    Args:
        job_hash: Stable job identifier from the JobsPage row.
    Returns:
        Same payload shape as the handoff-keyed endpoint.
    Raises:
        HTTPException: 404 when no PENDING_REVIEW handoff exists for
            this job. Other 4xx codes match the handoff-keyed endpoint.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook
    from api.routers.apply_runs import _spawn_user_apply_task  # noqa: PLC0415
    from api.services.tailored_resume import _validate_job_hash  # noqa: PLC0415

    validated_hash = _validate_job_hash(job_hash)
    db_path = str(_main.resolve_database_path())
    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        await db.migrate_apply_schema()

        handoff_id = await _find_pending_handoff_id_for_job(
            db=db, job_hash=validated_hash
        )
        if handoff_id is None:
            _raise_api_error(
                status_code=404,
                code="NO_PENDING_HANDOFF",
                message=(
                    "No PENDING_REVIEW handoff exists for this job. The "
                    "apply run may already be resolved."
                ),
                details={"job_hash": validated_hash},
            )

        merged_row = await _relaunch_apply_for_handoff_id(
            db=db, handoff_id=handoff_id
        )

    asyncio.create_task(
        _spawn_user_apply_task(db_path=db_path, merged_row=merged_row),
    )

    return {
        "ok": True,
        "apply_run_id": int(cast(int, merged_row["_apply_run_id"])),
        "status": str(merged_row["status"]),
        "job_hash": str(merged_row["job_hash"]),
        "handoff_id": handoff_id,
    }
