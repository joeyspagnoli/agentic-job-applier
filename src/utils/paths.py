"""Resolve repository-relative filesystem paths used by operational scripts."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def resolve_repo_root() -> Path:
    """Resolve the repository root path using stable project markers.

    Purpose:
        Provide a refactor-safe root resolver so modules can build absolute
        paths without relying on fragile hardcoded parent-depth traversal.
    Args:
        None.
    Output:
        Returns the absolute repository root path.
    """

    candidate = Path(__file__).resolve()
    project_markers = ("pyproject.toml", ".git", "AGENTS.md")
    for parent in candidate.parents:
        if any((parent / marker).exists() for marker in project_markers):
            return parent

    raise RuntimeError("Could not resolve repository root from project markers")


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

    repo_root = resolve_repo_root()

    # Loading the repo-local `.env` here keeps standalone scripts consistent
    # with `main.py` without requiring callers to duplicate dotenv handling.
    load_dotenv(repo_root / ".env")

    db_path = Path(os.getenv("DATABASE_PATH", "data/jobs.db")).expanduser()
    if not db_path.is_absolute():
        db_path = repo_root / db_path
    return db_path
