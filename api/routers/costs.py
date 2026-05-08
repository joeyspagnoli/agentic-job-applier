"""Cost-tracking router (stats, daily-trend, by-stage)."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter
from fastapi import Query

from src.database.db_manager import DatabaseManager

router = APIRouter(prefix="/api/costs", tags=["costs"])


@router.get("/stats")
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

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    db_path = str(_main.resolve_database_path())
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


@router.get("/daily-trend")
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

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    db_path = str(_main.resolve_database_path())
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


@router.get("/by-stage")
async def get_costs_by_stage() -> dict[str, object]:
    """Return current-month spend grouped by pipeline stage.

    Purpose:
        Power the stage breakdown bars on the Cost Tracking page.
    Args:
        None.
    Output:
        Returns stage spend rows with stage label and USD totals.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    db_path = str(_main.resolve_database_path())
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
