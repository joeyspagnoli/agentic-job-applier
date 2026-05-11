"""Validate resume-tailor prompt command and policy contracts.

Purpose:
    Ensure prompt text preserves required tool commands, DB path forwarding,
    and direct-edit fallback guidance for robust autonomous runs.
"""

from __future__ import annotations

from pathlib import Path

from src.agents.resume_tailor_pi.prompts import build_tailor_instruction
from src.agents.resume_tailor_adk.schemas import TailorInvocationContract


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


def _make_minimal_invocation(tmp_path: Path) -> TailorInvocationContract:
    """Create a minimal TailorInvocationContract for prompt-contract tests."""

    return TailorInvocationContract.model_validate(
        {
            "job_ref": {"job_hash": "abc123"},
            "database_path": str(tmp_path / "jobs.sqlite3"),
            "resume_yaml_path": str(tmp_path / "resume_content.yaml"),
            "output_tex_path": str(tmp_path / "resume.tex"),
            "output_pdf_path": str(tmp_path / "resume.pdf"),
            "create_git_branch": False,
        }
    )


def test_tailor_prompt_includes_candidate_context_when_both_provided(
    tmp_path: Path,
) -> None:
    """Candidate context block appears when both fields are non-empty.

    Purpose:
        Verify that experience_highlights and strongest_areas both render
        in the prompt when supplied, so the tailor agent can use them.
    Args:
        tmp_path: Pytest temporary directory fixture.
    Output:
        Returns `None`; asserts that all three context markers appear.
    """

    invocation = _make_minimal_invocation(tmp_path)

    # Act
    instruction_text = build_tailor_instruction(
        invocation=invocation,
        phase="content",
        attempt_index=0,
        current_page_count=None,
        experience_highlights=["Led K8s migration cutting cold-start 8s→800ms"],
        strongest_areas=["Python", "Kubernetes"],
    )

    # Assert
    assert "Candidate context:" in instruction_text
    assert "Strongest areas: Python, Kubernetes" in instruction_text
    assert "Experience highlights:" in instruction_text
    assert "Led K8s migration cutting cold-start 8s→800ms" in instruction_text


def test_tailor_prompt_omits_candidate_context_when_both_none(
    tmp_path: Path,
) -> None:
    """Candidate context block is absent when both fields are None.

    Purpose:
        Ensure the prompt is identical to today's behavior when no profile
        context is provided — no regression for callers that omit the params.
    Args:
        tmp_path: Pytest temporary directory fixture.
    Output:
        Returns `None`; asserts that the context header is absent.
    """

    invocation = _make_minimal_invocation(tmp_path)

    # Act
    instruction_text = build_tailor_instruction(
        invocation=invocation,
        phase="content",
        attempt_index=0,
        current_page_count=None,
        experience_highlights=None,
        strongest_areas=None,
    )

    # Assert
    assert "Candidate context:" not in instruction_text


def test_tailor_prompt_includes_highlights_only_when_areas_none(
    tmp_path: Path,
) -> None:
    """Experience highlights render without a Strongest areas line.

    Purpose:
        Confirm the context block handles partial population: when only
        experience_highlights is provided, the areas line is omitted.
    Args:
        tmp_path: Pytest temporary directory fixture.
    Output:
        Returns `None`; asserts highlights present and areas absent.
    """

    invocation = _make_minimal_invocation(tmp_path)

    # Act
    instruction_text = build_tailor_instruction(
        invocation=invocation,
        phase="content",
        attempt_index=0,
        current_page_count=None,
        experience_highlights=["React dashboard used by 200+ analysts"],
        strongest_areas=None,
    )

    # Assert
    assert "Candidate context:" in instruction_text
    assert "Experience highlights:" in instruction_text
    assert "React dashboard used by 200+ analysts" in instruction_text
    assert "Strongest areas:" not in instruction_text


def test_tailor_prompt_includes_areas_only_when_highlights_none(
    tmp_path: Path,
) -> None:
    """Strongest areas render without an Experience highlights block.

    Purpose:
        Confirm the context block handles partial population: when only
        strongest_areas is provided, the highlights section is omitted.
    Args:
        tmp_path: Pytest temporary directory fixture.
    Output:
        Returns `None`; asserts areas present and highlights absent.
    """

    invocation = _make_minimal_invocation(tmp_path)

    # Act
    instruction_text = build_tailor_instruction(
        invocation=invocation,
        phase="content",
        attempt_index=0,
        current_page_count=None,
        experience_highlights=None,
        strongest_areas=["Go", "distributed systems"],
    )

    # Assert
    assert "Candidate context:" in instruction_text
    assert "Strongest areas: Go, distributed systems" in instruction_text
    assert "Experience highlights:" not in instruction_text
