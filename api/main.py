"""Expose FastAPI endpoints and static dashboard serving for the project.

This module provides the unified runtime boundary for the dashboard product:
- `/api/*` JSON endpoints backed by SQLite
- Static serving for built React assets in `dashboard/dist`
- SPA fallback for client-side routing
"""

from __future__ import annotations

import json
import logging
import os
import secrets
from collections.abc import Mapping
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from typing import Literal
from typing import cast

from fastapi import Body
from fastapi import FastAPI
from fastapi import File
from fastapi import HTTPException
from fastapi import Query
from fastapi import Request
from fastapi import UploadFile
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
import yaml

from scripts.migrate_resume_tex_to_yaml import ResumeMigrationError
from scripts.migrate_resume_tex_to_yaml import migrate_resume_tex_to_yaml
from src.agents.resume_tailor_pi.schemas import ResumeContent
from src.agents.resume_tailor_pi.yaml_io import save_resume_yaml
from src.agents.root_apply_decider.prompts import load_candidate_context
from src.database.db_manager import DatabaseManager
from src.utils.paths import resolve_database_path
from src.utils.paths import resolve_repo_root

from api.config import ALLOWED_API_KEY_NAMES
from api.config import ALLOWED_SERVICE_TIERS
from api.config import DASHBOARD_ASSETS_DIR
from api.config import DASHBOARD_DIST_DIR
from api.config import DASHBOARD_INDEX_FILE
from api.config import DEFAULT_PAGE_SIZE
from api.config import DEFAULT_POLLING_SECONDS
from api.config import MAX_PAGE_SIZE
from api.config import SETTINGS_BACKUPS_DIR
from api.config import SETTINGS_COMPANIES_PATH
from api.config import SETTINGS_FILTERS_PATH
from api.config import SETTINGS_PROFILE_PATH
from api.config import SETTINGS_RESUME_PATH
from api.config import SETTINGS_RESUME_TEX_PATH
from api.config import SYSTEM_ACTION_FETCH_JOBS
from api.config import SYSTEM_ACTION_RESTART
from api.config import SYSTEM_ACTION_STATUS_ACCEPTED
from api.config import SYSTEM_ACTION_STOP
from api.config import TAILORED_RESUME_DIR
from api.config import TAILORED_RESUME_FILENAME
from api.config import TAILORED_RESUME_TOKEN_ENV_KEY
from api.config import TAILORED_RESUME_TOKEN_HEADER
from api.config import WORK_AUTH_STATUS_NO
from api.config import WORK_AUTH_STATUS_UNKNOWN
from api.config import WORK_AUTH_STATUS_YES
from api.errors import _error_response
from api.errors import _raise_api_error
from api.schemas.candidate import CandidateContactSectionPayload
from api.schemas.candidate import CandidateEducationEntryPayload
from api.schemas.candidate import CandidateProfileDocumentPayload
from api.schemas.candidate import CandidateProfileSectionPayload
from api.schemas.candidate import CandidateSearchDefaultsPayload
from api.schemas.candidate import CandidateWorkAuthorizationSectionPayload
from api.schemas.candidate import ProfileStructuredUpdateRequest
from api.schemas.candidate import ResumeStructuredUpdateRequest
from api.schemas.candidate import _normalize_optional_country_code
from api.schemas.common import ApiKeyUpsertRequest
from api.schemas.common import BudgetUpdateRequest
from api.schemas.common import JobImportRequest
from api.schemas.common import ProviderConfigRequest
from api.schemas.common import ReviewerActionRequest
from api.schemas.common import ServiceTierUpdateRequest
from api.schemas.common import YamlPayload
from api.schemas.common import YamlTextUpdateRequest
from api.services.env_keys import _build_api_keys_response
from api.services.env_keys import _delete_env_key
from api.services.env_keys import _read_env_key_statuses
from api.services.env_keys import _read_env_pairs
from api.services.env_keys import _write_env_key
from api.services.migrations import _lifespan
from api.services.migrations import _run_startup_migrations
from api.services.salary import _build_pipeline_steps
from api.services.salary import _parse_gate_result
from api.services.salary import _parse_unresolved_fields
from api.services.salary import _salary_display
from api.services.sources import _source_filter_sql
from api.services.sources import _source_label
from api.services.system_scripts import _dispatch_system_lifecycle_action
from api.services.system_scripts import _load_positive_int_env
from api.services.system_scripts import _resolve_system_script_path
from api.services.system_scripts import _run_system_script
from api.services.tailored_resume import _is_safe_tailored_resume_path
from api.services.tailored_resume import _require_tailored_resume_access
from api.services.tailored_resume import _resolve_artifact_path
from api.services.tailored_resume import _resolve_latest_tailored_resume_pdf_path
from api.services.tailored_resume import _validate_job_hash
from api.services.tex_migration import _build_fallback_education_section
from api.services.tex_migration import _build_fallback_personal_header
from api.services.tex_migration import _ensure_tex_required_sections
from api.services.tex_migration import _normalize_tex_section_headings
from api.services.tex_migration import _prepare_resume_tex_for_migration
from api.services.yaml_files import _backup_settings_file
from api.services.yaml_files import _normalize_candidate_profile_output
from api.services.yaml_files import _parse_yaml_mapping
from api.services.yaml_files import _persist_yaml_mapping
from api.services.yaml_files import _prune_settings_backups
from api.services.yaml_files import _read_settings_text
from api.services.yaml_files import _read_uploaded_text
from api.services.yaml_files import _resolve_settings_file_metadata
from api.services.yaml_files import _resume_counts
from api.services.yaml_files import _validate_candidate_profile_document
from api.services.yaml_files import _validate_resume_document

logger = logging.getLogger(__name__)


app = FastAPI(lifespan=_lifespan)

if DASHBOARD_ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=DASHBOARD_ASSETS_DIR), name="assets")


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


@app.get("/api/health")
async def health_check() -> dict[str, object]:
    """Return a lightweight health payload for runtime checks.

    Purpose:
        Provide a stable API liveness endpoint for local validation.
    Args:
        None.
    Output:
        Returns health status and dashboard polling interval defaults.
    """

    return {
        "ok": True,
        "status": "healthy",
        "polling_seconds": DEFAULT_POLLING_SECONDS,
    }


@app.post("/api/system/stop")
async def stop_system_stack() -> dict[str, object]:
    """Dispatch a non-destructive full stack stop operation.

    Purpose:
        Allow dashboard users to stop the running compose stack through one API
        action instead of manual shell commands.
    Args:
        None.
    Output:
        Returns accepted payload with request identifier.
    """

    try:
        request_id = _dispatch_system_lifecycle_action(SYSTEM_ACTION_STOP)
    except OSError as exc:
        _raise_api_error(
            status_code=500,
            code="SYSTEM_ACTION_DISPATCH_FAILED",
            message="Failed to dispatch system stop action.",
            details={"action": SYSTEM_ACTION_STOP, "error": str(exc)},
        )

    return {
        "ok": True,
        "action": SYSTEM_ACTION_STOP,
        "status": SYSTEM_ACTION_STATUS_ACCEPTED,
        "request_id": request_id,
    }


