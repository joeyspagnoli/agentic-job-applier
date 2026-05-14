"""Cover the resume-download endpoint's reviewer-verdict resolution.

Purpose:
    Lock the contract added in issue #41 item #3 — the
    `/api/jobs/{hash}/resume` endpoint must serve the reviewer-chosen
    PDF (`review_runs.selected_pdf_path`) for the reviewer-driven BASE
    and PAGE_FIT_FAILED branches, not the always-tailored
    `tailor_runs.artifact_pdf_path` it previously read. The legacy
    fallback to `tailor_runs.artifact_pdf_path` must still work for
    rows with no `review_runs` join.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import main as api_main
from src.database.db_manager import DatabaseManager


_TAILORED_PDF_BYTES = b"%PDF-1.4\n%tailored\n"
_BASE_PDF_BYTES = b"%PDF-1.4\n%base\n"


async def _seed_review_outcome(
    *,
    database_path: Path,
    job_hash: str,
    tailored_pdf_path: Path,
    selected_pdf_path: Path | None,
    review_verdict: str | None,
) -> None:
    """Seed one job + tailor run (+ optional review run) into a test DB.

    Purpose:
        Build the minimum set of rows the resume-download endpoint needs
        to resolve a PDF path for each branch of issue #41 item #3.
        Skipping the `review_runs` insert exercises the legacy fallback
        to `tailor_runs.artifact_pdf_path`.
    Args:
        database_path: SQLite file the API under test will read.
        job_hash: Stable job hash used in the URL path.
        tailored_pdf_path: Absolute path written to `tailor_runs`.
        selected_pdf_path: Absolute path for `review_runs.selected_pdf_path`.
            Pass `None` to skip the `review_runs` insert (legacy path).
        review_verdict: Verdict string for the `review_runs` row.
    Output:
        Returns `None` after committing the seeded rows.
    """

    manager = DatabaseManager(str(database_path))
    await manager.connect()
    await manager.create_tables()
    await manager.migrate_tailor_schema()
    await manager.migrate_review_schema()

    try:
        conn = manager._require_conn()
        await conn.execute(
            """
            INSERT INTO job_postings (
                job_hash, source, source_url, company, title, status
            ) VALUES (?, 'test', 'https://example.com/jobs/1', 'TestCo', 'Engineer', 'QUALIFIED')
            """,
            (job_hash,),
        )
        await conn.execute(
            """
            INSERT INTO tailor_runs (
                job_hash,
                status,
                artifact_pdf_path,
                page_count,
                completed_at
            ) VALUES (?, 'SUCCESS', ?, 1, CURRENT_TIMESTAMP)
            """,
            (job_hash, str(tailored_pdf_path)),
        )

        if selected_pdf_path is not None:
            tailor_run_cursor = await conn.execute(
                "SELECT id FROM tailor_runs WHERE job_hash = ? LIMIT 1",
                (job_hash,),
            )
            tailor_run_row = await tailor_run_cursor.fetchone()
            assert tailor_run_row is not None
            tailor_run_id = int(tailor_run_row["id"])

            await conn.execute(
                """
                INSERT INTO review_runs (
                    job_hash,
                    tailor_run_id,
                    status,
                    verdict,
                    selected_pdf_path,
                    completed_at
                ) VALUES (?, ?, 'SUCCESS', ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    job_hash,
                    tailor_run_id,
                    review_verdict,
                    str(selected_pdf_path),
                ),
            )

        await conn.commit()
    finally:
        await manager.close()


def _write_pdf(parent_dir: Path, job_hash: str, payload: bytes) -> Path:
    """Write a synthetic PDF under `<parent>/<job_hash>/resume_tailored.pdf`.

    Purpose:
        Match the on-disk layout enforced by the endpoint's
        `_is_safe_tailored_resume_path` safety check, which requires the
        file to live in a directory named for the job hash.
    Args:
        parent_dir: Container directory under which the per-job folder
            is created.
        job_hash: Job hash; becomes the folder name.
        payload: Bytes to write to the resume PDF.
    Output:
        Returns the absolute path to the written file.
    """

    target_dir = parent_dir / job_hash
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / "resume_tailored.pdf"
    path.write_bytes(payload)
    return path


