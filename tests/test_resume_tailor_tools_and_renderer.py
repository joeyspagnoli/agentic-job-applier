"""Validate resume-tailor schema, renderer, and tool helper behavior.

Purpose:
    Cover lock enforcement, listing enable/disable rendering, and page-count
    fallback parsing for the YAML-canonical resume-tailor subsystem.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

from src.agents.resume_tailor_pi.compiler import get_pdf_page_count
from src.agents.resume_tailor_pi.renderer import render_resume_yaml_to_tex
from src.agents.resume_tailor_pi.schemas import build_locked_section_snapshot
from src.agents.resume_tailor_pi.schemas import ensure_locked_sections_unchanged
from src.agents.resume_tailor_pi.tools import db_get_job_context
from src.agents.resume_tailor_pi.yaml_io import load_resume_yaml
from src.agents.resume_tailor_pi.yaml_io import save_resume_yaml
from src.database.db_manager import DatabaseManager
from src.models.job_posting import JobPosting


@pytest.mark.asyncio
async def test_db_get_job_context_supports_hash_and_id_selectors() -> None:
    """Verify tool context lookup works for both hash and numeric ID paths.

    Purpose:
        Ensure the tailored agent can retrieve job context directly from SQLite
        regardless of selector type in invocation contracts.
    Args:
        None.
    Output:
        Returns `None`; test passes when both lookup paths resolve one row.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "jobs.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            await db.migrate_agent_schema()
            inserted_job = JobPosting(
                source="test",
                source_url="https://example.com/jobs/resume",
                company="ResumeCo",
                title="Applied AI Intern",
                description="Build agentic systems",
            )
            await db.insert_job(inserted_job.to_db_dict())
            stored_row = await db.get_job_by_hash(inserted_job.job_hash)

        assert stored_row is not None
        stored_row_id = stored_row["id"]
        assert isinstance(stored_row_id, int)

        by_hash = await db_get_job_context(
            database_path=db_path,
            job_hash=inserted_job.job_hash,
        )
        by_id = await db_get_job_context(
            database_path=db_path,
            job_id=stored_row_id,
        )

    assert by_hash["job_hash"] == inserted_job.job_hash
    assert by_id["id"] == stored_row["id"]


def test_renderer_skips_disabled_listings(tmp_path: Path) -> None:
    """Verify disabled listings are excluded from rendered LaTeX output.

    Purpose:
        Protect active/inactive listing pool behavior so toggled-off entries do
        not appear in generated TeX artifacts.
    Args:
        tmp_path: Pytest temporary directory fixture.
    Output:
        Returns `None`; test passes when disabled title is absent from output.
    """

    source_yaml_path = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "resume_content_populated.yaml"
    )
    working_yaml_path = tmp_path / "resume_content.yaml"
    working_tex_path = tmp_path / "resume.tex"

    resume_content = load_resume_yaml(source_yaml_path)
    assert resume_content.experience.listings

    hidden_listing_title = resume_content.experience.listings[0].title
    resume_content.experience.listings[0].enabled = False
    save_resume_yaml(path=working_yaml_path, resume_content=resume_content)

    rendered_tex_path = render_resume_yaml_to_tex(
        yaml_path=working_yaml_path,
        tex_output_path=working_tex_path,
    )
    with open(rendered_tex_path, "r", encoding="utf-8") as tex_file:
        rendered_text = tex_file.read()

    assert hidden_listing_title not in rendered_text


def test_locked_section_snapshot_rejects_education_mutation(tmp_path: Path) -> None:
    """Verify lock snapshot checks reject education-section mutations.

    Purpose:
        Ensure immutable section policy remains enforced even when YAML files are
        modified between passes.
    Args:
        tmp_path: Pytest temporary directory fixture.
    Output:
        Returns `None`; test passes when lock check raises ValueError.
    """

    source_yaml_path = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "resume_content_populated.yaml"
    )
    working_yaml_path = tmp_path / "resume_content.yaml"

    baseline_resume = load_resume_yaml(source_yaml_path)
    locked_snapshot = build_locked_section_snapshot(baseline_resume)

    mutated_resume = baseline_resume.model_copy(deep=True)
    mutated_resume.education.entries[0].degree = "Tampered degree line"
    save_resume_yaml(path=working_yaml_path, resume_content=mutated_resume)

    reloaded_resume = load_resume_yaml(working_yaml_path)
    with pytest.raises(ValueError):
        ensure_locked_sections_unchanged(
            reloaded_resume,
            locked_snapshot=locked_snapshot,
        )


def test_page_count_falls_back_to_latex_log(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify page-count helper falls back to LaTeX log parsing.

    Purpose:
        Protect one-page enforcement when `pdfinfo` is unavailable or cannot
        parse output in a given runtime environment.
    Args:
        monkeypatch: Pytest fixture used to patch subprocess invocation.
        tmp_path: Pytest temporary directory fixture.
    Output:
        Returns `None`; test passes when fallback log parsing returns pages.
    """

    pdf_path = tmp_path / "resume.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    log_path = tmp_path / "resume.log"
    log_path.write_text(
        "Output written on resume.pdf (2 pages, 102400 bytes).",
        encoding="utf-8",
    )

    def fake_run(*_: Any, **__: Any) -> Any:
        """Return empty pdfinfo output to force log fallback path.

        Purpose:
            Simulate an environment where pdfinfo output does not provide the
            expected page count line.
        Args:
            *_: Ignored positional arguments.
            **__: Ignored keyword arguments.
        Output:
            Returns an object with empty stdout and zero return code.
        """

        class _Result:
            """Store subprocess-like return payload for tests."""

            returncode = 0
            stdout = ""

        return _Result()

    monkeypatch.setattr("subprocess.run", fake_run)
    parsed_page_count = get_pdf_page_count(pdf_path=pdf_path, log_path=log_path)
    assert parsed_page_count == 2