@app.post("/api/system/restart")
async def restart_system_stack() -> dict[str, object]:
    """Dispatch a full stack restart operation.

    Purpose:
        Allow dashboard users to restart the compose stack through one API
        action instead of running stop and start commands manually.
    Args:
        None.
    Output:
        Returns accepted payload with request identifier.
    """

    try:
        request_id = _dispatch_system_lifecycle_action(SYSTEM_ACTION_RESTART)
    except OSError as exc:
        _raise_api_error(
            status_code=500,
            code="SYSTEM_ACTION_DISPATCH_FAILED",
            message="Failed to dispatch system restart action.",
            details={"action": SYSTEM_ACTION_RESTART, "error": str(exc)},
        )

    return {
        "ok": True,
        "action": SYSTEM_ACTION_RESTART,
        "status": SYSTEM_ACTION_STATUS_ACCEPTED,
        "request_id": request_id,
    }


@app.post("/api/system/fetch-jobs")
async def fetch_jobs_now() -> dict[str, object]:
    """Dispatch an immediate discovery run by restarting the discovery container.

    Purpose:
        Allow users to trigger on-demand job discovery without restarting the
        full stack. Restarting only the discovery container causes `run_discovery.sh`
        to execute `main.py` immediately before sleeping, so new jobs appear
        within seconds rather than waiting for the 30-minute polling interval.
    Output:
        Returns accepted payload with request identifier.
    """

    try:
        request_id = _dispatch_system_lifecycle_action(SYSTEM_ACTION_FETCH_JOBS)
    except OSError as exc:
        _raise_api_error(
            status_code=500,
            code="SYSTEM_ACTION_DISPATCH_FAILED",
            message="Failed to dispatch discovery fetch action.",
            details={"action": SYSTEM_ACTION_FETCH_JOBS, "error": str(exc)},
        )

    return {
        "ok": True,
        "action": SYSTEM_ACTION_FETCH_JOBS,
        "status": SYSTEM_ACTION_STATUS_ACCEPTED,
        "request_id": request_id,
    }


@app.get("/api/dashboard/stats")
async def get_dashboard_stats() -> dict[str, object]:
    """Return KPI cards and non-trend chart datasets for the dashboard page.

    Purpose:
        Power the dashboard card values and secondary charts from live SQLite
        data with one request.
    Args:
        None.
    Output:
        Returns cards, source breakdown, pipeline funnel, and applications-over-
        time datasets in snake_case.
    """

    db_path = str(resolve_database_path())
    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        await db.migrate_apply_schema()

        assert db.conn is not None
        conn = db.conn

        totals_cursor = await conn.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM job_postings) AS jobs_discovered_total,
                (SELECT COUNT(*)
                 FROM job_postings
                 WHERE fetched_at >= datetime('now', 'start of day')) AS jobs_discovered_today,
                (SELECT COUNT(*) FROM tailor_runs WHERE status = 'SUCCESS') AS resumes_tailored_total,
                (SELECT COUNT(*)
                 FROM tailor_runs
                 WHERE status = 'SUCCESS'
                   AND completed_at >= datetime('now', 'start of day')) AS resumes_tailored_today,
                (SELECT COUNT(*) FROM job_postings WHERE status = 'APPLIED') AS applications_sent_total,
                (SELECT COUNT(*)
                 FROM apply_handoffs
                 WHERE handoff_status = 'APPROVED'
                   AND reviewed_at >= datetime('now', 'start of day')) AS applications_sent_today,
                (SELECT COUNT(*)
                 FROM apply_handoffs
                 WHERE handoff_status = 'PENDING_REVIEW') AS awaiting_review_total
            """
        )
        totals_row = await totals_cursor.fetchone()
        assert totals_row is not None  # SELECT with aggregate always returns a row

        source_cursor = await conn.execute(
            """
            SELECT source, COUNT(*) AS count
            FROM job_postings
            GROUP BY source
            ORDER BY count DESC
            """
        )
        source_rows = await source_cursor.fetchall()
        source_counts: dict[str, int] = {}
        for row in source_rows:
            source_label = _source_label(str(row["source"]))
            source_counts[source_label] = source_counts.get(source_label, 0) + int(
                row["count"] or 0
            )

        source_total = sum(source_counts.values())
        source_breakdown = [
            {
                "source": source_label,
                "count": count,
                "pct": 0.0 if source_total == 0 else (count / source_total) * 100.0,
            }
            for source_label, count in sorted(
                source_counts.items(),
                key=lambda item: item[1],
                reverse=True,
            )
        ]

        funnel_cursor = await conn.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM job_postings) AS discovered,
                (SELECT COUNT(*)
                 FROM job_postings
                 WHERE status IN ('QUALIFIED', 'APPLIED', 'REJECTED')) AS qualified,
                (SELECT COUNT(DISTINCT job_hash)
                 FROM tailor_runs
                 WHERE status = 'SUCCESS') AS tailored,
                (SELECT COUNT(DISTINCT job_hash)
                 FROM review_runs
                 WHERE status = 'SUCCESS') AS reviewed,
                (SELECT COUNT(*)
                 FROM job_postings
                 WHERE status = 'APPLIED') AS applied,
                (SELECT COUNT(*)
                 FROM apply_handoffs
                 WHERE handoff_status = 'PENDING_REVIEW') AS human_review
            """
        )
        funnel_row = await funnel_cursor.fetchone()
        assert funnel_row is not None  # SELECT with aggregate always returns a row

        now_utc = datetime.now(tz=UTC)
        labels = [
            "12 AM",
            "3 AM",
            "6 AM",
            "9 AM",
            "12 PM",
            "3 PM",
            "6 PM",
            "9 PM",
            "NOW",
        ]
        applications_over_time: list[dict[str, object]] = []

        for hour_index, label in enumerate(labels):
            if label == "NOW":
                cutoff = now_utc
            else:
                cutoff = now_utc.replace(
                    hour=(hour_index * 3) % 24,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
            cutoff_text = cutoff.strftime("%Y-%m-%d %H:%M:%S")

            applied_cursor = await conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM apply_handoffs
                WHERE handoff_status = 'APPROVED'
                  AND reviewed_at IS NOT NULL
                  AND reviewed_at <= ?
                  AND reviewed_at >= datetime('now', 'start of day')
                """,
                (cutoff_text,),
            )
            applied_row = await applied_cursor.fetchone()

            tailored_cursor = await conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM tailor_runs
                WHERE status = 'SUCCESS'
                  AND completed_at IS NOT NULL
                  AND completed_at <= ?
                  AND completed_at >= datetime('now', 'start of day')
                """,
                (cutoff_text,),
            )
            tailored_row = await tailored_cursor.fetchone()

            applications_over_time.append(
                {
                    "label": label,
                    "applied": int(applied_row["count"]) if applied_row else 0,
                    "tailored": int(tailored_row["count"]) if tailored_row else 0,
                }
            )

    return {
        "ok": True,
        "jobs_discovered_total": int(totals_row["jobs_discovered_total"] or 0),
        "jobs_discovered_today": int(totals_row["jobs_discovered_today"] or 0),
        "resumes_tailored_total": int(totals_row["resumes_tailored_total"] or 0),
        "resumes_tailored_today": int(totals_row["resumes_tailored_today"] or 0),
        "applications_sent_total": int(totals_row["applications_sent_total"] or 0),
        "applications_sent_today": int(totals_row["applications_sent_today"] or 0),
        "awaiting_review_total": int(totals_row["awaiting_review_total"] or 0),
        "source_breakdown": source_breakdown,
        "pipeline_funnel": [
            {"stage": "DISCOVERED", "count": int(funnel_row["discovered"] or 0)},
            {"stage": "QUALIFIED", "count": int(funnel_row["qualified"] or 0)},
            {"stage": "TAILORED", "count": int(funnel_row["tailored"] or 0)},
            {"stage": "REVIEWED", "count": int(funnel_row["reviewed"] or 0)},
            {"stage": "APPLIED", "count": int(funnel_row["applied"] or 0)},
            {"stage": "HUMAN_REVIEW", "count": int(funnel_row["human_review"] or 0)},
        ],
        "applications_over_time": applications_over_time,
    }


