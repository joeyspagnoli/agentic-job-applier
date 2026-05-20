"""Cover the resume-download endpoint's reviewer-verdict resolution.

Purpose:
    Lock the contract added in issue #41 item #3 — the
    `/api/jobs/{hash}/resume` endpoint must serve the reviewer-chosen
    PDF (`review_runs.selected_pdf_path`) for the reviewer-driven BASE
    and PAGE_FIT_FAILED branches, not the always-tailored
    `tailor_runs.artifact_pdf_path` it previously read. The legacy
    fallback to `tailor_runs.artifact_pdf_path` must still work for
    rows with no `review_runs` join.

    Issue #52 extends this contract: the on-disk layout the tailor
    pipeline actually emits is `<hash>/<variant>/<variant>.pdf`, not the
    flat `<hash>/resume_tailored.pdf` shape the pre-fix validator
    expected. The variant-subdir tests here lock the corrected
    `_is_safe_tailored_resume_path` validator (commit 38a89b1) against
    every reviewer verdict, while the legacy flat-layout tests near the
    top of the file keep the backwards-compat branch covered.
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
        Match the legacy flat layout the pre-variant tailor pipeline used
        (and the validator's original expectation). Kept so the
        backwards-compat branch in `_is_safe_tailored_resume_path` stays
        covered for any historical rows that still point at
        `resume_tailored.pdf`.
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


def _write_variant_pdf(
    parent_dir: Path, job_hash: str, variant: str, payload: bytes
) -> Path:
    """Write a synthetic PDF in the real per-variant pipeline layout.

    Purpose:
        Match the on-disk layout the resume-tailor pipeline actually
        emits — `<parent>/<hash>/<variant>/<variant>.pdf` — rather than
        the legacy flat shape `_write_pdf` produces. The bug surfaced in
        issue #52 (every successful tailor run returned HTTP 500
        `INVALID_ARTIFACT_PATH`) slipped through because the previous
        tests only exercised the legacy flat layout; tests using this
        helper turn red without the validator fix in commit 38a89b1.
    Args:
        parent_dir: Container directory under which the per-job folder
            is created.
        job_hash: Job hash; becomes the first-level folder name.
        variant: Variant name (`base`, `tailored_v1`, or `tailored_v2`);
            becomes both the second-level folder name and the filename
            stem to match the validator's `name == f"{variant}.pdf"`
            conjunct.
        payload: Bytes to write to the variant PDF.
    Output:
        Returns the absolute path to the written file.
    """

    target_dir = parent_dir / job_hash / variant
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{variant}.pdf"
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


def test_serves_tailored_v1_pdf_with_variant_subdir_layout(
    api_client: TestClient, tmp_path: Path
) -> None:
    """Reviewer chose tailored_v1; endpoint serves the per-variant artifact.

    Purpose:
        Lock the validator branch that accepts the current pipeline
        layout `<hash>/tailored_v1/tailored_v1.pdf` when the reviewer
        verdict is TAILORED. Before commit 38a89b1 the validator
        required a flat `<hash>/resume_tailored.pdf`, so this case
        returned HTTP 500 in production despite being the pipeline's
        most common success path.
    """

    job_hash = "e" * 32
    tailored_pdf = _write_variant_pdf(
        tmp_path / "tailored-out",
        job_hash,
        "tailored_v1",
        _TAILORED_PDF_BYTES,
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


def test_serves_tailored_v2_pdf_with_variant_subdir_layout(
    api_client: TestClient, tmp_path: Path
) -> None:
    """Reviewer chose tailored_v2; endpoint serves the per-variant artifact.

    Purpose:
        This is the exact bug reported in issue #52 — when the reviewer
        retry loop produces a `tailored_v2.pdf`, the validator must
        accept `<hash>/tailored_v2/tailored_v2.pdf`. The test stays red
        without the validator fix; together with the v1 case it locks
        both reviewer-tailored variants against the variant whitelist.
    """

    job_hash = "f" * 32
    tailored_pdf = _write_variant_pdf(
        tmp_path / "tailored-out",
        job_hash,
        "tailored_v2",
        _TAILORED_PDF_BYTES,
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


def test_serves_base_pdf_when_verdict_base_with_variant_subdir_layout(
    api_client: TestClient, tmp_path: Path
) -> None:
    """BASE verdict serves `<hash>/base/base.pdf` under the variant layout.

    Purpose:
        Pair the issue #41 reviewer-verdict contract with the issue #52
        on-disk shape: when the reviewer picks the BASE variant the
        endpoint must serve the per-variant base PDF the pipeline wrote,
        not a synthesized flat-layout path.
    """

    job_hash = "1" * 32
    tailored_pdf = _write_variant_pdf(
        tmp_path / "tailored-out",
        job_hash,
        "tailored_v1",
        _TAILORED_PDF_BYTES,
    )
    base_pdf = _write_variant_pdf(
        tmp_path / "tailored-out", job_hash, "base", _BASE_PDF_BYTES
    )

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


def test_serves_base_pdf_when_verdict_page_fit_failed_with_variant_subdir_layout(
    api_client: TestClient, tmp_path: Path
) -> None:
    """PAGE_FIT_FAILED forces base PDF resolution under the variant layout.

    Purpose:
        PAGE_FIT_FAILED is the safety-net verdict — the reviewer rejected
        every tailored candidate because none fit on a single page, and
        the pipeline falls back to base. This test locks that fallback
        against the per-variant on-disk layout so a future regression
        cannot drop PAGE_FIT_FAILED from the verdicts that resolve to
        `<hash>/base/base.pdf`.
    """

    job_hash = "2" * 32
    tailored_pdf = _write_variant_pdf(
        tmp_path / "tailored-out",
        job_hash,
        "tailored_v1",
        _TAILORED_PDF_BYTES,
    )
    base_pdf = _write_variant_pdf(
        tmp_path / "tailored-out", job_hash, "base", _BASE_PDF_BYTES
    )

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


def test_serves_base_pdf_when_verdict_no_improvement_with_variant_subdir_layout(
    api_client: TestClient, tmp_path: Path
) -> None:
    """NO_IMPROVEMENT verdict resolves to `<hash>/base/base.pdf` cleanly.

    Purpose:
        Round out the verdict matrix for the per-variant layout —
        NO_IMPROVEMENT (the reviewer judged tailoring didn't help) must
        also resolve to the base PDF the pipeline wrote. Together with
        the BASE and PAGE_FIT_FAILED cases this proves every reviewer
        branch that selects `base.pdf` is covered by the real pipeline
        layout, not just the legacy `resume_tailored.pdf` shape.
    """

    job_hash = "3" * 32
    tailored_pdf = _write_variant_pdf(
        tmp_path / "tailored-out",
        job_hash,
        "tailored_v1",
        _TAILORED_PDF_BYTES,
    )
    base_pdf = _write_variant_pdf(
        tmp_path / "tailored-out", job_hash, "base", _BASE_PDF_BYTES
    )

    asyncio.run(
        _seed_review_outcome(
            database_path=Path(api_main.resolve_database_path()),
            job_hash=job_hash,
            tailored_pdf_path=tailored_pdf,
            selected_pdf_path=base_pdf,
            review_verdict="NO_IMPROVEMENT",
        )
    )

    response = api_client.get(f"/api/jobs/{job_hash}/resume")

    assert response.status_code == 200
    assert response.content == _BASE_PDF_BYTES


@pytest.mark.parametrize(
    ("invalid_subdir", "invalid_filename", "job_hash_seed"),
    [
        ("sneaky", "sneaky.pdf", "4" * 32),
        ("something_else", "whatever.pdf", "5" * 32),
    ],
)
def test_rejects_path_with_unknown_variant_subdir(
    api_client: TestClient,
    tmp_path: Path,
    invalid_subdir: str,
    invalid_filename: str,
    job_hash_seed: str,
) -> None:
    """Validator rejects PDFs in subdirs outside the variant whitelist.

    Purpose:
        Lock the closed `_VARIANT_SUBDIR_NAMES` whitelist — a future
        refactor that loosens the second-level directory check (for
        example, dropping the whitelist in favor of any non-empty
        string) must turn this test red. Without the whitelist the
        endpoint would happily serve any `<hash>/<anything>/*.pdf`
        attacker-controlled path that the upstream layers let through.
    """

    invalid_dir = tmp_path / "tailored-out" / job_hash_seed / invalid_subdir
    invalid_dir.mkdir(parents=True, exist_ok=True)
    invalid_pdf_path = invalid_dir / invalid_filename
    invalid_pdf_path.write_bytes(_TAILORED_PDF_BYTES)

    asyncio.run(
        _seed_review_outcome(
            database_path=Path(api_main.resolve_database_path()),
            job_hash=job_hash_seed,
            tailored_pdf_path=invalid_pdf_path,
            selected_pdf_path=invalid_pdf_path,
            review_verdict="TAILORED",
        )
    )

    response = api_client.get(f"/api/jobs/{job_hash_seed}/resume")

    assert response.status_code == 500
    assert response.json()["code"] == "INVALID_ARTIFACT_PATH"


def test_rejects_variant_subdir_pdf_when_filename_does_not_match_variant(
    api_client: TestClient, tmp_path: Path
) -> None:
    """`<hash>/base/tailored_v1.pdf` is rejected — filename must match subdir.

    Purpose:
        Lock the `candidate_path.name == f"{parent_name}.pdf"` conjunct
        in the validator. The subdir is on the whitelist and the
        grandparent is the job hash, so the only thing keeping this path
        from validating is the filename/variant pairing check. A
        regression that relaxes the filename rule (for example, accepting
        any `.pdf` inside a known variant directory) would turn this red.
    """

    job_hash = "6" * 32
    variant_dir = tmp_path / "tailored-out" / job_hash / "base"
    variant_dir.mkdir(parents=True, exist_ok=True)
    # Filename stem is `tailored_v1`, but the enclosing variant directory
    # is `base` — the validator must reject this mismatched pairing even
    # though every other structural check (whitelist, grandparent hash,
    # PDF suffix, file exists) passes.
    mismatched_pdf_path = variant_dir / "tailored_v1.pdf"
    mismatched_pdf_path.write_bytes(_TAILORED_PDF_BYTES)

    asyncio.run(
        _seed_review_outcome(
            database_path=Path(api_main.resolve_database_path()),
            job_hash=job_hash,
            tailored_pdf_path=mismatched_pdf_path,
            selected_pdf_path=mismatched_pdf_path,
            review_verdict="TAILORED",
        )
    )

    response = api_client.get(f"/api/jobs/{job_hash}/resume")

    assert response.status_code == 500
    assert response.json()["code"] == "INVALID_ARTIFACT_PATH"
