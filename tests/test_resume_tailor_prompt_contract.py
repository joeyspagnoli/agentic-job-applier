"""Validate resume-tailor prompt command and policy contracts.

Purpose:
    Ensure prompt text preserves required tool commands, DB path forwarding,
    and direct-edit fallback guidance for robust autonomous runs.
"""

from __future__ import annotations

from pathlib import Path

from src.agents.resume_tailor_pi.prompts import build_tailor_instruction
from src.agents.resume_tailor_pi.schemas import TailorInvocationContract


def test_tailor_prompt_includes_database_path_and_recovery_commands(
    tmp_path: Path,
) -> None:
    """Verify prompt text exposes DB path forwarding and rollback commands.

    Purpose:
        Protect prompt-level contracts so agent command examples remain aligned
        with runtime invocation fields and available CLI tools.
    Args:
        tmp_path: Pytest temporary directory fixture.
    Output:
        Returns `None`; test passes when required command fragments are present.
    """

    database_path = tmp_path / "jobs db.sqlite3"
    invocation = TailorInvocationContract.model_validate(
        {
            "job_ref": {"job_hash": "hash123"},
            "database_path": str(database_path),
            "resume_yaml_path": str(tmp_path / "resume_content.yaml"),
            "output_tex_path": str(tmp_path / "resume.tex"),
            "output_pdf_path": str(tmp_path / "resume.pdf"),
            "create_git_branch": False,
        }
    )

    instruction_text = build_tailor_instruction(
        invocation=invocation,
        phase="content",
        attempt_index=0,
        current_page_count=None,
    )

    expected_snapshot_path = (
        Path(invocation.output_tex_path).resolve().parent
        / "resume_tailor.snapshot.yaml"
    )

    assert "db-get-job-context --database-path" in instruction_text
    assert str(database_path) in instruction_text
    assert "backup-resume-yaml" in instruction_text
    assert "restore-resume-yaml" in instruction_text
    assert str(expected_snapshot_path) in instruction_text
    assert "Tool usage examples:" in instruction_text
    assert "If `save-resume-yaml` is flaky" in instruction_text
