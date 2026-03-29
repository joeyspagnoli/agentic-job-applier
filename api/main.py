"""Expose FastAPI endpoints and static dashboard serving for the project.

This module provides the unified runtime boundary for the dashboard product:
- `/api/*` JSON endpoints backed by SQLite
- Static serving for built React assets in `dashboard/dist`
- SPA fallback for client-side routing
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from typing import Literal

from fastapi import Body
from fastapi import FastAPI
from fastapi import File
from fastapi import HTTPException
from fastapi import Query
from fastapi import UploadFile
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pydantic import Field
import yaml

from src.agents.root_apply_decider.prompts import load_candidate_context
from src.database.db_manager import DatabaseManager
from src.utils.paths import resolve_database_path
from src.utils.paths import resolve_repo_root

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
DEFAULT_POLLING_SECONDS = 30

DASHBOARD_DIST_DIR = resolve_repo_root() / "dashboard" / "dist"
DASHBOARD_ASSETS_DIR = DASHBOARD_DIST_DIR / "assets"
DASHBOARD_INDEX_FILE = DASHBOARD_DIST_DIR / "index.html"

SETTINGS_RESUME_PATH = resolve_repo_root() / "config" / "resume_content.yaml"
SETTINGS_PROFILE_PATH = resolve_repo_root() / "config" / "candidate_profile.yaml"


class ReviewerActionRequest(BaseModel):
    """Request payload for human-review action endpoints.

    Attributes:
        reviewer_notes: Optional note to persist with the reviewer action.
    """

    reviewer_notes: str | None = Field(
        default=None,
        description="Optional note to persist with this reviewer action.",
    )


class BudgetUpdateRequest(BaseModel):
    """Request payload for monthly budget updates.

    Attributes:
        monthly_budget_usd: New non-negative budget in USD.
    """

    monthly_budget_usd: float = Field(
        ge=0,
        description="New monthly budget limit in USD.",
    )


def _error_response(
    *,
    code: str,
    message: str,
    details: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build one deterministic API error payload.

    Purpose:
        Keep every endpoint error response shape consistent for frontend
        consumers and deterministic integration tests.
    Args:
        code: Stable machine-readable error code.
        message: Human-readable error summary.
        details: Optional structured details for debugging or UI hints.
    Output:
        Returns a dictionary payload with `ok`, `code`, `message`, and `details`.
    """

    return {
        "ok": False,
        "code": code,
        "message": message,
        "details": details or {},
    }


def _raise_api_error(
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, object] | None = None,
) -> None:
    """Raise an HTTPException with the project's standard error payload.

    Purpose:
        Centralize FastAPI error raising so route handlers stay focused on
        business logic and all errors share the same response contract.
    Args:
        status_code: HTTP status code for the response.
        code: Stable machine-readable error code.
        message: Human-readable error message.
        details: Optional structured details payload.
    Output:
        Raises `HTTPException` and does not return.
    """

    raise HTTPException(
        status_code=status_code,
        detail=_error_response(code=code, message=message, details=details),
    )


def _load_positive_int_env(name: str, default_value: int) -> int:
    """Load one positive integer environment value with fallback behavior.

    Purpose:
        Keep retry-limit and polling defaults predictable when environment
        values are missing, malformed, or invalid.
    Args:
        name: Environment variable name to read.
        default_value: Fallback value when env parsing fails.
    Output:
        Returns a strictly positive integer.
    """

    raw_value = os.getenv(name)
    if raw_value is None:
        return default_value
    try:
        parsed_value = int(raw_value)
    except ValueError:
        return default_value
    if parsed_value <= 0:
        return default_value
    return parsed_value


def _source_label(raw_source: str) -> str:
    """Map internal source identifiers to compact frontend labels.

    Purpose:
        Normalize source strings from multiple fetchers to one stable UI enum
        without changing existing database source values.
    Args:
        raw_source: Source string persisted in `job_postings.source`.
    Output:
        Returns one of `GREENHOUSE`, `WORKDAY`, or `JOBSPY`.
    """

    normalized = raw_source.lower()
    if "greenhouse" in normalized:
        return "GREENHOUSE"
    if "workday" in normalized or "apify" in normalized:
        return "WORKDAY"
    return "JOBSPY"


