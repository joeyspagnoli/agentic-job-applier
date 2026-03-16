"""Runtime loop for pi-mono post-tailor resume review.

Purpose:
    Execute one high-agency review-agent invocation while runtime enforces only
    hard operational boundaries (timeout, crash, missing/invalid report).
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path

from .prompts import build_review_instruction
from .schemas import ReviewInvocationContract
from .schemas import ReviewReport
from .schemas import ReviewRunResult
from .schemas import ReviewVerdict

DEFAULT_PI_ARGV_COMMAND_ENV = "PI_CODING_AGENT_COMMAND_ARGV"
DEFAULT_PI_COMMAND_ENV = "PI_CODING_AGENT_COMMAND"
DEFAULT_PI_COMMAND_ARGV: tuple[str, ...] = (
    "pi",
    "--print",
    "--mode",
    "text",
    "--no-session",
)


class PiCodingAgentInvocationError(RuntimeError):
    """Represent a failed pi-coding-agent command invocation."""


def _resolve_pi_command(invocation: ReviewInvocationContract) -> list[str]:
    """Resolve pi-coding-agent command tokens for this review run.

    Purpose:
        Centralize command resolution from invocation fields and environment
        variables so runtime behavior stays deterministic and testable.
    Args:
        invocation: Validated review invocation payload.
    Output:
        Returns subprocess argv token list.
    Raises:
        PiCodingAgentInvocationError: When configured argv payload is invalid.
    """

    base_argv: list[str]

    if invocation.pi_coding_agent_command_argv:
        base_argv = list(invocation.pi_coding_agent_command_argv)
    else:
        raw_argv_json = os.getenv(DEFAULT_PI_ARGV_COMMAND_ENV, "").strip()
        if raw_argv_json != "":
            try:
                parsed_argv = json.loads(raw_argv_json)
            except json.JSONDecodeError as exc:
                raise PiCodingAgentInvocationError(
                    f"Invalid {DEFAULT_PI_ARGV_COMMAND_ENV} JSON payload: {exc}"
                ) from exc

            if isinstance(parsed_argv, list) and all(
                isinstance(token, str) and token.strip() != "" for token in parsed_argv
            ):
                base_argv = [token.strip() for token in parsed_argv]
            else:
                raise PiCodingAgentInvocationError(
                    f"{DEFAULT_PI_ARGV_COMMAND_ENV} must be a JSON string array"
                )
        else:
            raw_command = invocation.pi_coding_agent_command
            if raw_command is None or raw_command.strip() == "":
                raw_command = os.getenv(DEFAULT_PI_COMMAND_ENV, "").strip()
            if raw_command != "":
                base_argv = shlex.split(raw_command)
            else:
                base_argv = list(DEFAULT_PI_COMMAND_ARGV)

    if invocation.pi_model:
        return base_argv + ["--model", invocation.pi_model]
    return base_argv


def _resolve_pi_workspace_dir(
    *,
    invocation: ReviewInvocationContract,
    repo_root: Path,
) -> Path:
    """Resolve the working directory used for pi-coding-agent subprocess runs.

    Purpose:
        Keep review-agent execution scoped to an explicit workspace directory.
    Args:
        invocation: Validated review invocation payload.
        repo_root: Repository root used for resolving relative workspace paths.
    Output:
        Returns absolute workspace path.
    """

    configured_workspace = invocation.pi_coding_agent_workspace_dir
    if configured_workspace is not None and configured_workspace.strip() != "":
        workspace_path = Path(configured_workspace).expanduser()
        if not workspace_path.is_absolute():
            workspace_path = repo_root / workspace_path
    else:
        # Default to repository root so `python -m scripts.*` tool commands in
        # prompts resolve consistently during agent execution.
        workspace_path = repo_root

    workspace_path.mkdir(parents=True, exist_ok=True)
    return workspace_path.resolve()


def _build_pi_environment(invocation: ReviewInvocationContract) -> dict[str, str]:
    """Build a conservative environment map for review-agent subprocess calls.

    Purpose:
        Limit subprocess environment exposure to an explicit allowlist while
        preserving required runtime variables.
    Args:
        invocation: Validated review invocation payload.
    Output:
        Returns deterministic environment dictionary.
    """

    environment: dict[str, str] = {}
    for variable_name in invocation.pi_coding_agent_env_allowlist:
        variable_value = os.getenv(variable_name)
        if variable_value is not None:
            environment[variable_name] = variable_value

    if "PATH" not in environment and "PATH" in os.environ:
        environment["PATH"] = os.environ["PATH"]

    environment["PI_RESUME_REVIEW_MODE"] = "1"
    environment["PI_RESUME_REVIEW_MAX_ITERATIONS"] = str(
        invocation.max_review_iterations
    )
    return environment


def _invoke_pi_coding_agent(
    *,
    invocation: ReviewInvocationContract,
    instruction_text: str,
    workspace_dir: Path,
) -> subprocess.CompletedProcess[str]:
    """Invoke pi-coding-agent for one review run.

    Purpose:
        Execute one model-driven review session while keeping timeout and
        non-zero exit handling explicit.
    Args:
        invocation: Validated review invocation payload.
        instruction_text: Prompt text sent through stdin.
        workspace_dir: Working directory for subprocess execution.
    Output:
        Returns completed subprocess payload.
    Raises:
        PiCodingAgentInvocationError: When command execution fails.
    """

    command_tokens = _resolve_pi_command(invocation)
    process_environment = _build_pi_environment(invocation)

    try:
        completed_process = subprocess.run(
            command_tokens,
            cwd=workspace_dir,
            check=False,
            text=True,
            input=instruction_text,
            capture_output=True,
            env=process_environment,
            timeout=invocation.pi_coding_agent_timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise PiCodingAgentInvocationError(
            "Failed to execute pi-coding-agent command. Ensure the first argv "
            f"token exists in PATH: {command_tokens[0]}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise PiCodingAgentInvocationError(
            "pi-coding-agent command timed out after "
            f"{invocation.pi_coding_agent_timeout_seconds} seconds"
        ) from exc

    if completed_process.returncode != 0:
        raise PiCodingAgentInvocationError(
            "pi-coding-agent command failed with non-zero exit code. "
            f"stdout:\n{completed_process.stdout}\n"
            f"stderr:\n{completed_process.stderr}"
        )

    return completed_process


def _load_review_report(*, report_path: Path) -> ReviewReport:
    """Load and validate the review report artifact from disk.

    Purpose:
        Enforce the report handshake contract that marks review completion.
    Args:
        report_path: Absolute report path expected from agent tool usage.
    Output:
        Returns validated `ReviewReport` model.
    Raises:
        RuntimeError: When report file is missing or invalid.
    """

    if not report_path.exists():
        raise RuntimeError(f"Review report artifact not found: {report_path}")

    try:
        report_payload = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Review report is not valid JSON at {report_path}: {exc}"
        ) from exc

    try:
        return ReviewReport.model_validate(report_payload)
    except Exception as exc:
        raise RuntimeError(f"Review report schema validation failed: {exc}") from exc


def _validate_selected_artifacts(*, review_report: ReviewReport) -> None:
    """Validate selected artifact references when verdict requires artifacts.

    Purpose:
        Keep downstream handoff deterministic by ensuring selected artifact
        paths exist for PASS/TAILORED/BASE verdicts.
    Args:
        review_report: Validated review-report payload.
    Output:
        Returns `None` when selected artifacts pass hard checks.
    Raises:
        RuntimeError: When required selected artifacts are missing on disk.
    """

    if review_report.verdict == ReviewVerdict.FAIL:
        return

    required_paths = [
        review_report.selected_yaml_path,
        review_report.selected_tex_path,
        review_report.selected_pdf_path,
    ]
    missing_paths = [
        path_value
        for path_value in required_paths
        if path_value is None or not Path(path_value).resolve().exists()
    ]

    if missing_paths:
        raise RuntimeError(
            "Review report references missing selected artifacts: "
            f"{', '.join(str(path_value) for path_value in missing_paths)}"
        )


def run_resume_review_pipeline(
    *, invocation: ReviewInvocationContract
) -> ReviewRunResult:
    """Run the pi-mono review runtime with hard-error-only boundaries.

    Purpose:
        Execute one high-agency agent review session and accept the agent's
        verdict while runtime enforces timeout/crash/report-schema safety.
    Args:
        invocation: Validated review invocation contract.
    Output:
        Returns `ReviewRunResult` with either validated report output or hard
        runtime failure details.
    """

    repo_root = Path(__file__).resolve().parents[3]
    report_path = Path(invocation.review_report_path).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)

    if report_path.exists():
        report_path.unlink()

    pi_workspace_dir = _resolve_pi_workspace_dir(
        invocation=invocation,
        repo_root=repo_root,
    )

    instruction_text = build_review_instruction(invocation=invocation)

    try:
        completed_process = _invoke_pi_coding_agent(
            invocation=invocation,
            instruction_text=instruction_text,
            workspace_dir=pi_workspace_dir,
        )
    except Exception as exc:
        return ReviewRunResult(
            success=False,
            failure_reason=str(exc),
            hard_failure=True,
            review_report_path=str(report_path),
            agent_stdout=None,
            agent_stderr=None,
        )

    try:
        review_report = _load_review_report(report_path=report_path)
        _validate_selected_artifacts(review_report=review_report)
    except Exception as exc:
        return ReviewRunResult(
            success=False,
            failure_reason=str(exc),
            hard_failure=True,
            review_report_path=str(report_path),
            agent_stdout=completed_process.stdout,
            agent_stderr=completed_process.stderr,
        )

    return ReviewRunResult(
        success=True,
        hard_failure=False,
        verdict=review_report.verdict,
        review_report_path=str(report_path),
        review_report=review_report,
        selected_yaml_path=review_report.selected_yaml_path,
        selected_tex_path=review_report.selected_tex_path,
        selected_pdf_path=review_report.selected_pdf_path,
        agent_stdout=completed_process.stdout,
        agent_stderr=completed_process.stderr,
    )
