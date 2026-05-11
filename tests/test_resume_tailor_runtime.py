"""Validate one-page enforcement behavior for resume-tailor runtime loop.

Purpose:
    Ensure the runtime performs content retries before layout compression and
    reports explicit failures when one-page constraints remain unmet.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from src.agents.resume_tailor_adk.schemas import TailorInvocationContract
from src.agents.resume_tailor_pi import runtime as runtime_module


def _build_invocation(tmp_path: Path) -> TailorInvocationContract:
    """Build a deterministic invocation payload for runtime tests.

    Purpose:
        Keep test setup concise while reusing one valid invocation contract for
        different runtime scenarios.
    Args:
        tmp_path: Pytest temporary directory fixture.
    Output:
        Returns a validated `TailorInvocationContract` instance.
    """

    source_yaml_path = Path("config/resume_content.yaml").resolve()
    working_yaml_path = tmp_path / "resume_content.yaml"
    shutil.copy2(source_yaml_path, working_yaml_path)

    return TailorInvocationContract.model_validate(
        {
            "job_ref": {"job_hash": "abc123hash"},
            "database_path": str(tmp_path / "jobs.db"),
            "resume_yaml_path": str(working_yaml_path),
            "render_template_path": "",
            "output_tex_path": str(tmp_path / "resume.tex"),
            "output_pdf_path": str(tmp_path / "resume.pdf"),
            "page_limit": 1,
            "content_readjust_attempts": 2,
            "layout_bounds_profile": "balanced",
            "pi_coding_agent_command": "echo simulated",
            "create_git_branch": False,
            "branch_prefix": "resume-tailor",
        }
    )


def test_runtime_uses_two_content_retries_before_layout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify overflow handling sequence is content then layout.

    Purpose:
        Ensure exactly two post-overflow content retries occur before bounded
        layout compression is attempted.
    Args:
        monkeypatch: Pytest fixture used to patch runtime side effects.
        tmp_path: Pytest temporary directory fixture.
    Output:
        Returns `None`; test passes when phase order and attempt count match.
    """

    invocation = _build_invocation(tmp_path)
    measured_pages = iter([2, 2, 2, 1])

    def fake_invoke(**_: object) -> str:
        """Return a no-op stdout string for mocked agent invocation.

        Purpose:
            Remove external command dependency from runtime sequencing tests.
        Args:
            **_: Ignored invocation arguments.
        Output:
            Returns deterministic stdout text.
        """

        return "ok"

    def fake_compile_and_measure(*, invocation: TailorInvocationContract) -> int:
        """Return deterministic page counts for each runtime pass.

        Purpose:
            Simulate overflow across content passes and success after layout
            compression without invoking TeX tooling.
        Args:
            invocation: Invocation payload for the current run.
        Output:
            Returns deterministic page count sequence values.
        """

        _ = invocation
        return next(measured_pages)

    monkeypatch.setattr(runtime_module, "invoke_pi_coding_agent", fake_invoke)
    monkeypatch.setattr(
        runtime_module,
        "_compile_and_measure_pages",
        fake_compile_and_measure,
    )

    run_result = runtime_module.run_resume_tailor_pipeline(invocation=invocation)

    assert run_result.success is True
    assert [attempt.phase for attempt in run_result.attempts] == [
        "content",
        "content",
        "content",
        "layout",
    ]
    assert run_result.attempts[-1].success is True