@app.get("/api/dashboard/discovery-trend")
async def get_dashboard_discovery_trend(
    range_key: Literal["7d", "30d"] = Query(default="7d", alias="range"),
) -> dict[str, object]:
    """Return discovery-trend bars for dashboard range toggle states.

    Purpose:
        Provide the bar-chart dataset for 7-day or 30-day dashboard trend views.
    Args:
        range_key: Requested range (`7d` or `30d`) from query parameter.
    Output:
        Returns ordered trend points with `label` and `count`.
    """

    day_count = 7 if range_key == "7d" else 30
    start_date = (datetime.now(tz=UTC) - timedelta(days=day_count - 1)).date()
    labels = [start_date + timedelta(days=offset) for offset in range(day_count)]

    db_path = str(resolve_database_path())
    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        assert db.conn is not None
        conn = db.conn

        cursor = await conn.execute(
            """
            SELECT date(fetched_at) AS day, COUNT(*) AS count
            FROM job_postings
            WHERE fetched_at >= datetime('now', ?)
            GROUP BY day
            ORDER BY day ASC
            """,
            (f"-{day_count - 1} days",),
        )
        rows = await cursor.fetchall()

    counts_by_day = {str(row["day"]): int(row["count"]) for row in rows}
    points = [
        {
            "label": date_value.strftime("%a")
            if range_key == "7d"
            else date_value.strftime("%m/%d"),
            "date": date_value.isoformat(),
            "count": counts_by_day.get(date_value.isoformat(), 0),
        }
        for date_value in labels
    ]

    return {
        "ok": True,
        "range": range_key,
        "points": points,
    }


@app.get("/api/jobs")
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

    db_path = str(resolve_database_path())
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


@app.get("/api/jobs/{job_hash}/resume")
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


@app.get("/api/human-review")
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

    db_path = str(resolve_database_path())
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


@app.post("/api/human-review/{handoff_id}/complete")
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

    db_path = str(resolve_database_path())
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


@app.post("/api/human-review/{handoff_id}/dismiss")
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

    db_path = str(resolve_database_path())
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


def _serialize_failure_record(
    *,
    failure_id: str,
    stage: str,
    company: str,
    position: str,
    error_text: str,
    attempts: int,
    max_attempts: int,
    status: str,
    platform: str,
    job_posting_url: str,
    event_time: str,
) -> dict[str, object]:
    """Build one normalized failure record for the failures endpoint.

    Purpose:
        Keep the failures API response shape stable across stage-specific SQL
        sources (gate/tailor/review/apply).
    Args:
        failure_id: Stage-qualified failure identifier.
        stage: Pipeline stage label.
        company: Company name for the failed job.
        position: Job title for the failed job.
        error_text: Raw error text.
        attempts: Number of attempts recorded.
        max_attempts: Maximum retry attempts configured for the stage.
        status: Retry status (`RETRYING` or `EXHAUSTED`).
        platform: Source platform label.
        job_posting_url: Original job posting URL.
        event_time: Timestamp string for sorting.
    Output:
        Returns normalized failure record dictionary.
    """

    short_error_code = (
        error_text.split("\n", maxsplit=1)[0].split(":", maxsplit=1)[0].strip().upper()
    )
    if short_error_code == "":
        short_error_code = "UNKNOWN_FAILURE"

    return {
        "id": failure_id,
        "stage": stage,
        "company": company,
        "position": position,
        "error_code": short_error_code,
        "attempts": attempts,
        "max_attempts": max_attempts,
        "time": event_time,
        "status": status,
        "error_trace": [line for line in error_text.splitlines() if line.strip() != ""],
        "platform": platform,
        "job_posting_url": job_posting_url,
    }


