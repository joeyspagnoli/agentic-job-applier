"""Cover status-command behavior for partial schema and untrusted output."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from scripts import status as status_script


def _create_minimal_job_postings_table(db_path: Path) -> None:
    """Create minimal `job_postings` schema needed by status script.

    Purpose:
        Build intentionally partial schemas for degraded-behavior status tests.
    Args:
        db_path: SQLite database path to initialize.
    Output:
        Returns `None` after creating a reduced `job_postings` table.
    """

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE job_postings (
                job_hash TEXT PRIMARY KEY,
                source TEXT,
                source_url TEXT,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                company TEXT,
                title TEXT,
                status TEXT DEFAULT 'NEW'
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def test_status_handles_missing_crawl_and_daily_tables_gracefully(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify status output degrades gracefully when optional tables are absent.

    Purpose:
        Keep operational status command usable on partially initialized schema.
    Args:
        monkeypatch: Pytest fixture used to point script at temp DB.
        capsys: Pytest fixture used to capture terminal output.
    Output:
        Returns `None`; test passes when missing-table messages are printed.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "jobs.db"
        _create_minimal_job_postings_table(db_path)

        monkeypatch.setattr(status_script, "resolve_database_path", lambda: db_path)
        status_script.print_status()
        output = capsys.readouterr().out

    assert "Recent crawls: unavailable (crawl_history table missing)" in output
    assert "Daily statistics: unavailable (daily_stats table missing)" in output


def test_status_handles_missing_agent_columns_without_crashing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify status command works when agent columns are absent.

    Purpose:
        Prevent script crashes on pre-migration databases lacking gate columns.
    Args:
        monkeypatch: Pytest fixture used to point script at temp DB.
        capsys: Pytest fixture used to capture terminal output.
    Output:
        Returns `None`; test passes when script omits gate section cleanly.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "jobs.db"
        _create_minimal_job_postings_table(db_path)
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                """
                INSERT INTO job_postings(job_hash, source, source_url, company, title, status)
                VALUES ('hash1', 'source', 'url', 'company', 'title', 'NEW')
                """
            )
            conn.commit()
        finally:
            conn.close()

        monkeypatch.setattr(status_script, "resolve_database_path", lambda: db_path)
        status_script.print_status()
        output = capsys.readouterr().out

    assert "Total jobs in database: 1" in output
    assert "Gate processing:" not in output


def test_status_sanitizes_control_sequences_from_terminal_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify status output strips terminal control characters from fields.

    Purpose:
        Reduce log spoofing risk when DB contains untrusted source/error text.
    Args:
        monkeypatch: Pytest fixture used to point script at temp DB.
        capsys: Pytest fixture used to capture terminal output.
    Output:
        Returns `None`; test passes when output contains no escape characters.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "jobs.db"
        conn = sqlite3.connect(db_path)
        try:
            conn.executescript(
                """
                CREATE TABLE job_postings (
                    job_hash TEXT PRIMARY KEY,
                    source TEXT,
                    source_url TEXT,
                    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    company TEXT,
                    title TEXT,
                    status TEXT DEFAULT 'NEW'
                );
                CREATE TABLE crawl_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT,
                    company TEXT,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    status TEXT DEFAULT 'FAILED',
                    jobs_found INTEGER DEFAULT 0,
                    jobs_new INTEGER DEFAULT 0,
                    error_message TEXT
                );
                CREATE TABLE daily_stats (
                    date TEXT PRIMARY KEY,
                    total_jobs_discovered INTEGER DEFAULT 0,
                    jobs_new INTEGER DEFAULT 0,
                    jobs_duplicate INTEGER DEFAULT 0,
                    sources_crawled INTEGER DEFAULT 0,
                    sources_failed INTEGER DEFAULT 0
                );
                """
            )
            conn.execute(
                """
                INSERT INTO job_postings(job_hash, source, source_url, company, title, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "hash1",
                    "\x1b[31msource\x1b[0m",
                    "url",
                    "\x1b[32mcompany\x1b[0m",
                    "title",
                    "NEW",
                ),
            )
            conn.execute(
                """
                INSERT INTO crawl_history(source, company, status, jobs_found, jobs_new, error_message)
                VALUES (?, ?, 'FAILED', 0, 0, ?)
                """,
                (
                    "\x1b[31mcrawl\x1b[0m",
                    "\x1b[32mco\x1b[0m",
                    "\x1b[35merror\x1b[0m",
                ),
            )
            conn.commit()
        finally:
            conn.close()

        monkeypatch.setattr(status_script, "resolve_database_path", lambda: db_path)
        status_script.print_status()
        output = capsys.readouterr().out

    assert "\x1b" not in output


def test_status_reports_missing_job_postings_table(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify status prints actionable message when core table is missing.

    Purpose:
        Keep failure mode readable for partially initialized or corrupt DB files.
    Args:
        monkeypatch: Pytest fixture used to point script at temp DB.
        capsys: Pytest fixture used to capture terminal output.
    Output:
        Returns `None`; test passes when missing-table message is printed.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "jobs.db"
        sqlite3.connect(db_path).close()

        monkeypatch.setattr(status_script, "resolve_database_path", lambda: db_path)
        status_script.print_status()
        output = capsys.readouterr().out

    assert "job_postings table is missing" in output
