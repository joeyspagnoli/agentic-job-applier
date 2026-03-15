"""Cover time-window query semantics and agent-schema migration readiness."""

from __future__ import annotations

import tempfile
from datetime import datetime
from datetime import timedelta
from pathlib import Path

import pytest

from scripts import query_jobs as query_jobs_script
from scripts import status as status_script
from src.database.db_manager import DatabaseManager
from src.models.job_posting import JobPosting


@pytest.mark.asyncio
async def test_status_failed_24h_filter_uses_sqlite_compatible_timestamps(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    """Verify status script reports only failures from the last 24 hours.

    Purpose:
        Prevent timestamp-format mismatches from dropping recent failed crawls
        out of the operational status output.
    Args:
        monkeypatch: Pytest fixture used to point status script at test DB.
        capsys: Pytest fixture used to capture script output.
    Output:
        Returns `None`; the test passes when only recent failures are counted.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "jobs.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            assert db.conn is not None

            recent = (datetime.utcnow() - timedelta(hours=2)).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            old = (datetime.utcnow() - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
            await db.conn.execute(
                """
                INSERT INTO crawl_history
                    (source, company, started_at, completed_at, status, jobs_found, jobs_new, error_message)
                VALUES (?, ?, ?, ?, 'FAILED', 0, 0, ?)
                """,
                ("greenhouse", "RecentCo", recent, recent, "recent error"),
            )
            await db.conn.execute(
                """
                INSERT INTO crawl_history
                    (source, company, started_at, completed_at, status, jobs_found, jobs_new, error_message)
                VALUES (?, ?, ?, ?, 'FAILED', 0, 0, ?)
                """,
                ("greenhouse", "OldCo", old, old, "old error"),
            )
            await db.conn.commit()

        monkeypatch.setattr(status_script, "resolve_database_path", lambda: db_path)
        status_script.print_status()
        output = capsys.readouterr().out

    assert "Failed crawls (last 24h): 1" in output
    assert "RecentCo" in output
    assert "old error" not in output


@pytest.mark.asyncio
async def test_query_jobs_new_only_filters_by_today_window(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    """Verify `--new` style filtering includes only current-day jobs.

    Purpose:
        Ensure query script uses expected today-window semantics for operator
        inspection workflows.
    Args:
        monkeypatch: Pytest fixture used to point query script at test DB.
        capsys: Pytest fixture used to capture script output.
    Output:
        Returns `None`; the test passes when only today rows are printed.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "jobs.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            assert db.conn is not None

            today_job = JobPosting(
                source="test",
                source_url="https://example.com/jobs/today",
                company="TodayCo",
                title="Engineer",
                description="Today posting",
            )
            old_job = JobPosting(
                source="test",
                source_url="https://example.com/jobs/old",
                company="OldCo",
                title="Engineer",
                description="Old posting",
            )
            await db.insert_job(today_job.to_db_dict())
            await db.insert_job(old_job.to_db_dict())
            await db.conn.execute(
                "UPDATE job_postings SET fetched_at = datetime('now', '-2 days') WHERE company = 'OldCo'"
            )
            await db.conn.commit()

        monkeypatch.setattr(query_jobs_script, "resolve_database_path", lambda: db_path)
        query_jobs_script.query_jobs(new_only=True, limit=10)
        output = capsys.readouterr().out

    assert "TodayCo" in output
    assert "OldCo" not in output


@pytest.mark.asyncio
async def test_get_jobs_today_counts_only_current_day_rows():
    """Verify database helper counts rows within today's timestamp window.

    Purpose:
        Protect the today-count helper used by end-of-cycle logging.
    Args:
        None.
    Output:
        Returns `None`; the test passes when only current-day rows are counted.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "jobs.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            assert db.conn is not None

            today_job = JobPosting(
                source="test",
                source_url="https://example.com/jobs/today",
                company="TodayCo",
                title="Engineer",
                description="Today posting",
            )
            old_job = JobPosting(
                source="test",
                source_url="https://example.com/jobs/old",
                company="OldCo",
                title="Engineer",
                description="Old posting",
            )
            await db.insert_job(today_job.to_db_dict())
            await db.insert_job(old_job.to_db_dict())
            await db.conn.execute(
                "UPDATE job_postings SET fetched_at = datetime('now', '-3 days') WHERE company = 'OldCo'"
            )
            await db.conn.commit()

            count = await db.get_jobs_today()

    assert count == 1


@pytest.mark.asyncio
async def test_agent_queries_auto_migrate_legacy_schema():
    """Verify agent-query methods self-heal legacy schema before querying.

    Purpose:
        Ensure agent-processing query paths do not fail when called on a
        pre-migration database missing agent columns.
    Args:
        None.
    Output:
        Returns `None`; the test passes when migration runs and query succeeds.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "legacy.db"
        db = DatabaseManager(str(db_path))
        await db.connect()
        assert db.conn is not None

        await db.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS job_postings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_hash TEXT UNIQUE NOT NULL,
                source TEXT NOT NULL,
                source_url TEXT NOT NULL,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                company TEXT NOT NULL,
                company_url TEXT,
                title TEXT NOT NULL,
                location TEXT,
                is_remote BOOLEAN,
                job_type TEXT,
                salary_min INTEGER,
                salary_max INTEGER,
                salary_currency TEXT DEFAULT 'USD',
                salary_source TEXT,
                description TEXT,
                requirements TEXT,
                posted_date TEXT,
                posted_date_parsed TIMESTAMP,
                status TEXT DEFAULT 'NEW',
                raw_data JSON,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        await db.conn.commit()

        pending = await db.get_jobs_pending_agent_processing(limit=10)

        cursor = await db.conn.execute("PRAGMA table_info(job_postings)")
        columns = [row[1] for row in await cursor.fetchall()]
        await db.close()

    assert pending == []
    for required in (
        "agent_processed_at",
        "agent_result",
        "agent_failed_at",
        "agent_error",
        "agent_retry_count",
        "agent_next_retry_at",
        "agent_claim_token",
        "agent_claimed_at",
    ):
        assert required in columns


@pytest.mark.asyncio
async def test_migrate_agent_schema_is_idempotent():
    """Verify running agent migration repeatedly does not fail.

    Purpose:
        Keep startup migrations safe to run on every process launch.
    Args:
        None.
    Output:
        Returns `None`; the test passes when repeated migration preserves index
        presence and does not raise.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            await db.migrate_agent_schema()
            await db.migrate_agent_schema()

            assert db.conn is not None
            cursor = await db.conn.execute("PRAGMA index_list(job_postings)")
            index_names = {row[1] for row in await cursor.fetchall()}

    assert "idx_agent_processed" in index_names
    assert "idx_agent_failed" in index_names
    assert "idx_agent_retry_ready" in index_names
    assert "idx_agent_claimed_at" in index_names
