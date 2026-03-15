"""Resolve repository-relative filesystem paths used by operational scripts."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def resolve_database_path() -> Path:
    """Resolve the SQLite database path from environment or repo defaults.

    Purpose:
        Keep every script aligned on the same `DATABASE_PATH` lookup behavior
        while making relative paths stable even when commands run outside the
        repository root.
    Args:
        None.
    Output:
        Returns an absolute filesystem path to the SQLite database file.
    """

    repo_root = Path(__file__).resolve().parents[2]

    # Loading the repo-local `.env` here keeps standalone scripts consistent
    # with `main.py` without requiring callers to duplicate dotenv handling.
    load_dotenv(repo_root / ".env")

    db_path = Path(os.getenv("DATABASE_PATH", "data/jobs.db")).expanduser()
    if not db_path.is_absolute():
        db_path = repo_root / db_path
    return db_path