def test_runtime_succeeds_when_first_content_pass_fits(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify runtime exits after first content pass when page count is valid.

    Purpose:
        Protect the one-page happy path so runtime avoids unnecessary retries
        when the first compile already satisfies page constraints.
    Args:
        monkeypatch: Pytest fixture used to patch runtime side effects.
        tmp_path: Pytest temporary directory fixture.
    Output:
        Returns `None`; test passes when runtime exits with one success attempt.
    """

    invocation = _build_invocation(tmp_path)

    def fake_invoke(**_: object) -> str:
        """Return deterministic stdout for mocked agent invocation.

        Purpose:
            Remove external command dependency from happy-path runtime tests.
        Args:
            **_: Ignored invocation arguments.
        Output:
            Returns deterministic stdout text.
        """

        return "ok"

    def fake_compile_and_measure(*, invocation: TailorInvocationContract) -> int:
        """Return one-page result for the first content pass.

        Purpose:
            Simulate compile behavior where first attempt already fits page
            limits so runtime should terminate immediately.
        Args:
            invocation: Invocation payload for the current run.
        Output:
            Returns page count `1`.
        """

        _ = invocation
        return 1

    monkeypatch.setattr(runtime_module, "invoke_pi_coding_agent", fake_invoke)
    monkeypatch.setattr(
        runtime_module,
        "_compile_and_measure_pages",
        fake_compile_and_measure,
    )

    run_result = runtime_module.run_resume_tailor_pipeline(invocation=invocation)

    assert run_result.success is True
    assert run_result.final_page_count == 1
    assert len(run_result.attempts) == 1
    assert run_result.attempts[0].phase == "content"
    assert run_result.attempts[0].success is True


def test_runtime_fails_when_layout_still_overflows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify runtime returns explicit failure when page overflow persists.

    Purpose:
        Ensure hard one-page policy does not silently pass when both content and
        layout corrections fail to fit output on one page.
    Args:
        monkeypatch: Pytest fixture used to patch runtime side effects.
        tmp_path: Pytest temporary directory fixture.
    Output:
        Returns `None`; test passes when failure payload is explicit.
    """

    invocation = _build_invocation(tmp_path)
    measured_pages = iter([2, 2, 2, 2])

    def fake_invoke(**_: object) -> str:
        """Return a no-op stdout string for mocked agent invocation.

        Purpose:
            Remove external command dependency from overflow-failure tests.
        Args:
            **_: Ignored invocation arguments.
        Output:
            Returns deterministic stdout text.
        """

        return "ok"

    def fake_compile_and_measure(*, invocation: TailorInvocationContract) -> int:
        """Return deterministic always-overflow page counts.

        Purpose:
            Simulate unrecoverable overflow across all phases.
        Args:
            invocation: Invocation payload for the current run.
        Output:
            Returns deterministic page count sequence values.
        """

        _ = invocation
        return next(measured_pages)

    monkeypatch.setattr(runtime_module, "invoke_pi_coding_agent", fake_invoke)
    monkeypatch.setattr(
        runtime_module,
        "_compile_and_measure_pages",
        fake_compile_and_measure,
    )

    run_result = runtime_module.run_resume_tailor_pipeline(invocation=invocation)

    assert run_result.success is False
    assert run_result.failure_reason is not None
    assert "one page" in run_result.failure_reason.lower()
    assert run_result.attempts[-1].phase == "layout"
    assert run_result.attempts[-1].success is False


def test_runtime_restores_yaml_after_failed_content_pass(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify runtime restores last valid YAML snapshot after content failure.

    Purpose:
        Ensure malformed writes in a failed content pass do not persist to the
        canonical YAML artifact.
    Args:
        monkeypatch: Pytest fixture used to patch runtime side effects.
        tmp_path: Pytest temporary directory fixture.
    Output:
        Returns `None`; test passes when failed-pass edits are rolled back.
    """

    invocation = _build_invocation(tmp_path)
    yaml_path = Path(invocation.resume_yaml_path)
    baseline_yaml_text = yaml_path.read_text(encoding="utf-8")

    def fake_invoke(**_: object) -> str:
        """Write malformed YAML and raise to trigger runtime rollback path.

        Purpose:
            Simulate a failed agent pass that leaves the YAML file corrupted
            before runtime error handling executes.
        Args:
            **_: Ignored invocation arguments.
        Output:
            Raises RuntimeError to force failure/restore path.
        Raises:
            RuntimeError: Always raised to simulate failed content pass.
        """

        yaml_path.write_text("invalid: [", encoding="utf-8")
        raise RuntimeError("simulated content pass failure")

    monkeypatch.setattr(runtime_module, "invoke_pi_coding_agent", fake_invoke)

    run_result = runtime_module.run_resume_tailor_pipeline(invocation=invocation)

    restored_yaml_text = yaml_path.read_text(encoding="utf-8")
    assert run_result.success is False
    assert restored_yaml_text == baseline_yaml_text


def test_maybe_checkout_tailor_branch_creates_branch_in_clean_repo(
    tmp_path: Path,
) -> None:
    """Verify branch helper creates and checks out a deterministic branch.

    Purpose:
        Cover the optional branch-creation path used by `run_resume_tailor.py`
        when callers request isolated tailoring edits.
    Args:
        tmp_path: Pytest temporary directory fixture.
    Output:
        Returns `None`; test passes when helper returns the active new branch.
    """

    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )

    tracked_file = repo_root / "README.md"
    tracked_file.write_text("# test\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "README.md"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "initial commit"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )

    invocation = TailorInvocationContract.model_validate(
        {
            "job_ref": {"job_hash": "abc123hash"},
            "database_path": str(tmp_path / "jobs.db"),
            "resume_yaml_path": str(tmp_path / "resume_content.yaml"),
            "output_tex_path": str(tmp_path / "resume.tex"),
            "output_pdf_path": str(tmp_path / "resume.pdf"),
            "create_git_branch": True,
            "branch_prefix": "resume-tailor",
            "branch_allow_dirty": False,
        }
    )

    branch_name = runtime_module.maybe_checkout_tailor_branch(
        invocation=invocation,
        repo_root=repo_root,
    )

    current_branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo_root,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()

    assert branch_name is not None
    assert branch_name.startswith("resume-tailor/abc123hash/")
    assert current_branch == branch_name


def test_workspace_defaults_to_repo_root(tmp_path: Path) -> None:
    """Verify default tailor-agent workspace resolves to repository root.

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