@app.get("/api/failures")
async def get_failures(
    search: str = Query(default=""),
    stage: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> dict[str, object]:
    """Return unified failures feed across gate/tailor/review/apply stages.

    Purpose:
        Replace mock failures data with actionable stage failure records and
        summary stats needed by the failures page.
    Args:
        search: Optional text filter across company/title/error/stage fields.
        stage: Optional exact stage filter.
        status: Optional exact retry-status filter.
        page: 1-based page number.
        page_size: Number of rows per page.
    Output:
        Returns summary + paginated failures list.
    """

    max_gate_retries = _load_positive_int_env("AGENT_MAX_RETRIES", 3)
    max_tailor_retries = _load_positive_int_env("TAILOR_MAX_RETRIES", 2)
    max_review_retries = _load_positive_int_env("REVIEW_MAX_RETRIES", 2)
    max_apply_retries = _load_positive_int_env("APPLY_MAX_RETRIES", 2)

    db_path = str(resolve_database_path())
    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        await db.migrate_agent_schema()
        await db.migrate_tailor_schema()
        await db.migrate_review_schema()
        await db.migrate_apply_schema()

        assert db.conn is not None
        conn = db.conn

        gate_cursor = await conn.execute(
            """
            SELECT
                jp.job_hash,
                jp.company,
                jp.title,
                jp.agent_error,
                jp.agent_retry_count,
                jp.agent_failed_at,
                jp.source,
                jp.source_url
            FROM job_postings jp
            WHERE jp.agent_failed_at IS NOT NULL
            """
        )
        gate_rows = await gate_cursor.fetchall()

        tailor_cursor = await conn.execute(
            """
            SELECT
                tr.id,
                tr.job_hash,
                tr.error,
                tr.next_retry_at,
                COALESCE(tr.completed_at, tr.started_at) AS event_time,
                jp.company,
                jp.title,
                jp.source,
                jp.source_url,
                (
                    SELECT COUNT(*)
                    FROM tailor_runs tr_count
                    WHERE tr_count.job_hash = tr.job_hash
                      AND tr_count.status = 'FAILED'
                ) AS attempts
            FROM tailor_runs tr
            JOIN job_postings jp ON jp.job_hash = tr.job_hash
            WHERE tr.status = 'FAILED'
            """
        )
        tailor_rows = await tailor_cursor.fetchall()

        review_cursor = await conn.execute(
            """
            SELECT
                rr.id,
                rr.job_hash,
                rr.error,
                rr.next_retry_at,
                COALESCE(rr.completed_at, rr.started_at) AS event_time,
                jp.company,
                jp.title,
                jp.source,
                jp.source_url,
                (
                    SELECT COUNT(*)
                    FROM review_runs rr_count
                    WHERE rr_count.tailor_run_id = rr.tailor_run_id
                      AND rr_count.status = 'FAILED'
                ) AS attempts
            FROM review_runs rr
            JOIN job_postings jp ON jp.job_hash = rr.job_hash
            WHERE rr.status = 'FAILED'
            """
        )
        review_rows = await review_cursor.fetchall()

        apply_cursor = await conn.execute(
            """
            SELECT
                ar.id,
                ar.job_hash,
                ar.error,
                ar.next_retry_at,
                COALESCE(ar.completed_at, ar.started_at) AS event_time,
                jp.company,
                jp.title,
                jp.source,
                jp.source_url,
                (
                    SELECT COUNT(*)
                    FROM apply_runs ar_count
                    WHERE ar_count.review_run_id = ar.review_run_id
                      AND ar_count.status = 'FAILED'
                ) AS attempts
            FROM apply_runs ar
            JOIN job_postings jp ON jp.job_hash = ar.job_hash
            WHERE ar.status = 'FAILED'
            """
        )
        apply_rows = await apply_cursor.fetchall()

    records: list[dict[str, object]] = []

    for row in gate_rows:
        records.append(
            _serialize_failure_record(
                failure_id=f"GATE:{row['job_hash']}",
                stage="GATE",
                company=str(row["company"]),
                position=str(row["title"]),
                error_text=str(row["agent_error"] or "Unknown gate failure."),
                attempts=int(row["agent_retry_count"] or 0),
                max_attempts=max_gate_retries,
                status="EXHAUSTED",
                platform=_source_label(str(row["source"])),
                job_posting_url=str(row["source_url"]),
                event_time=str(row["agent_failed_at"]),
            )
        )

    for row in tailor_rows:
        records.append(
            _serialize_failure_record(
                failure_id=f"TAILOR:{row['id']}",
                stage="TAILORING",
                company=str(row["company"]),
                position=str(row["title"]),
                error_text=str(row["error"] or "Unknown tailor failure."),
                attempts=int(row["attempts"] or 0),
                max_attempts=max_tailor_retries,
                status="RETRYING" if row["next_retry_at"] is not None else "EXHAUSTED",
                platform=_source_label(str(row["source"])),
                job_posting_url=str(row["source_url"]),
                event_time=str(row["event_time"]),
            )
        )

    for row in review_rows:
        records.append(
            _serialize_failure_record(
                failure_id=f"REVIEW:{row['id']}",
                stage="REVIEW",
                company=str(row["company"]),
                position=str(row["title"]),
                error_text=str(row["error"] or "Unknown review failure."),
                attempts=int(row["attempts"] or 0),
                max_attempts=max_review_retries,
                status="RETRYING" if row["next_retry_at"] is not None else "EXHAUSTED",
                platform=_source_label(str(row["source"])),
                job_posting_url=str(row["source_url"]),
                event_time=str(row["event_time"]),
            )
        )

    for row in apply_rows:
        records.append(
            _serialize_failure_record(
                failure_id=f"APPLY:{row['id']}",
                stage="APPLY",
                company=str(row["company"]),
                position=str(row["title"]),
                error_text=str(row["error"] or "Unknown apply failure."),
                attempts=int(row["attempts"] or 0),
                max_attempts=max_apply_retries,
                status="RETRYING" if row["next_retry_at"] is not None else "EXHAUSTED",
                platform=_source_label(str(row["source"])),
                job_posting_url=str(row["source_url"]),
                event_time=str(row["event_time"]),
            )
        )

    records.sort(key=lambda item: str(item["time"]), reverse=True)

    filtered_records = records
    if stage is not None and stage.strip() != "":
        normalized_stage = stage.strip().upper()
        filtered_records = [
            item
            for item in filtered_records
            if str(item["stage"]).upper() == normalized_stage
        ]
    if status is not None and status.strip() != "":
        normalized_status = status.strip().upper()
        filtered_records = [
            item
            for item in filtered_records
            if str(item["status"]).upper() == normalized_status
        ]
    if search.strip():
        search_value = search.strip().lower()
        filtered_records = [
            item
            for item in filtered_records
            if search_value in str(item["company"]).lower()
            or search_value in str(item["position"]).lower()
            or search_value in str(item["error_code"]).lower()
            or search_value in str(item["stage"]).lower()
        ]

    total_items = len(filtered_records)
    offset = (page - 1) * page_size
    page_items = filtered_records[offset : offset + page_size]
    total_pages = max((total_items + page_size - 1) // page_size, 1)

    stage_counts: dict[str, int] = {}
    for item in records:
        stage_label = str(item["stage"])
        stage_counts[stage_label] = stage_counts.get(stage_label, 0) + 1

    most_failing_stage = "NONE"
    most_failing_count = 0
    if stage_counts:
        most_failing_stage, most_failing_count = max(
            stage_counts.items(),
            key=lambda item: item[1],
        )

    last_24h_cutoff = datetime.now(tz=UTC) - timedelta(hours=24)
    last_24h_count = 0
    for item in records:
        try:
            item_time = datetime.fromisoformat(str(item["time"]).replace(" ", "T"))
        except ValueError:
            continue
        if item_time.tzinfo is None:
            item_time = item_time.replace(tzinfo=UTC)
        if item_time >= last_24h_cutoff:
            last_24h_count += 1

    exhausted_count = len([item for item in records if item["status"] == "EXHAUSTED"])
    retry_success_rate = (
        0.0
        if len(records) == 0
        else max(0.0, ((len(records) - exhausted_count) / len(records)) * 100.0)
    )

    return {
        "ok": True,
        "summary": {
            "total_failures": len(records),
            "last_24_hours": last_24h_count,
            "most_failing_stage": {
                "stage": most_failing_stage,
                "count": most_failing_count,
            },
            "retry_success_rate_pct": retry_success_rate,
        },
        "page": page,
        "page_size": page_size,
        "total_items": total_items,
        "total_pages": total_pages,
        "items": page_items,
    }


@app.post("/api/failures/{failure_id}/retry")
async def retry_failure(failure_id: str) -> dict[str, object]:
    """Requeue one failed stage record based on its stage-qualified ID.

    Purpose:
        Implement stage-specific retry semantics requested by the dashboard,
        including gate/tailor/review/apply reset behavior.
    Args:
        failure_id: Stage-qualified identifier in `<STAGE>:<id>` format.
    Output:
        Returns canonical mutation success payload.
    """

    if ":" not in failure_id:
        _raise_api_error(
            status_code=400,
            code="INVALID_FAILURE_ID",
            message="Failure ID must use '<STAGE>:<id>' format.",
        )

    stage_key, stage_value = failure_id.split(":", maxsplit=1)
    stage_key = stage_key.strip().upper()

    db_path = str(resolve_database_path())
    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        await db.migrate_agent_schema()
        await db.migrate_tailor_schema()
        await db.migrate_review_schema()
        await db.migrate_apply_schema()

        assert db.conn is not None
        conn = db.conn

        if stage_key == "GATE":
            await db.reset_agent_failure_state(stage_value)
            return {"ok": True, "failure_id": failure_id, "requeued": True}

        if stage_key == "TAILOR":
            cursor = await conn.execute(
                "SELECT job_hash FROM tailor_runs WHERE id = ?",
                (int(stage_value),),
            )
            row = await cursor.fetchone()
            if row is None:
                _raise_api_error(
                    status_code=404,
                    code="FAILURE_NOT_FOUND",
                    message="Tailor failure record was not found.",
                )
            await db.reset_tailor_failure_state(job_hash=str(row["job_hash"]))
            return {"ok": True, "failure_id": failure_id, "requeued": True}

        if stage_key == "REVIEW":
            cursor = await conn.execute(
                "SELECT job_hash FROM review_runs WHERE id = ?",
                (int(stage_value),),
            )
            row = await cursor.fetchone()
            if row is None:
                _raise_api_error(
                    status_code=404,
                    code="FAILURE_NOT_FOUND",
                    message="Review failure record was not found.",
                )
            deleted_count = await db.reset_review_failure_state(
                job_hash=str(row["job_hash"])
            )
            return {
                "ok": True,
                "failure_id": failure_id,
                "requeued": deleted_count > 0,
                "deleted_failures": deleted_count,
            }

        if stage_key == "APPLY":
            cursor = await conn.execute(
                "SELECT job_hash FROM apply_runs WHERE id = ?",
                (int(stage_value),),
            )
            row = await cursor.fetchone()
            if row is None:
                _raise_api_error(
                    status_code=404,
                    code="FAILURE_NOT_FOUND",
                    message="Apply failure record was not found.",
                )
            deleted_count = await db.reset_apply_failure_state(
                job_hash=str(row["job_hash"])
            )
            return {
                "ok": True,
                "failure_id": failure_id,
                "requeued": deleted_count > 0,
                "deleted_failures": deleted_count,
            }

    _raise_api_error(
        status_code=409,
        code="NON_RETRIABLE_FAILURE",
        message="This failure stage is not retriable.",
    )
    raise AssertionError("Unreachable: _raise_api_error always raises HTTPException.")


@app.get("/api/costs/stats")
async def get_cost_stats() -> dict[str, object]:
    """Return high-level cost KPIs for the cost-tracking page cards.

    Purpose:
        Power the top KPI cards for month spend, average per application, and
        today's cost-event count.
    Args:
        None.
    Output:
        Returns cost-stat payload in snake_case.
    """

    db_path = str(resolve_database_path())
    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        await db.migrate_cost_schema()
        await db.migrate_apply_schema()

        assert db.conn is not None
        conn = db.conn

        total_cursor = await conn.execute(
            """
            SELECT COALESCE(SUM(cost_usd), 0.0) AS total_spend_usd
            FROM cost_events
            WHERE strftime('%Y-%m', recorded_at) = strftime('%Y-%m', 'now')
            """
        )
        total_row = await total_cursor.fetchone()
        assert total_row is not None  # COALESCE aggregate always returns a row

        today_calls_cursor = await conn.execute(
            """
            SELECT COUNT(*) AS api_calls_today
            FROM cost_events
            WHERE recorded_at >= datetime('now', 'start of day')
            """
        )
        today_calls_row = await today_calls_cursor.fetchone()
        assert today_calls_row is not None  # SELECT COUNT(*) always returns a row

        applied_cursor = await conn.execute(
            """
            SELECT COUNT(*) AS applied_count
            FROM apply_handoffs
            WHERE handoff_status = 'APPROVED'
            """
        )
        applied_row = await applied_cursor.fetchone()
        assert applied_row is not None  # SELECT COUNT(*) always returns a row

    total_spend = float(total_row["total_spend_usd"] or 0.0)
    applied_count = int(applied_row["applied_count"] or 0)
    average_cost_per_application = (
        0.0 if applied_count == 0 else total_spend / float(applied_count)
    )

    return {
        "ok": True,
        "total_spend_usd": total_spend,
        "avg_cost_per_application_usd": average_cost_per_application,
        "api_calls_today": int(today_calls_row["api_calls_today"] or 0),
    }


@app.get("/api/costs/daily-trend")
async def get_cost_daily_trend(
    range_key: Literal["7d", "30d", "all"] = Query(default="7d", alias="range"),
) -> dict[str, object]:
    """Return spend trend bars grouped by day or month.

    Purpose:
        Provide chart data for the Cost Tracking range toggle options.
    Args:
        range_key: Requested range (`7d`, `30d`, or `all`).
    Output:
        Returns ordered trend points with spend amounts.
    """

    db_path = str(resolve_database_path())
    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        await db.migrate_cost_schema()

        assert db.conn is not None
        conn = db.conn

        if range_key == "all":
            cursor = await conn.execute(
                """
                SELECT strftime('%Y-%m', recorded_at) AS bucket,
                       COALESCE(SUM(cost_usd), 0.0) AS spend_usd
                FROM cost_events
                GROUP BY bucket
                ORDER BY bucket ASC
                """
            )
            rows = await cursor.fetchall()
            monthly_points = [
                {
                    "label": str(row["bucket"]),
                    "spend_usd": float(row["spend_usd"] or 0.0),
                }
                for row in rows
            ]
            return {"ok": True, "range": range_key, "points": monthly_points}

        day_count = 7 if range_key == "7d" else 30
        cursor = await conn.execute(
            """
            SELECT date(recorded_at) AS bucket,
                   COALESCE(SUM(cost_usd), 0.0) AS spend_usd
            FROM cost_events
            WHERE recorded_at >= datetime('now', ?)
            GROUP BY bucket
            ORDER BY bucket ASC
            """,
            (f"-{day_count - 1} days",),
        )
        rows = await cursor.fetchall()

    spend_by_day = {str(row["bucket"]): float(row["spend_usd"] or 0.0) for row in rows}
    start_day = (datetime.now(tz=UTC) - timedelta(days=day_count - 1)).date()
    points: list[dict[str, object]] = []
    for offset in range(day_count):
        day_value = start_day + timedelta(days=offset)
        points.append(
            {
                "label": day_value.strftime("%a")
                if range_key == "7d"
                else day_value.strftime("%m/%d"),
                "date": day_value.isoformat(),
                "spend_usd": spend_by_day.get(day_value.isoformat(), 0.0),
            }
        )

    return {
        "ok": True,
        "range": range_key,
        "points": points,
    }


@app.get("/api/costs/by-stage")
async def get_costs_by_stage() -> dict[str, object]:
    """Return current-month spend grouped by pipeline stage.

    Purpose:
        Power the stage breakdown bars on the Cost Tracking page.
    Args:
        None.
    Output:
        Returns stage spend rows with stage label and USD totals.
    """

    db_path = str(resolve_database_path())
    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        await db.migrate_cost_schema()

        assert db.conn is not None
        conn = db.conn

        cursor = await conn.execute(
            """
            SELECT stage, COALESCE(SUM(cost_usd), 0.0) AS spend_usd
            FROM cost_events
            WHERE strftime('%Y-%m', recorded_at) = strftime('%Y-%m', 'now')
            GROUP BY stage
            ORDER BY spend_usd DESC
            """
        )
        rows = await cursor.fetchall()

    return {
        "ok": True,
        "items": [
            {
                "stage": str(row["stage"]),
                "spend_usd": float(row["spend_usd"] or 0.0),
            }
            for row in rows
        ],
    }


@app.get("/api/settings/api-keys")
async def get_api_keys() -> dict[str, object]:
    """Return configured status for all allowed API key names.

    Purpose:
        Drive the settings UI key list without exposing secret values.
    Args:
        None.
    Output:
        Returns ok + keys list with name and configured flag per entry.
    """

    return _build_api_keys_response()


@app.put("/api/settings/api-keys/{key_name}")
async def upsert_api_key(
    key_name: str, payload: ApiKeyUpsertRequest
) -> dict[str, object]:
    """Add or replace one API key secret in the project .env file.

    Purpose:
        Persist user-supplied API key secrets durably so the pipeline worker
        picks them up on next run.
    Args:
        key_name: Environment variable name from the URL path.
        payload: Parsed request body with the new secret value.
    Output:
        Returns updated API key status payload.
    Raises:
        HTTPException 400: When key_name is not in the allowed set.
    """

    if key_name not in ALLOWED_API_KEY_NAMES:
        _raise_api_error(
            status_code=400,
            code="UNKNOWN_API_KEY",
            message=f"'{key_name}' is not a supported API key name.",
        )
    _write_env_key(key_name, payload.value.strip())
    return _build_api_keys_response()


@app.delete("/api/settings/api-keys/{key_name}")
async def delete_api_key(key_name: str) -> dict[str, object]:
    """Remove one API key entry from the project .env file.

    Purpose:
        Allow users to fully revoke a stored key from the settings UI.
    Args:
        key_name: Environment variable name from the URL path.
    Output:
        Returns updated API key status payload.
    Raises:
        HTTPException 400: When key_name is not in the allowed set.
    """

    if key_name not in ALLOWED_API_KEY_NAMES:
        _raise_api_error(
            status_code=400,
            code="UNKNOWN_API_KEY",
            message=f"'{key_name}' is not a supported API key name.",
        )
    _delete_env_key(key_name)
    return _build_api_keys_response()


@app.get("/api/settings/service-tier")
async def get_service_tier() -> dict[str, object]:
    """Return the currently active service tier.

    Purpose:
        Let the settings UI pre-select the correct tier card on load.
    Args:
        None.
    Output:
        Returns ok + tier string.
    """

    db_path = str(resolve_database_path())
    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        await db.migrate_cost_schema()
        tier = await db.get_service_tier()
    return {"ok": True, "tier": tier}


@app.put("/api/settings/service-tier")
async def update_service_tier(payload: ServiceTierUpdateRequest) -> dict[str, object]:
    """Persist the selected service tier.

    Purpose:
        Keep the active pipeline tier durable so worker scripts respect the
        user's chosen automation level on their next run.
    Args:
        payload: Parsed request body with the new tier identifier.
    Output:
        Returns ok + updated tier string.
    Raises:
        HTTPException 400: When the requested tier is not a valid identifier.
    """

    if payload.tier not in ALLOWED_SERVICE_TIERS:
        _raise_api_error(
            status_code=400,
            code="UNKNOWN_SERVICE_TIER",
            message=f"'{payload.tier}' is not a valid service tier.",
        )
    db_path = str(resolve_database_path())
    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        await db.migrate_cost_schema()
        tier = await db.set_service_tier(payload.tier)
    return {"ok": True, "tier": tier}


@app.get("/api/budget")
async def get_budget() -> dict[str, object]:
    """Return current monthly budget settings and utilization.

    Purpose:
        Provide budget widget data for settings and sidebar views.
    Args:
        None.
    Output:
        Returns monthly budget + spend snapshot.
    """

    db_path = str(resolve_database_path())
    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        await db.migrate_cost_schema()
        budget_payload = await db.get_budget_settings()

    return {
        "ok": True,
        **budget_payload,
    }


@app.put("/api/budget")
async def update_budget(payload: BudgetUpdateRequest) -> dict[str, object]:
    """Persist an updated monthly budget value.

    Purpose:
        Back settings-panel budget saves with durable SQLite persistence.
    Args:
        payload: Parsed budget update payload.
    Output:
        Returns canonical mutation success payload with updated snapshot.
    """

    db_path = str(resolve_database_path())
    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        await db.migrate_cost_schema()
        updated_payload = await db.set_budget_settings(
            monthly_budget_usd=payload.monthly_budget_usd,
        )

    return {
        "ok": True,
        **updated_payload,
    }


@app.get("/api/settings/files")
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

    return {
        "ok": True,
        "resume": _resolve_settings_file_metadata(SETTINGS_RESUME_PATH),
        "profile": _resolve_settings_file_metadata(SETTINGS_PROFILE_PATH),
    }


@app.get("/api/settings/profile")
async def get_profile_settings() -> dict[str, object]:
    """Return candidate profile settings with raw YAML and parsed fields.

    Purpose:
        Power guided and advanced profile editors from one read endpoint.
    Args:
        None.
    Output:
        Returns metadata, raw YAML text, and parsed profile payload.
    """

    yaml_text = _read_settings_text(SETTINGS_PROFILE_PATH, file_label="Profile")
    parsed_payload = _parse_yaml_mapping(yaml_text=yaml_text, context="profile")
    profile_document = _validate_candidate_profile_document(parsed_payload)

    return {
        "ok": True,
        "metadata": _resolve_settings_file_metadata(SETTINGS_PROFILE_PATH),
        "yaml_text": yaml_text,
        **_normalize_candidate_profile_output(profile_document),
    }


@app.put("/api/settings/profile")
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

    parsed_payload = _parse_yaml_mapping(yaml_text=payload.yaml_text, context="profile")
    profile_document = _validate_candidate_profile_document(parsed_payload)

    _backup_settings_file(SETTINGS_PROFILE_PATH, file_label="Profile")
    SETTINGS_PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PROFILE_PATH.write_text(payload.yaml_text, encoding="utf-8")
    load_candidate_context.cache_clear()

    return {
        "ok": True,
        "metadata": _resolve_settings_file_metadata(SETTINGS_PROFILE_PATH),
        "yaml_text": payload.yaml_text,
        **_normalize_candidate_profile_output(profile_document),
    }


@app.put("/api/settings/profile/structured")
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

    existing_payload: dict[str, object]
    if SETTINGS_PROFILE_PATH.exists():
        existing_text = _read_settings_text(SETTINGS_PROFILE_PATH, file_label="Profile")
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
    _backup_settings_file(SETTINGS_PROFILE_PATH, file_label="Profile")
    persisted_yaml = _persist_yaml_mapping(
        SETTINGS_PROFILE_PATH,
        payload=merged_payload,
    )
    load_candidate_context.cache_clear()

    return {
        "ok": True,
        "metadata": _resolve_settings_file_metadata(SETTINGS_PROFILE_PATH),
        "yaml_text": persisted_yaml,
        **_normalize_candidate_profile_output(profile_document),
    }


@app.post("/api/settings/resume")
async def upload_resume_file(file: UploadFile = File(...)) -> dict[str, object]:
    """Replace the canonical base resume YAML from settings upload.

    Purpose:
        Persist resume YAML updates from the settings panel.
    Args:
        file: Uploaded resume YAML file.
    Output:
        Returns canonical mutation success payload with updated metadata.
    """

    text = await _read_uploaded_text(file)
    parsed_payload = _parse_yaml_mapping(yaml_text=text, context="resume")
    resume_document = _validate_resume_document(parsed_payload)
    _backup_settings_file(SETTINGS_RESUME_PATH, file_label="Resume")
    save_resume_yaml(path=SETTINGS_RESUME_PATH, resume_content=resume_document)

    return {
        "ok": True,
        "resume": _resolve_settings_file_metadata(SETTINGS_RESUME_PATH),
    }


@app.post("/api/settings/resume/pdf")
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
    import io

    import pypdf

    raw_bytes = await file.read()
    try:
        reader = pypdf.PdfReader(io.BytesIO(raw_bytes))
    except Exception as exc:
        _raise_api_error(
            status_code=400,
            code="INVALID_PDF",
            message=f"Could not read PDF file: {exc}",
        )
        raise AssertionError("Unreachable")

    extracted_pages: list[str] = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        extracted_pages.append(page_text)

    extracted_text = "\n".join(extracted_pages).strip()

    raw_pdf_path = SETTINGS_RESUME_PATH.parent / "resume_raw.pdf"
    raw_pdf_path.parent.mkdir(parents=True, exist_ok=True)
    raw_pdf_path.write_bytes(raw_bytes)

    candidate_name = ""
    candidate_phone = ""
    candidate_email = ""
    if SETTINGS_PROFILE_PATH.exists():
        try:
            profile_text = SETTINGS_PROFILE_PATH.read_text(encoding="utf-8")
            profile_data = yaml.safe_load(profile_text) or {}
            contact = (profile_data.get("profile") or {}).get("contact") or {}
            candidate_name = str(contact.get("full_name") or "").strip()
            candidate_phone = str(contact.get("phone") or "").strip()
            candidate_email = str(contact.get("email") or "").strip()
        except (OSError, yaml.YAMLError, KeyError, TypeError, AttributeError):
            pass

    from src.agents.resume_tailor_pi.schemas import (
        EducationSection,
        ExperienceSection,
        PersonalSection,
        ProjectsSection,
        ResumeContent,
        SkillsAchievementsSection,
    )

    stub_resume = ResumeContent(
        personal=PersonalSection(
            name=candidate_name or "Your Name",
            phone=candidate_phone or "",
            email=candidate_email or "",
            links=[],
        ),
        education=EducationSection(),
        experience=ExperienceSection(),
        projects=ProjectsSection(),
        skills_achievements=SkillsAchievementsSection(),
    )

    _backup_settings_file(SETTINGS_RESUME_PATH, file_label="Resume")
    save_resume_yaml(path=SETTINGS_RESUME_PATH, resume_content=stub_resume)

    return {
        "ok": True,
        "resume": _resolve_settings_file_metadata(SETTINGS_RESUME_PATH),
        "pdf_pages": len(reader.pages),
        "extracted_chars": len(extracted_text),
    }


@app.get("/api/settings/resume")
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

    yaml_text = _read_settings_text(SETTINGS_RESUME_PATH, file_label="Resume")
    parsed_payload = _parse_yaml_mapping(yaml_text=yaml_text, context="resume")
    resume_document = _validate_resume_document(parsed_payload)

    return {
        "ok": True,
        "metadata": _resolve_settings_file_metadata(SETTINGS_RESUME_PATH),
        "yaml_text": yaml_text,
        "resume": resume_document.model_dump(mode="json"),
        "counts": _resume_counts(resume_document),
    }


@app.put("/api/settings/resume")
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

    parsed_payload = _parse_yaml_mapping(yaml_text=payload.yaml_text, context="resume")
    resume_document = _validate_resume_document(parsed_payload)
    _backup_settings_file(SETTINGS_RESUME_PATH, file_label="Resume")
    save_resume_yaml(path=SETTINGS_RESUME_PATH, resume_content=resume_document)
    persisted_yaml = _read_settings_text(SETTINGS_RESUME_PATH, file_label="Resume")

    return {
        "ok": True,
        "metadata": _resolve_settings_file_metadata(SETTINGS_RESUME_PATH),
        "yaml_text": persisted_yaml,
        "resume": resume_document.model_dump(mode="json"),
        "counts": _resume_counts(resume_document),
    }


@app.put("/api/settings/resume/structured")
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

    resume_document = _validate_resume_document(payload.resume)
    _backup_settings_file(SETTINGS_RESUME_PATH, file_label="Resume")
    save_resume_yaml(path=SETTINGS_RESUME_PATH, resume_content=resume_document)
    persisted_yaml = _read_settings_text(SETTINGS_RESUME_PATH, file_label="Resume")

    return {
        "ok": True,
        "metadata": _resolve_settings_file_metadata(SETTINGS_RESUME_PATH),
        "yaml_text": persisted_yaml,
        "resume": resume_document.model_dump(mode="json"),
        "counts": _resume_counts(resume_document),
    }


@app.post("/api/settings/resume/tex")
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

    tex_text = await _read_uploaded_text(file)
    prepared_tex_text = tex_text
    if SETTINGS_RESUME_PATH.exists():
        fallback_yaml_text = _read_settings_text(
            SETTINGS_RESUME_PATH, file_label="Resume"
        )
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

    SETTINGS_RESUME_TEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_RESUME_TEX_PATH.write_text(prepared_tex_text, encoding="utf-8")
    migrated_output_path = SETTINGS_RESUME_PATH.with_name(
        f"{SETTINGS_RESUME_PATH.stem}.migrated.tmp{SETTINGS_RESUME_PATH.suffix}"
    )

    try:
        migrated_resume = migrate_resume_tex_to_yaml(
            resume_tex_path=SETTINGS_RESUME_TEX_PATH,
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
    _backup_settings_file(SETTINGS_RESUME_PATH, file_label="Resume")
    try:
        migrated_output_path.replace(SETTINGS_RESUME_PATH)
    except OSError as exc:
        _raise_api_error(
            status_code=500,
            code="RESUME_REPLACE_FAILED",
            message="Failed to persist converted resume YAML file.",
            details={
                "output_yaml_path": str(SETTINGS_RESUME_PATH),
                "temporary_yaml_path": str(migrated_output_path),
                "error": str(exc),
            },
        )

    persisted_yaml = _read_settings_text(SETTINGS_RESUME_PATH, file_label="Resume")
    return {
        "ok": True,
        "metadata": _resolve_settings_file_metadata(SETTINGS_RESUME_PATH),
        "yaml_text": persisted_yaml,
        "resume": migrated_resume.model_dump(mode="json"),
        "counts": _resume_counts(migrated_resume),
        "migration": {
            "source_tex_path": str(SETTINGS_RESUME_TEX_PATH),
            "output_yaml_path": str(SETTINGS_RESUME_PATH),
            "normalized_input": prepared_tex_text != tex_text,
            **_resume_counts(migrated_resume),
        },
    }


@app.post("/api/settings/profile")
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

    text = await _read_uploaded_text(file)
    parsed_payload = _parse_yaml_mapping(yaml_text=text, context="profile")
    _validate_candidate_profile_document(parsed_payload)
    _backup_settings_file(SETTINGS_PROFILE_PATH, file_label="Profile")
    SETTINGS_PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PROFILE_PATH.write_text(text, encoding="utf-8")

    load_candidate_context.cache_clear()

    return {
        "ok": True,
        "profile": _resolve_settings_file_metadata(SETTINGS_PROFILE_PATH),
    }


@app.get("/api/settings/resume/download")
async def download_resume_file() -> FileResponse:
    """Download the canonical base resume YAML file.

    Purpose:
        Provide settings-panel download action for current resume YAML.
    Args:
        None.
    Output:
        Returns FileResponse for `config/resume_content.yaml`.
    """

    if not SETTINGS_RESUME_PATH.exists():
        _raise_api_error(
            status_code=404,
            code="FILE_NOT_FOUND",
            message="Resume file does not exist.",
        )
    return FileResponse(
        SETTINGS_RESUME_PATH,
        media_type="application/x-yaml",
        filename=SETTINGS_RESUME_PATH.name,
    )


@app.get("/api/settings/profile/download")
async def download_profile_file() -> FileResponse:
    """Download the candidate profile YAML file.

    Purpose:
        Provide settings-panel download action for current profile YAML.
    Args:
        None.
    Output:
        Returns FileResponse for `config/candidate_profile.yaml`.
    """

    if not SETTINGS_PROFILE_PATH.exists():
        _raise_api_error(
            status_code=404,
            code="FILE_NOT_FOUND",
            message="Profile file does not exist.",
        )
    return FileResponse(
        SETTINGS_PROFILE_PATH,
        media_type="application/x-yaml",
        filename=SETTINGS_PROFILE_PATH.name,
    )


# ── Fetcher Settings Endpoints ───────────────────────────────────────


@app.get("/api/settings/filters")
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


@app.put("/api/settings/filters")
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


@app.get("/api/settings/sources")
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


@app.put("/api/settings/sources")
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


# ---------------------------------------------------------------------------
# AI Provider Configuration + Codex Device Auth
# ---------------------------------------------------------------------------


@app.get("/api/settings/ai-provider")
async def get_ai_provider() -> dict[str, object]:
    """Return the current AI provider configuration.

    Returns:
        JSON with the current provider mode, type, and auth status.
    """
    from src.providers.factory import get_codex_provider, build_provider_from_env
    from src.providers.types import ProviderMode, ProviderType

    codex = get_codex_provider()
    codex_authenticated = codex.is_authenticated

    # Read stored config from env or defaults.
    current_mode = "codex" if codex_authenticated else "byok"

    # Detect which BYOK key is configured.
    byok_provider = "none"
    has_openai = bool(os.environ.get("OPENAI_API_KEY"))
    has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))
    has_google = bool(os.environ.get("GOOGLE_API_KEY"))
    if has_openai:
        byok_provider = "openai"
    elif has_anthropic:
        byok_provider = "anthropic"
    elif has_google:
        byok_provider = "gemini"

    return {
        "ok": True,
        "config": {
            "mode": current_mode,
            "providerType": byok_provider if current_mode == "byok" else "codex",
            "codexAuthenticated": codex_authenticated,
            "hasOpenaiKey": has_openai,
            "hasAnthropicKey": has_anthropic,
            "hasGoogleKey": has_google,
        },
    }


@app.put("/api/settings/ai-provider")
async def put_ai_provider(payload: ProviderConfigRequest) -> dict[str, object]:
    """Update the AI provider configuration.

    For BYOK mode, persists the API key to the .env file.
    For Codex mode, verifies that device auth is complete.

    Args:
        payload: New provider configuration.

    Returns:
        JSON confirming the configuration update.
    """
    from src.providers.types import ProviderMode

    if payload.mode == ProviderMode.CODEX.value:
        from src.providers.factory import get_codex_provider

        codex = get_codex_provider()
        if not codex.is_authenticated:
            _raise_api_error(
                status_code=400,
                code="CODEX_NOT_AUTHENTICATED",
                message="Complete Codex device auth before selecting Codex mode.",
            )
        return {"ok": True, "mode": "codex", "provider": "codex"}

    # BYOK mode — persist the key to .env.
    key_env_map = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "gemini": "GOOGLE_API_KEY",
        "openrouter": "OPENAI_API_KEY",
    }
    env_key_name = key_env_map.get(payload.provider_type)
    if not env_key_name:
        _raise_api_error(
            status_code=400,
            code="INVALID_PROVIDER",
            message=f"Unsupported provider type: {payload.provider_type}",
        )

    if not payload.api_key:
        _raise_api_error(
            status_code=400,
            code="MISSING_API_KEY",
            message="API key is required for BYOK mode.",
        )

    _write_env_key(env_key_name, payload.api_key.strip())

    # For OpenRouter, also persist the base URL.
    if payload.provider_type == "openrouter" and payload.base_url:
        _write_env_key("OPENROUTER_BASE_URL", payload.base_url.strip())

    return {
        "ok": True,
        "mode": "byok",
        "provider": payload.provider_type,
    }


