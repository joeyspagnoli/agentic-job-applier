"""Startup migrations and FastAPI lifespan hook for the API runtime."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.database.db_manager import DatabaseManager
from src.utils.paths import resolve_database_path

from api.services.supervisor import start_supervisor
from api.services.supervisor import stop_supervisor


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
    """Run startup migrations and start the worker supervisor.

    Purpose:
        Guarantee schema readiness on process boot, then spawn the
        in-process supervisor that owns discovery / gate / tailor /
        apply asyncio loops, and finally tear those tasks down on
        shutdown.
    Args:
        _app: FastAPI app instance supplied by framework lifecycle hooks.
    Output:
        Yields control back to FastAPI after migrations complete and the
        supervisor is running. Cancels supervised tasks on shutdown.
    """

    await _run_startup_migrations()
    await start_supervisor()
    try:
        yield
    finally:
        await stop_supervisor()