@pytest.fixture
def api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Return a `TestClient` wired to an isolated SQLite database.

    Purpose:
        Redirect `resolve_database_path` to a per-test path and clear the
        download token so the endpoint exercises the local-only path.
    """

    database_path = tmp_path / "jobs.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.delenv(api_main.TAILORED_RESUME_TOKEN_ENV_KEY, raising=False)
    return TestClient(api_main.app)


def test_serves_tailored_pdf_when_reviewer_verdict_is_tailored(
    api_client: TestClient, tmp_path: Path
) -> None:
    """Reviewer chose the tailored variant — endpoint returns those bytes."""

    job_hash = "a" * 32
    tailored_pdf = _write_pdf(
        tmp_path / "tailored-out", job_hash, _TAILORED_PDF_BYTES
    )

    asyncio.run(
        _seed_review_outcome(
            database_path=Path(api_main.resolve_database_path()),
            job_hash=job_hash,
            tailored_pdf_path=tailored_pdf,
            selected_pdf_path=tailored_pdf,
            review_verdict="TAILORED",
        )
    )

    response = api_client.get(f"/api/jobs/{job_hash}/resume")

    assert response.status_code == 200
    assert response.content == _TAILORED_PDF_BYTES


def test_serves_base_pdf_when_reviewer_verdict_is_base(
    api_client: TestClient, tmp_path: Path
) -> None:
    """Reviewer chose the base variant — endpoint serves the BASE PDF.

    Purpose:
        Regression target for issue #41 item #3. Before the fix the
        endpoint read `tailor_runs.artifact_pdf_path` and would have
        served the tailored bytes under a "Download base PDF" label.
    """

    job_hash = "b" * 32
    tailored_pdf = _write_pdf(
        tmp_path / "tailored-out", job_hash, _TAILORED_PDF_BYTES
    )
    base_pdf = _write_pdf(tmp_path / "base-out", job_hash, _BASE_PDF_BYTES)

    asyncio.run(
        _seed_review_outcome(
            database_path=Path(api_main.resolve_database_path()),
            job_hash=job_hash,
            tailored_pdf_path=tailored_pdf,
            selected_pdf_path=base_pdf,
            review_verdict="BASE",
        )
    )

    response = api_client.get(f"/api/jobs/{job_hash}/resume")

    assert response.status_code == 200
    assert response.content == _BASE_PDF_BYTES


def test_serves_base_pdf_when_reviewer_verdict_is_page_fit_failed(
    api_client: TestClient, tmp_path: Path
) -> None:
    """PAGE_FIT_FAILED forces fallback to the base PDF — regression target."""

    job_hash = "c" * 32
    tailored_pdf = _write_pdf(
        tmp_path / "tailored-out", job_hash, _TAILORED_PDF_BYTES
    )
    base_pdf = _write_pdf(tmp_path / "base-out", job_hash, _BASE_PDF_BYTES)

    asyncio.run(
        _seed_review_outcome(
            database_path=Path(api_main.resolve_database_path()),
            job_hash=job_hash,
            tailored_pdf_path=tailored_pdf,
            selected_pdf_path=base_pdf,
            review_verdict="PAGE_FIT_FAILED",
        )
    )

    response = api_client.get(f"/api/jobs/{job_hash}/resume")

    assert response.status_code == 200
    assert response.content == _BASE_PDF_BYTES


def test_falls_back_to_tailor_run_when_no_review_run_exists(
    api_client: TestClient, tmp_path: Path
) -> None:
    """Legacy rows with no `review_runs` join still resolve via tailor_runs.

    Purpose:
        Guard backward compatibility — pre-reviewer DBs (or rows whose
        review_runs row is absent) must still serve a PDF through the
        `tailor_runs.artifact_pdf_path` fallback in the COALESCE.
    """

    job_hash = "d" * 32
    tailored_pdf = _write_pdf(
        tmp_path / "tailored-out", job_hash, _TAILORED_PDF_BYTES
    )

    asyncio.run(
        _seed_review_outcome(
            database_path=Path(api_main.resolve_database_path()),
            job_hash=job_hash,
            tailored_pdf_path=tailored_pdf,
            selected_pdf_path=None,
            review_verdict=None,
        )
    )

    response = api_client.get(f"/api/jobs/{job_hash}/resume")

    assert response.status_code == 200
    assert response.content == _TAILORED_PDF_BYTES
