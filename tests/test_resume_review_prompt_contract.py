"""Validate resume-review prompt tool and completion contracts.

Purpose:
    Ensure review prompt text includes required tool sequence and explicit
    `write-review-report` example usage for deterministic completion.
"""

from __future__ import annotations

from pathlib import Path

from src.agents.resume_review_pi.prompts import build_review_instruction
from src.agents.resume_review_pi.schemas import ReviewInvocationContract


def test_review_prompt_includes_tool_sequence_and_report_example(
    tmp_path: Path,
) -> None:
    """Verify prompt includes review tools and report write example command.

    Purpose:
        Protect prompt contracts so agent instructions always expose analysis
        tools, edit loop behavior, and strict report completion semantics.
    Args:
        tmp_path: Pytest temporary directory fixture.
    Output:
        Returns `None`; test passes when required prompt fragments exist.
    """

    invocation = ReviewInvocationContract.model_validate(
        {
            "job_ref": {"job_hash": "abc123hash"},
            "tailor_run_id": 42,
            "database_path": str(tmp_path / "jobs.db"),
            "tailored_yaml_path": str(tmp_path / "resume_content_work.yaml"),
            "tailored_tex_path": str(tmp_path / "resume_tailored.tex"),
            "tailored_pdf_path": str(tmp_path / "resume_tailored.pdf"),
            "tailored_log_path": str(tmp_path / "resume_tailored.log"),
            "base_yaml_path": str(tmp_path / "resume_base.yaml"),
            "base_tex_path": str(tmp_path / "resume_base.tex"),
            "base_pdf_path": str(tmp_path / "resume_base.pdf"),
            "review_report_path": str(tmp_path / "review_report.json"),
            "max_review_iterations": 2,
        }
    )

    instruction_text = build_review_instruction(invocation=invocation)
    snapshot_path = (
        Path(invocation.tailored_yaml_path).resolve().parent
        / "resume_review.snapshot.yaml"
    )

    assert "db-get-job-context --database-path" in instruction_text
    assert "load-resume-yaml" in instruction_text
    assert "save-resume-yaml" in instruction_text
    assert "backup-resume-yaml" in instruction_text
    assert "restore-resume-yaml" in instruction_text
    assert "analyze-pdf-geometry" in instruction_text
    assert "compare-pdf-to-base" in instruction_text
    assert "analyze-latex-log" in instruction_text
    assert "extract-pdf-text-signals" in instruction_text
    assert "write-review-report" in instruction_text
    assert "--report-json" in instruction_text
    assert "Tool usage examples:" in instruction_text
    assert str(snapshot_path) in instruction_text
