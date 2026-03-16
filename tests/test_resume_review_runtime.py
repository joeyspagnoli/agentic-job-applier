"""Validate hard-error boundaries for pi-mono review runtime.

Purpose:
    Ensure runtime accepts agent-authored verdicts and only fails on strict
    operational errors such as command failure, missing report, or bad refs.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.agents.resume_review_pi import runtime as runtime_module
from src.agents.resume_review_pi.schemas import ReviewInvocationContract
from src.agents.resume_review_pi.schemas import ReviewReport
from src.agents.resume_review_pi.schemas import ReviewVerdict


def _build_invocation(tmp_path: Path) -> ReviewInvocationContract:
    """Build a deterministic review invocation for runtime unit tests.

    Purpose:
        Keep runtime test setup concise while reusing one valid invocation
        payload across success and failure scenarios.
    Args:
        tmp_path: Pytest temporary directory fixture.
    Output:
        Returns validated `ReviewInvocationContract` instance.
    """

    tailored_yaml_path = tmp_path / "resume_content_work.yaml"
    tailored_tex_path = tmp_path / "resume_tailored.tex"
    tailored_pdf_path = tmp_path / "resume_tailored.pdf"
    tailored_log_path = tmp_path / "resume_tailored.log"
    base_yaml_path = tmp_path / "resume_base.yaml"
    base_tex_path = tmp_path / "resume_base.tex"
    base_pdf_path = tmp_path / "resume_base.pdf"

    for path in (
        tailored_yaml_path,
        tailored_tex_path,
        tailored_pdf_path,
        tailored_log_path,
        base_yaml_path,
        base_tex_path,
        base_pdf_path,
    ):
        path.write_text("stub", encoding="utf-8")

    return ReviewInvocationContract.model_validate(
        {
            "job_ref": {"job_hash": "a" * 32},
            "tailor_run_id": 7,
            "database_path": str(tmp_path / "jobs.db"),
            "tailored_yaml_path": str(tailored_yaml_path),
            "tailored_tex_path": str(tailored_tex_path),
            "tailored_pdf_path": str(tailored_pdf_path),
            "tailored_log_path": str(tailored_log_path),
            "base_yaml_path": str(base_yaml_path),
            "base_tex_path": str(base_tex_path),
            "base_pdf_path": str(base_pdf_path),
            "review_report_path": str(tmp_path / "review_report.json"),
            "pi_coding_agent_command": "echo simulated",
            "max_review_iterations": 2,
        }
    )


def test_runtime_accepts_pass_verdict(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Verify runtime returns success for valid PASS report payload.

    Purpose:
        Ensure runtime treats agent-authored PASS verdict as completed review
        when report schema and selected references are valid.
    Args:
        monkeypatch: Pytest monkeypatch fixture.
        tmp_path: Pytest temporary directory fixture.
    Output:
        Returns `None`; test passes when runtime result is successful.
    """

    invocation = _build_invocation(tmp_path)

    def fake_invoke(**_: object) -> subprocess.CompletedProcess[str]:
        """Return deterministic successful subprocess payload.

        Purpose:
            Remove external pi dependency from runtime unit tests.
        Args:
            **_: Ignored keyword args from runtime invocation.
        Output:
            Returns subprocess-like completed process object.
        """

        return subprocess.CompletedProcess(
            args=["pi"],
            returncode=0,
            stdout="agent ok",
            stderr="",
        )

    def fake_report(*, report_path: Path) -> ReviewReport:
        """Return a valid PASS report with selected tailored paths.

        Purpose:
            Stub report loading so runtime success-path assertions can run
            without writing report files on disk.
        Args:
            report_path: Resolved report path requested by runtime.
        Output:
            Returns validated PASS review report.
        """

        _ = report_path
        return ReviewReport(
            verdict=ReviewVerdict.PASS,
            summary="Tailored output accepted",
            iteration_count=1,
            selected_yaml_path=invocation.tailored_yaml_path,
            selected_tex_path=invocation.tailored_tex_path,
            selected_pdf_path=invocation.tailored_pdf_path,
        )

    monkeypatch.setattr(runtime_module, "_invoke_pi_coding_agent", fake_invoke)
    monkeypatch.setattr(runtime_module, "_load_review_report", fake_report)

    result = runtime_module.run_resume_review_pipeline(invocation=invocation)

    assert result.success is True
    assert result.hard_failure is False
    assert result.verdict == ReviewVerdict.PASS
    assert result.selected_pdf_path == invocation.tailored_pdf_path


