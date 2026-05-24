"""Cover API resume-download contracts and settings upload resilience.

Purpose:
    Verify tailored-resume downloads resolve artifacts from persisted DB metadata
    and ensure resume TeX migration failures do not rotate backups prematurely.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import main as api_main
from src.database.db_manager import DatabaseManager


async def _seed_tailored_resume_artifact(
    *,
    database_path: Path,
    job_hash: str,
    artifact_pdf_path: Path,
) -> None:
    """Insert one SUCCESS tailor artifact row for a target job hash.

    Purpose:
        Create deterministic database state for resume-download endpoint tests
        without invoking worker pipelines.
    Args:
        database_path: SQLite database path used by the API under test.
        job_hash: Stable job hash associated with the artifact row.
        artifact_pdf_path: Filesystem path to the generated PDF artifact.
    Output:
        Returns `None` after inserting rows and committing.
    """

    manager = DatabaseManager(str(database_path))
    await manager.connect()
    await manager.create_tables()
    await manager.migrate_tailor_schema()

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
            (job_hash, str(artifact_pdf_path)),
        )
        await conn.commit()
    finally:
        await manager.close()


@pytest.fixture
def api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Build a TestClient instance wired to an isolated database path.

    Purpose:
        Keep endpoint contract tests deterministic and side-effect free by using
        a temporary SQLite database and temporary settings file paths.
    Args:
        tmp_path: Pytest temporary directory fixture.
        monkeypatch: Fixture used for environment and module patching.
    Output:
        Returns a configured `TestClient` for `api_main.app`.
    """

    database_path = tmp_path / "jobs.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setattr(
        api_main, "SETTINGS_RESUME_PATH", tmp_path / "resume.tex"
    )
    monkeypatch.setattr(api_main, "SETTINGS_BACKUPS_DIR", tmp_path / "backups")

    return TestClient(api_main.app)


def test_download_tailored_resume_uses_persisted_artifact_path(
    api_client: TestClient,
    tmp_path: Path,
) -> None:
    """Verify download endpoint serves a PDF from DB-persisted artifact path.

    Purpose:
        Protect behavior when the tailor worker writes to a custom output
        directory instead of the legacy default path.
    Args:
        api_client: Isolated FastAPI test client fixture.
        tmp_path: Temporary directory fixture.
    Output:
        Returns `None`; test passes when endpoint returns seeded PDF bytes.
    """

    job_hash = "a" * 32
    artifact_path = tmp_path / "custom-output" / job_hash / "resume_tailored.pdf"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_bytes = b"%PDF-1.4\n%tailored\n"
    artifact_path.write_bytes(artifact_bytes)

    database_path = Path(api_main.resolve_database_path())
    asyncio.run(
        _seed_tailored_resume_artifact(
            database_path=database_path,
            job_hash=job_hash,
            artifact_pdf_path=artifact_path,
        )
    )

    response = api_client.get(f"/api/jobs/{job_hash}/resume")

    assert response.status_code == 200
    assert response.content == artifact_bytes
    assert response.headers["content-type"].startswith("application/pdf")


def test_download_tailored_resume_succeeds_for_any_client(
    api_client: TestClient,
    tmp_path: Path,
) -> None:
    """Verify the download endpoint serves resumes without an access gate.

    Purpose:
        Lock in the post-#61 contract that the endpoint accepts any
        client because the operator already chose port exposure in
        docker-compose. Replaces the prior token/localhost-only test.
    Args:
        api_client: Isolated FastAPI test client fixture.
        tmp_path: Temporary directory fixture.
    Output:
        Returns `None`; test passes when the endpoint returns 200.
    """

    job_hash = "b" * 32
    artifact_path = tmp_path / "any-client" / job_hash / "resume_tailored.pdf"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(b"%PDF-1.4\n%any-client\n")

    database_path = Path(api_main.resolve_database_path())
    asyncio.run(
        _seed_tailored_resume_artifact(
            database_path=database_path,
            job_hash=job_hash,
            artifact_pdf_path=artifact_path,
        )
    )

    response = api_client.get(f"/api/jobs/{job_hash}/resume")
    assert response.status_code == 200


def test_download_tailored_resume_rejects_invalid_hash(api_client: TestClient) -> None:
    """Verify invalid hash values are rejected before file resolution.

    Purpose:
        Guard path-traversal and malformed-input protections on the download
        endpoint boundary.
    Args:
        api_client: Isolated FastAPI test client fixture.
    Output:
        Returns `None`; test passes when endpoint returns HTTP 400.
    """

    response = api_client.get("/api/jobs/not-a-valid-hash/resume")
    assert response.status_code == 400


def test_download_tailored_resume_returns_not_found_when_no_artifact(
    api_client: TestClient,
) -> None:
    """Verify endpoint returns 404 when no successful artifact exists.

    Purpose:
        Ensure callers receive deterministic not-found behavior when a job has
        no persisted successful tailor artifact path.
    Args:
        api_client: Isolated FastAPI test client fixture.
    Output:
        Returns `None`; test passes when endpoint returns HTTP 404.
    """

    response = api_client.get(f"/api/jobs/{'c' * 32}/resume")
    assert response.status_code == 404


def test_upload_resume_tex_endpoint_returns_410_gone(
    api_client: TestClient,
) -> None:
    """The legacy `POST /resume/tex` endpoint is retired (Phase 3).

    Purpose:
        Confirm the structured 410-GONE envelope is emitted so older
        dashboard builds get a clear "moved" signal rather than a
        500 / silent fail.
    """

    response = api_client.post(
        "/api/settings/resume/tex",
        files={
            "file": ("resume.tex", b"\\section{Experience}", "text/plain")
        },
    )

    assert response.status_code == 410
    payload = response.json()
    assert payload["code"] == "ENDPOINT_REMOVED"
    assert payload["new_endpoint"] == "POST /api/settings/resume"


def test_invalid_resume_tex_upload_returns_422_with_validator_errors(
    api_client: TestClient,
) -> None:
    """Phase 3: `POST /resume` rejects non-conforming `.tex` with 422.

    Purpose:
        Pin the new error envelope so the frontend's
        `<ValidatorErrorList>` keeps rendering the right shape.
    """

    response = api_client.post(
        "/api/settings/resume",
        files={
            "file": (
                "resume.tex",
                b"\\documentclass{article}\\begin{document}no sections\\end{document}",
                "text/plain",
            )
        },
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["code"] == "INVALID_RESUME_TEX"
    assert payload["errors"]
    assert payload["errors"][0]["code"] == "CONTRACT_NO_TAILORABLE_SECTION"
