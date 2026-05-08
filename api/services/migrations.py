"""Startup migrations and FastAPI lifespan hook for the API runtime."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.database.db_manager import DatabaseManager
from src.utils.paths import resolve_database_path


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
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
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