@app.post("/api/settings/codex-auth/start")
async def start_codex_auth() -> dict[str, object]:
    """Initiate the Codex OAuth device authorization flow.

    Returns:
        JSON with the verification URL and one-time user code.
    """
    from src.providers.factory import get_codex_provider

    codex = get_codex_provider()

    try:
        snapshot = await codex.start_device_auth()
        return {"ok": True, "auth": snapshot.to_dict()}
    except Exception as exc:
        _raise_api_error(
            status_code=500,
            code="CODEX_AUTH_FAILED",
            message=str(exc),
        )


@app.get("/api/settings/codex-auth/status")
async def get_codex_auth_status() -> dict[str, object]:
    """Return the current Codex device auth session status.

    Returns:
        JSON with the auth snapshot (status, URL, code, expiry).
    """
    from src.providers.factory import get_codex_provider

    codex = get_codex_provider()
    snapshot = codex.get_auth_snapshot()
    return {"ok": True, "auth": snapshot.to_dict()}


@app.post("/api/settings/codex-auth/disconnect")
async def disconnect_codex_auth() -> dict[str, object]:
    """Log out of Codex and clear the active session.

    Returns:
        JSON confirming the logout with an idle auth snapshot.
    """
    from src.providers.factory import get_codex_provider

    codex = get_codex_provider()

    try:
        snapshot = await codex.disconnect()
        return {"ok": True, "auth": snapshot.to_dict()}
    except Exception as exc:
        _raise_api_error(
            status_code=500,
            code="CODEX_DISCONNECT_FAILED",
            message=str(exc),
        )


