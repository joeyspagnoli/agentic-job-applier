"""Startup migrations and FastAPI lifespan hook for the API runtime."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import FastAPI
from pydantic import ValidationError

from src.config.schema import CandidateProfile
from src.database.db_manager import DatabaseManager
from src.utils.paths import resolve_database_path

from api.services.supervisor import start_supervisor
from api.services.supervisor import stop_supervisor

logger = logging.getLogger(__name__)


def _validate_candidate_profile_on_startup(profile_path: Path) -> None:
    """Validate candidate_profile.yaml against CandidateProfile schema.

    Purpose:
        Surface misconfigured or incomplete profile YAML at process boot
        with actionable error output so operators can fix the problem before
        any apply-finisher run begins.
    Args:
        profile_path: Absolute path to the candidate_profile.yaml file.
    Output:
        Returns ``None`` when validation passes.
    Raises:
        SystemExit: When the profile file exists but fails schema validation,
            after logging every invalid-field path with a sample fix hint.
    """

    if not profile_path.exists():
        logger.warning(
            "candidate_profile.yaml not found at %s — skipping startup validation.",
            profile_path,
        )
        return

    raw_text = profile_path.read_text(encoding="utf-8")
    parsed = yaml.safe_load(raw_text) or {}
    try:
        CandidateProfile.model_validate(parsed)
    except ValidationError as exc:
        logger.error(
            "candidate_profile.yaml failed schema validation (%d error(s)):",
            exc.error_count(),
        )
        for error in exc.errors():
            loc = " -> ".join(str(part) for part in error["loc"])
            logger.error("  [%s] %s  (type=%s)", loc, error["msg"], error["type"])
        logger.error(
            "Fix hint: open config/candidate_profile.yaml and ensure the "
            "`apply_prefs` block is present with valid values.  "
            "See src/config/schema.py for the full field reference."
        )
        raise SystemExit(1) from exc


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

    from api.config import SETTINGS_PROFILE_PATH  # noqa: PLC0415 — late import mirrors router pattern

    _validate_candidate_profile_on_startup(SETTINGS_PROFILE_PATH)
    await _run_startup_migrations()
    await start_supervisor()
    try:
        yield
    finally:
        await stop_supervisor()
