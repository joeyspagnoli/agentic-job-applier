"""Dashboard router (KPI stats, discovery trend)."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter
from fastapi import Query

from src.database.db_manager import DatabaseManager

from api.services.sources import _source_label

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats")
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

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    db_path = str(_main.resolve_database_path())
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


@router.get("/discovery-trend")
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

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    day_count = 7 if range_key == "7d" else 30
    start_date = (datetime.now(tz=UTC) - timedelta(days=day_count - 1)).date()
    labels = [start_date + timedelta(days=offset) for offset in range(day_count)]

    db_path = str(_main.resolve_database_path())
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