def test_runtime_accepts_fail_verdict(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Verify runtime accepts FAIL verdict when report schema is valid.

    Purpose:
        Ensure runtime does not impose subjective quality policy and allows
        agent-authored FAIL decisions as successful review completion.
    Args:
        monkeypatch: Pytest monkeypatch fixture.
        tmp_path: Pytest temporary directory fixture.
    Output:
        Returns `None`; test passes when FAIL verdict is accepted.
    """

    invocation = _build_invocation(tmp_path)

    monkeypatch.setattr(
        runtime_module,
        "_invoke_pi_coding_agent",
        lambda **_: subprocess.CompletedProcess(
            args=["pi"], returncode=0, stdout="agent ok", stderr=""
        ),
    )
    monkeypatch.setattr(
        runtime_module,
        "_load_review_report",
        lambda report_path: ReviewReport(
            verdict=ReviewVerdict.FAIL,
            summary="Tailored and base both unsuitable",
            iteration_count=2,
        ),
    )

    result = runtime_module.run_resume_review_pipeline(invocation=invocation)

    assert result.success is True
    assert result.verdict == ReviewVerdict.FAIL


def test_runtime_fails_on_pi_command_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Verify runtime returns hard failure when pi invocation fails.

    Purpose:
        Protect hard runtime boundary for non-zero exit, timeout, and command
        invocation exceptions.
    Args:
        monkeypatch: Pytest monkeypatch fixture.
        tmp_path: Pytest temporary directory fixture.
    Output:
        Returns `None`; test passes when runtime returns hard failure.
    """

    invocation = _build_invocation(tmp_path)

    def fake_invoke(**_: object) -> subprocess.CompletedProcess[str]:
        """Raise deterministic invocation error for failure-path tests.

        Purpose:
            Simulate pi command failure in runtime tests.
        Args:
            **_: Ignored keyword args.
        Output:
            Raises PiCodingAgentInvocationError for testing.
        Raises:
            PiCodingAgentInvocationError: Always raised in this stub.
        """

        raise runtime_module.PiCodingAgentInvocationError("simulated pi failure")

    monkeypatch.setattr(runtime_module, "_invoke_pi_coding_agent", fake_invoke)

    result = runtime_module.run_resume_review_pipeline(invocation=invocation)

    assert result.success is False
    assert result.hard_failure is True
    assert "simulated pi failure" in (result.failure_reason or "")


def test_runtime_fails_when_report_missing_or_invalid(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify runtime fails hard when report artifact cannot be validated.

    Purpose:
        Enforce strict report handshake for review completion.
    Args:
        monkeypatch: Pytest monkeypatch fixture.
        tmp_path: Pytest temporary directory fixture.
    Output:
        Returns `None`; test passes when runtime returns hard failure.
    """

    invocation = _build_invocation(tmp_path)

    monkeypatch.setattr(
        runtime_module,
        "_invoke_pi_coding_agent",
        lambda **_: subprocess.CompletedProcess(
            args=["pi"], returncode=0, stdout="agent ok", stderr=""
        ),
    )

    def fake_report(*, report_path: Path) -> ReviewReport:
        """Raise deterministic report validation error.

        Purpose:
            Simulate missing or malformed report artifact failure path.
        Args:
            report_path: Requested report path.
        Output:
            Raises runtime error for test assertions.
        Raises:
            RuntimeError: Always raised in this stub.
        """

        _ = report_path
        raise RuntimeError("invalid review report")

    monkeypatch.setattr(runtime_module, "_load_review_report", fake_report)

    result = runtime_module.run_resume_review_pipeline(invocation=invocation)

    assert result.success is False
    assert result.hard_failure is True
    assert "invalid review report" in (result.failure_reason or "")


def test_runtime_fails_when_selected_artifact_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify runtime fails hard when report points to missing selected refs.

    Purpose:
        Enforce strict artifact-reference checks for PASS/TAILORED/BASE verdicts.
    Args:
        monkeypatch: Pytest monkeypatch fixture.
        tmp_path: Pytest temporary directory fixture.
    Output:
        Returns `None`; test passes when runtime rejects missing file refs.
    """

    invocation = _build_invocation(tmp_path)

    monkeypatch.setattr(
        runtime_module,
        "_invoke_pi_coding_agent",
        lambda **_: subprocess.CompletedProcess(
            args=["pi"], returncode=0, stdout="agent ok", stderr=""
        ),
    )

    missing_pdf_path = tmp_path / "missing.pdf"

    monkeypatch.setattr(
        runtime_module,
        "_load_review_report",
        lambda report_path: ReviewReport(
            verdict=ReviewVerdict.TAILORED,
            summary="Keep tailored output",
            iteration_count=1,
            selected_yaml_path=invocation.tailored_yaml_path,
            selected_tex_path=invocation.tailored_tex_path,
            selected_pdf_path=str(missing_pdf_path),
        ),
    )

    result = runtime_module.run_resume_review_pipeline(invocation=invocation)

    assert result.success is False
    assert result.hard_failure is True
    assert "missing selected artifacts" in (result.failure_reason or "")


def test_workspace_defaults_to_repo_root(tmp_path: Path) -> None:
    """Verify default review-agent workspace resolves to repository root.

    Purpose:
        Ensure prompt examples that run `python -m scripts.*` commands execute
        from a module-resolvable working directory by default.
    Args:
        tmp_path: Pytest temporary directory fixture.
    Output:
        Returns `None`; test passes when workspace path equals repo root.
    """

    invocation = _build_invocation(tmp_path)
    repo_root = tmp_path / "repo_root"
    repo_root.mkdir(parents=True, exist_ok=True)

    workspace_path = runtime_module._resolve_pi_workspace_dir(
        invocation=invocation,
        repo_root=repo_root,
    )

    assert workspace_path == repo_root.resolve()
