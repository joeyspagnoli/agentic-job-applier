"""Tests for `insert_pipeline_review_run` — the claim-tokenless write path.

Purpose:
    The resume-tailor pipeline runs tailor and review in one process, so it
    bypasses the per-stage claim-token dance and writes the SUCCESS row
    directly. These tests cover row shape and CHECK-constraint enforcement.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import cast

import pytest
import pytest_asyncio

from src.database.db_manager import DatabaseManager


@pytest_asyncio.fixture
async def db(tmp_path: Path) -> AsyncGenerator[DatabaseManager, None]:
    """Provide a DB with both tailor and review schemas migrated."""

    manager = DatabaseManager(str(tmp_path / "review.db"))
    await manager.connect()
    await manager.create_tables()
    yield manager
    await manager.close()


async def _seed_tailor_run(db: DatabaseManager, job_hash: str) -> int:
    """Create one tailor_runs row and return its id."""

    inserted = await db.insert_user_triggered_tailor_run(job_hash=job_hash)
    assert inserted is not None
    return cast(int, inserted["id"])


@pytest.mark.parametrize(
    "verdict",
    ["PASS", "TAILORED", "BASE", "FAIL", "NO_IMPROVEMENT", "PAGE_FIT_FAILED"],
)
@pytest.mark.asyncio
async def test_insert_accepts_every_allowed_verdict(
    db: DatabaseManager,
    verdict: str,
) -> None:
    """Each allowed verdict round-trips into a SUCCESS review_runs row."""

    tailor_run_id = await _seed_tailor_run(db, job_hash="a" * 40)

    review_run_id = await db.insert_pipeline_review_run(
        job_hash="a" * 40,
        tailor_run_id=tailor_run_id,
        verdict=verdict,
        selected_yaml_path="/tmp/sel.yaml",
        selected_tex_path="/tmp/sel.tex",
        selected_pdf_path="/tmp/sel.pdf",
        review_report_json='{"verdict":"' + verdict + '"}',
        fallback_base_yaml_path="/tmp/base.yaml",
        fallback_base_tex_path="/tmp/base.tex",
        fallback_base_pdf_path="/tmp/base.pdf",
    )

    assert review_run_id > 0
    runs = await db.get_review_runs_for_tailor_run(tailor_run_id)
    assert len(runs) == 1
    assert runs[0]["verdict"] == verdict
    assert runs[0]["status"] == "SUCCESS"


@pytest.mark.asyncio
async def test_insert_rejects_unknown_verdict_via_check_constraint(
    db: DatabaseManager,
) -> None:
    """Unsupported verdict strings trigger SQLite's CHECK at insert time."""

    tailor_run_id = await _seed_tailor_run(db, job_hash="b" * 40)

    with pytest.raises(Exception, match="CHECK"):
        await db.insert_pipeline_review_run(
            job_hash="b" * 40,
            tailor_run_id=tailor_run_id,
            verdict="DEFINITELY_BOGUS",
            selected_yaml_path=None,
            selected_tex_path=None,
            selected_pdf_path=None,
            review_report_json=None,
            fallback_base_yaml_path=None,
            fallback_base_tex_path=None,
            fallback_base_pdf_path=None,
        )


@pytest.mark.asyncio
async def test_insert_persists_full_payload(db: DatabaseManager) -> None:
    """All provided fields are read back unchanged on the SUCCESS row."""

    tailor_run_id = await _seed_tailor_run(db, job_hash="c" * 40)

    review_run_id = await db.insert_pipeline_review_run(
        job_hash="c" * 40,
        tailor_run_id=tailor_run_id,
        verdict="TAILORED",
        selected_yaml_path="/var/x.yaml",
        selected_tex_path="/var/x.tex",
        selected_pdf_path="/var/x.pdf",
        review_report_json='{"k":"v"}',
        fallback_base_yaml_path="/var/base.yaml",
        fallback_base_tex_path="/var/base.tex",
        fallback_base_pdf_path="/var/base.pdf",
    )

    rows = await db.get_review_runs_for_tailor_run(tailor_run_id)
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == review_run_id
    assert row["tailor_run_id"] == tailor_run_id
    assert row["selected_yaml_path"] == "/var/x.yaml"
    assert row["selected_tex_path"] == "/var/x.tex"
    assert row["selected_pdf_path"] == "/var/x.pdf"
    assert row["review_report_json"] == '{"k":"v"}'
    assert row["fallback_base_yaml_path"] == "/var/base.yaml"
