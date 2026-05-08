"""Budget settings router."""

from __future__ import annotations

from fastapi import APIRouter

from src.database.db_manager import DatabaseManager

from api.schemas.common import BudgetUpdateRequest

router = APIRouter(prefix="/api/budget", tags=["budget"])


@router.get("")
async def get_budget() -> dict[str, object]:
    """Return current monthly budget settings and utilization.

    Purpose:
        Provide budget widget data for settings and sidebar views.
    Args:
        None.
    Output:
        Returns monthly budget + spend snapshot.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    db_path = str(_main.resolve_database_path())
    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        await db.migrate_cost_schema()
        budget_payload = await db.get_budget_settings()

    return {
        "ok": True,
        **budget_payload,
    }


@router.put("")
async def update_budget(payload: BudgetUpdateRequest) -> dict[str, object]:
    """Persist an updated monthly budget value.

    Purpose:
        Back settings-panel budget saves with durable SQLite persistence.
    Args:
        payload: Parsed budget update payload.
    Output:
        Returns canonical mutation success payload with updated snapshot.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    db_path = str(_main.resolve_database_path())
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