def _salary_display(
    salary_min: int | None,
    salary_max: int | None,
    salary_currency: str | None,
) -> str:
    """Render salary fields to a single human-readable display string.

    Purpose:
        Keep salary formatting consistent across all jobs-table rows.
    Args:
        salary_min: Minimum salary in cents, when available.
        salary_max: Maximum salary in cents, when available.
        salary_currency: Currency code (for example, USD).
    Output:
        Returns a display string suitable for direct table rendering.
    """

    currency = (salary_currency or "USD").upper()
    if salary_min is None and salary_max is None:
        return "—"
    if salary_min is not None and salary_max is not None:
        return f"{currency} ${salary_min / 100:,.0f}–${salary_max / 100:,.0f}"
    if salary_min is not None:
        return f"{currency} ${salary_min / 100:,.0f}+"
    return f"Up to {currency} ${salary_max / 100:,.0f}"


def _parse_gate_result(agent_result: str | None) -> tuple[str, str]:
    """Parse gate decision and explanation from stored JSON payload.

    Purpose:
        Decode serialized gate output safely for jobs-table detail rendering
        without failing requests on malformed legacy payloads.
    Args:
        agent_result: Raw serialized gate payload from `job_postings.agent_result`.
    Output:
        Returns `(decision, explanation)` with safe fallback values.
    """

    if not agent_result:
        return "UNKNOWN", "No gate reasoning is available for this job yet."

    try:
        payload = json.loads(agent_result)
    except json.JSONDecodeError:
        return "UNKNOWN", "Gate result could not be parsed from stored payload."

    decision = str(payload.get("decision") or "UNKNOWN").upper()
    explanation = str(payload.get("explanation") or "No explanation provided.")
    return decision, explanation


def _build_pipeline_steps(
    *,
    job_status: str,
    has_tailor_success: bool,
    has_review_success: bool,
    has_apply_success: bool,
    has_pending_handoff: bool,
) -> list[dict[str, str]]:
    """Construct timeline step states for one jobs-table expansion panel.

    Purpose:
        Keep pipeline-step rendering deterministic using persisted stage
        outcomes and the current top-level job status.
    Args:
        job_status: Coarse job status from `job_postings.status`.
        has_tailor_success: Whether at least one tailor run succeeded.
        has_review_success: Whether at least one review run succeeded.
        has_apply_success: Whether at least one apply run succeeded.
        has_pending_handoff: Whether a pending human-review handoff exists.
    Output:
        Returns six step records with `label` and `status` keys.
    """

    status_upper = job_status.upper()
    discovered = "complete"
    qualified = (
        "complete"
        if status_upper in {"QUALIFIED", "APPLIED", "REJECTED", "FILTERED"}
        else "pending"
    )
    tailored = "complete" if has_tailor_success else "pending"
    reviewed = "complete" if has_review_success else "pending"
    applied = "complete" if has_apply_success else "pending"
    human_review = "active" if has_pending_handoff else "pending"

    return [
        {"label": "DISCOVERED", "status": discovered},
        {"label": "QUALIFIED", "status": qualified},
        {"label": "TAILORED", "status": tailored},
        {"label": "REVIEWED", "status": reviewed},
        {"label": "APPLIED", "status": applied},
        {"label": "HUMAN REVIEW", "status": human_review},
    ]