# ── Onboarding status ──────────────────────────────────────────────


@app.get("/api/settings/onboarding-status")
async def get_onboarding_status() -> dict[str, object]:
    """Check whether the user has completed initial onboarding.

    Returns:
        JSON with completion state and step details.
    """
    profile_path = SETTINGS_PROFILE_PATH
    profile_exists = profile_path.exists()
    profile_has_content = False

    if profile_exists:
        try:
            content = profile_path.read_text(encoding="utf-8").strip()
            profile_has_content = len(content) > 50
        except OSError:
            pass

    completed_steps: list[str] = []
    missing_steps: list[str] = []

    if profile_has_content:
        completed_steps.append("profile")
    else:
        missing_steps.append("profile")

    resume_path = SETTINGS_RESUME_PATH
    if resume_path.exists():
        completed_steps.append("resume")
    else:
        missing_steps.append("resume")

    is_complete = "profile" in completed_steps and "resume" in completed_steps

    return {
        "ok": True,
        "is_complete": is_complete,
        "completed_steps": completed_steps,
        "missing_steps": missing_steps,
    }


# ── SSE pipeline progress ─────────────────────────────────────────

@app.get("/api/pipeline/progress")
async def pipeline_progress_sse() -> StreamingResponse:
    """Server-sent events endpoint for real-time pipeline progress.

    Returns:
        Streaming SSE response with pipeline stage updates.
    """

    async def event_stream() -> AsyncIterator[str]:
        """Yield SSE-formatted pipeline progress events.

        Yields:
            SSE-formatted data strings.
        """
        yield f"data: {json.dumps({'stage': 'idle', 'source': '', 'progress': 0, 'jobsFound': 0, 'errors': []})}\n\n"

        heartbeat_interval_seconds = 30
        while True:
            await asyncio.sleep(heartbeat_interval_seconds)
            yield ": heartbeat\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Manual job import ──────────────────────────────────────────────


@app.post("/api/jobs/import")
async def import_job_manually(payload: JobImportRequest) -> dict[str, object]:
    """Import a job posting manually from URL or pasted text.

    Args:
        payload: Import request with mode and associated data.

    Returns:
        JSON with created job identifier.
    """
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
    db_path = str(resolve_database_path())

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
    "resolve_database_path",
]