def _parse_unresolved_fields(raw_json: str | None) -> list[dict[str, str]]:
    """Normalize stored unresolved-field payloads for human-review UI cards.

    Purpose:
        Convert flexible worker JSON output into a stable structure consumed by
        the review dashboard table expansion panel.
    Args:
        raw_json: Serialized unresolved-fields JSON from apply telemetry.
    Output:
        Returns a list with `field_name`, `ai_answer`, `reasoning`, and
        `answer_confidence` keys.
    """

    if not raw_json:
        return []

    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError:
        return []

    if not isinstance(payload, list):
        return []

    normalized_items: list[dict[str, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue

        field_name = str(
            item.get("label")
            or item.get("field_name")
            or item.get("name")
            or "Unresolved field"
        )
        ai_answer = str(
            item.get("recommended_value")
            or item.get("suggested_value")
            or item.get("value")
            or "Manual response required"
        )
        reasoning = str(
            item.get("reason")
            or item.get("hint")
            or "Generated from captured form context."
        )

        confidence_raw = str(item.get("confidence") or "medium").lower()
        if confidence_raw in {"high", "medium", "low"}:
            answer_confidence = confidence_raw
        else:
            answer_confidence = "medium"

        normalized_items.append(
            {
                "field_name": field_name,
                "ai_answer": ai_answer,
                "reasoning": reasoning,
                "answer_confidence": answer_confidence,
            }
        )

    return normalized_items


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


async def _run_startup_migrations() -> None:
    """Run idempotent DB migrations required by API endpoints.

    Purpose:
        Ensure old local databases are upgraded before serving requests so API
        handlers can rely on all required tables and columns.
    Args:
        None.
    Output:
        Returns `None` after migrations complete.
    """

    db_path = str(resolve_database_path())
    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        await db.migrate_agent_schema()
        await db.migrate_tailor_schema()
        await db.migrate_review_schema()
        await db.migrate_apply_schema()
        await db.migrate_cost_schema()


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """Run startup migrations before the API begins serving traffic.

    Purpose:
        Guarantee schema readiness on process boot while keeping startup logic
        colocated with the FastAPI application instance.
    Args:
        _app: FastAPI app instance supplied by framework lifecycle hooks.
    Output:
        Yields control back to FastAPI after migrations complete.
    """

    await _run_startup_migrations()
    yield


app = FastAPI(lifespan=_lifespan)

if DASHBOARD_ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=DASHBOARD_ASSETS_DIR), name="assets")


@app.exception_handler(HTTPException)
async def _http_exception_handler(_request, exc: HTTPException) -> JSONResponse:
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

        now_utc = datetime.now(tz=UTC)
        labels = ["12 AM", "3 AM", "6 AM", "9 AM", "12 PM", "3 PM", "6 PM", "9 PM", "NOW"]
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
            "label": date_value.strftime("%a") if range_key == "7d" else date_value.strftime("%m/%d"),
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
        filters.append("jp.source = ?")
        params.append(source.strip())

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
        gate_decision, gate_reasoning = _parse_gate_result(str(row["agent_result"] or ""))
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
        unresolved_fields = _parse_unresolved_fields(str(row["unresolved_fields_json"] or ""))
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
                "resume_file_name": Path(str(row["resume_pdf_path"] or "resume.pdf")).name,
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
            item for item in filtered_records if str(item["stage"]).upper() == normalized_stage
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
            deleted_count = await db.reset_review_failure_state(job_hash=str(row["job_hash"]))
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
            deleted_count = await db.reset_apply_failure_state(job_hash=str(row["job_hash"]))
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

        today_calls_cursor = await conn.execute(
            """
            SELECT COUNT(*) AS api_calls_today
            FROM cost_events
            WHERE recorded_at >= datetime('now', 'start of day')
            """
        )
        today_calls_row = await today_calls_cursor.fetchone()

        applied_cursor = await conn.execute(
            """
            SELECT COUNT(*) AS applied_count
            FROM apply_handoffs
            WHERE handoff_status = 'APPROVED'
            """
        )
        applied_row = await applied_cursor.fetchone()

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
            points = [
                {
                    "label": str(row["bucket"]),
                    "spend_usd": float(row["spend_usd"] or 0.0),
                }
                for row in rows
            ]
            return {"ok": True, "range": range_key, "points": points}

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
                "label": day_value.strftime("%a") if range_key == "7d" else day_value.strftime("%m/%d"),
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
    try:
        yaml.safe_load(text)
    except yaml.YAMLError:
        _raise_api_error(
            status_code=400,
            code="INVALID_YAML",
            message="Uploaded resume file must be valid YAML.",
        )

    SETTINGS_RESUME_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_RESUME_PATH.write_text(text, encoding="utf-8")

    return {
        "ok": True,
        "resume": _resolve_settings_file_metadata(SETTINGS_RESUME_PATH),
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
    try:
        yaml.safe_load(text)
    except yaml.YAMLError:
        _raise_api_error(
            status_code=400,
            code="INVALID_YAML",
            message="Uploaded profile file must be valid YAML.",
        )

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
