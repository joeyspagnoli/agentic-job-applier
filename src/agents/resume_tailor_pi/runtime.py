"""Runtime loop for pi-mono YAML-canonical resume tailoring.

Purpose:
    Execute the end-to-end tailoring cycle with lock checks, render/compile,
    and hard one-page enforcement semantics.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from datetime import datetime
from pathlib import Path

from .compiler import compile_resume_tex
from .compiler import get_pdf_page_count
from .prompts import build_tailor_instruction
from .renderer import render_resume_yaml_to_tex
from .schemas import ResumeContent
from .schemas import TailorAttemptRecord
from .schemas import TailorInvocationContract
from .schemas import TailorRunResult
from .schemas import build_locked_section_snapshot
from .schemas import ensure_locked_sections_unchanged
from .yaml_io import load_resume_yaml
from .yaml_io import save_resume_yaml

DEFAULT_BRANCH_TIME_FORMAT = "%Y%m%d-%H%M%S"
DEFAULT_PI_ARGV_COMMAND_ENV = "PI_CODING_AGENT_COMMAND_ARGV"
DEFAULT_PI_COMMAND_ENV = "PI_CODING_AGENT_COMMAND"
DEFAULT_PI_COMMAND_ARGV: tuple[str, ...] = (
    "pi",
    "--print",
    "--mode",
    "text",
    "--no-session",
)
BALANCED_MARGIN_MIN = 0.46
BALANCED_TOP_VSPACE_MIN = -0.55
BALANCED_SECTION_FONT_MIN = 12.5
BALANCED_SECTION_LINE_HEIGHT_MIN = 14.0
BALANCED_SECTION_SPACING_MIN = 0.0
BALANCED_SUBHEADING_ITEMSEP_MIN = 1.0
BALANCED_BULLET_ITEMSEP_MIN = 0.2


class PiCodingAgentInvocationError(RuntimeError):
    """Represent a failed pi-coding-agent command invocation."""


class ResumePageFitError(RuntimeError):
    """Represent a terminal failure to satisfy one-page constraints."""


def _job_ref_for_branch(invocation: TailorInvocationContract) -> str:
    """Build a branch-name-safe token from invocation job selector fields.

    Purpose:
        Keep per-run branch naming deterministic and readable regardless of
        whether callers use job hash or numeric job ID selectors.
    Args:
        invocation: Validated tailor invocation payload.
    Output:
        Returns a short token string suitable for git branch names.
    """

    if invocation.job_ref.job_hash is not None:
        return invocation.job_ref.job_hash[:12]
    return f"id{invocation.job_ref.job_id}"


def _run_git_command(
    *,
    repo_root: Path,
    args: list[str],
) -> subprocess.CompletedProcess[str]:
    """Run one git command and return the captured process payload.

    Purpose:
        Centralize git invocation behavior and captured output handling for
        branch preflight and creation steps.
    Args:
        repo_root: Repository root where git should execute.
        args: Argument list passed to `git`.
    Output:
        Returns completed subprocess payload for the executed git command.
    """

    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        text=True,
        capture_output=True,
    )


def _get_current_branch_name(repo_root: Path) -> str:
    """Get the currently checked-out branch name.

    Purpose:
        Capture an explicit base branch reference before creating a per-run
        tailor branch.
    Args:
        repo_root: Repository root where git should execute.
    Output:
        Returns the current branch name.
    Raises:
        RuntimeError: When current branch cannot be resolved.
    """

    branch_process = _run_git_command(
        repo_root=repo_root,
        args=["rev-parse", "--abbrev-ref", "HEAD"],
    )
    branch_name = branch_process.stdout.strip()
    if branch_process.returncode != 0 or branch_name == "":
        raise RuntimeError(
            "Could not resolve current git branch before tailor branch creation"
        )
    return branch_name


def maybe_checkout_tailor_branch(
    *,
    invocation: TailorInvocationContract,
    repo_root: Path,
) -> str | None:
    """Optionally create and checkout a dedicated branch for this run.

    Purpose:
        Support safer tailoring sessions by isolating generated edits on a new
        branch when callers opt into branch creation.
    Args:
        invocation: Validated tailor invocation payload.
        repo_root: Repository root where git commands should run.
    Output:
        Returns checked-out branch name when created, otherwise `None`.
    Raises:
        RuntimeError: When branch creation is requested but git commands fail.
    """

    if not invocation.create_git_branch:
        return None

    inside_repo = _run_git_command(
        repo_root=repo_root,
        args=["rev-parse", "--is-inside-work-tree"],
    )
    if inside_repo.returncode != 0:
        raise RuntimeError(
            "Branch creation requested but current path is not a git repo"
        )

    status_process = _run_git_command(
        repo_root=repo_root,
        args=["status", "--porcelain"],
    )
    if status_process.returncode != 0:
        raise RuntimeError("Could not read git status before tailor branch creation")
    if status_process.stdout.strip() != "" and not invocation.branch_allow_dirty:
        raise RuntimeError(
            "Repository has uncommitted changes. Commit/stash changes or set "
            "`branch_allow_dirty=true` to proceed."
        )

    base_ref = invocation.branch_base_ref or _get_current_branch_name(repo_root)
    timestamp = datetime.utcnow().strftime(DEFAULT_BRANCH_TIME_FORMAT)
    branch_name = (
        f"{invocation.branch_prefix}/{_job_ref_for_branch(invocation)}/{timestamp}"
    )

    create_branch = _run_git_command(
        repo_root=repo_root,
        args=["checkout", "-b", branch_name, base_ref],
    )
    if create_branch.returncode != 0:
        raise RuntimeError(
            f"Failed to create branch for tailoring run: {create_branch.stderr.strip()}"
        )

    return branch_name


def _resolve_pi_command(invocation: TailorInvocationContract) -> list[str]:
    """Resolve the pi-coding-agent command tokens for this run.

    Purpose:
        Centralize command resolution from invocation payload or environment so
        runtime invocation behavior is explicit and testable.
    Args:
        invocation: Validated tailor invocation payload.
    Output:
        Returns shell-tokenized command list for subprocess execution.
    Raises:
        PiCodingAgentInvocationError: When no command is configured.
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
                # Fall back to a deterministic non-interactive baseline command.
                base_argv = list(DEFAULT_PI_COMMAND_ARGV)

    if invocation.pi_model:
        base_argv = base_argv + ["--model", invocation.pi_model]
    return base_argv


def _resolve_pi_workspace_dir(
    *,
    invocation: TailorInvocationContract,
    repo_root: Path,
) -> Path:
    """Resolve the working directory used for pi-coding-agent subprocess runs.

    Purpose:
        Keep model execution scoped to an explicit workspace path instead of an
        implicit repository root.
    Args:
        invocation: Validated tailor invocation payload.
        repo_root: Repository root used for resolving relative paths.
    Output:
        Returns an absolute workspace directory path.
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


def _build_pi_environment(invocation: TailorInvocationContract) -> dict[str, str]:
    """Build a conservative environment map for pi-coding-agent invocation.

    Purpose:
        Limit subprocess environment exposure to an explicit allowlist while
        preserving required runtime variables.
    Args:
        invocation: Validated tailor invocation payload.
    Output:
        Returns a deterministic environment dictionary.
    """

    environment: dict[str, str] = {}
    for variable_name in invocation.pi_coding_agent_env_allowlist:
        variable_value = os.getenv(variable_name)
        if variable_value is not None:
            environment[variable_name] = variable_value

    if "PATH" not in environment and "PATH" in os.environ:
        environment["PATH"] = os.environ["PATH"]

    environment["PI_RESUME_TAILOR_MODE"] = "1"
    environment["PI_RESUME_TAILOR_PAGE_LIMIT"] = str(invocation.page_limit)
    return environment


def invoke_pi_coding_agent(
    *,
    invocation: TailorInvocationContract,
    instruction_text: str,
    workspace_dir: Path,
) -> str:
    """Invoke pi-coding-agent command for one tailoring pass.

    Purpose:
        Execute one model-driven edit pass against the canonical YAML file while
        keeping runtime invocation and errors explicit.
    Args:
        invocation: Validated tailor invocation payload.
        instruction_text: Prompt text sent to the coding-agent command stdin.
        workspace_dir: Working directory used as subprocess execution root.
    Output:
        Returns stdout text emitted by the command.
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

    return completed_process.stdout


def apply_balanced_layout_compression(
    *, resume_content: ResumeContent
) -> ResumeContent:
    """Apply bounded balanced-profile layout compression.

    Purpose:
        Provide deterministic, constrained layout compression after exhausting
        content retries while preserving readability.
    Args:
        resume_content: Current canonical resume model.
    Output:
        Returns a new `ResumeContent` model with compressed layout knobs.
    """

    updated_resume = resume_content.model_copy(deep=True)
    layout = updated_resume.layout

    layout.margin_in = max(BALANCED_MARGIN_MIN, layout.margin_in - 0.03)
    layout.top_vspace_in = max(BALANCED_TOP_VSPACE_MIN, layout.top_vspace_in - 0.05)
    layout.section_heading_font_size_pt = max(
        BALANCED_SECTION_FONT_MIN,
        layout.section_heading_font_size_pt - 0.5,
    )
    layout.section_heading_line_height_pt = max(
        BALANCED_SECTION_LINE_HEIGHT_MIN,
        layout.section_heading_line_height_pt - 0.5,
    )
    layout.section_spacing_before_pt = max(
        BALANCED_SECTION_SPACING_MIN,
        layout.section_spacing_before_pt - 0.5,
    )
    layout.section_spacing_after_pt = max(
        BALANCED_SECTION_SPACING_MIN,
        layout.section_spacing_after_pt - 0.5,
    )
    layout.subheading_itemsep_pt = max(
        BALANCED_SUBHEADING_ITEMSEP_MIN,
        layout.subheading_itemsep_pt - 0.5,
    )
    layout.bullet_itemsep_pt = max(
        BALANCED_BULLET_ITEMSEP_MIN,
        layout.bullet_itemsep_pt - 0.4,
    )

    return updated_resume


def _restore_yaml_snapshot(*, yaml_path: Path, snapshot_text: str) -> None:
    """Restore YAML file content from the latest known-valid snapshot.

    Purpose:
        Prevent partial or invalid edits from persisting when compile or lock
        checks fail mid-run.
    Args:
        yaml_path: Canonical resume YAML path to restore.
        snapshot_text: Previously saved valid YAML file content.
    Output:
        Returns `None` after writing the snapshot back to disk.
    """

    with open(yaml_path, "w", encoding="utf-8") as yaml_file:
        yaml_file.write(snapshot_text)


def _compile_and_measure_pages(
    *,
    invocation: TailorInvocationContract,
) -> int:
    """Render, compile, and return page count for current YAML content.

    Purpose:
        Keep render/compile/page-check behavior centralized for consistent
        enforcement across content and layout phases.
    Args:
        invocation: Validated tailor invocation payload.
    Output:
        Returns integer page count extracted from compiled PDF output.
    """

    tex_path = render_resume_yaml_to_tex(
        yaml_path=invocation.resume_yaml_path,
        tex_output_path=invocation.output_tex_path,
    )
    pdf_path = compile_resume_tex(
        tex_path=tex_path,
        pdf_output_path=invocation.output_pdf_path,
    )
    log_path = tex_path.with_suffix(".log")
    return get_pdf_page_count(pdf_path=pdf_path, log_path=log_path)


def run_resume_tailor_pipeline(
    *, invocation: TailorInvocationContract
) -> TailorRunResult:
    """Run the V1 pi-mono resume-tailor loop with one-page enforcement.

    Purpose:
        Execute content passes, enforce lock boundaries, compile artifacts, and
        guarantee either a one-page result or explicit failure.
    Args:
        invocation: Validated runtime invocation contract.
    Output:
        Returns a `TailorRunResult` describing success/failure and run history.
    """

    repo_root = Path(__file__).resolve().parents[3]
    pi_workspace_dir = _resolve_pi_workspace_dir(
        invocation=invocation,
        repo_root=repo_root,
    )
    yaml_path = Path(invocation.resume_yaml_path).resolve()
    attempts: list[TailorAttemptRecord] = []

    try:
        baseline_resume = load_resume_yaml(yaml_path)
        locked_snapshot = build_locked_section_snapshot(baseline_resume)
        with open(yaml_path, "r", encoding="utf-8") as yaml_file:
            last_valid_yaml_snapshot = yaml_file.read()
    except Exception as exc:
        return TailorRunResult(
            success=False,
            failure_reason=f"Failed to load baseline resume YAML: {exc}",
            output_tex_path=invocation.output_tex_path,
            output_pdf_path=invocation.output_pdf_path,
            final_page_count=None,
            attempts=attempts,
            active_git_branch=None,
        )

    try:
        active_branch = maybe_checkout_tailor_branch(
            invocation=invocation,
            repo_root=repo_root,
        )
    except Exception as exc:
        return TailorRunResult(
            success=False,
            failure_reason=f"Failed to create tailor branch: {exc}",
            output_tex_path=invocation.output_tex_path,
            output_pdf_path=invocation.output_pdf_path,
            final_page_count=None,
            attempts=attempts,
            active_git_branch=None,
        )
    current_page_count: int | None = None

    total_content_passes = invocation.content_readjust_attempts + 1
    for content_index in range(total_content_passes):
        try:
            instruction_text = build_tailor_instruction(
                invocation=invocation,
                phase="content",
                attempt_index=content_index,
                current_page_count=current_page_count,
            )
            invoke_pi_coding_agent(
                invocation=invocation,
                instruction_text=instruction_text,
                workspace_dir=pi_workspace_dir,
            )

            current_resume = load_resume_yaml(yaml_path)
            ensure_locked_sections_unchanged(
                current_resume,
                locked_snapshot=locked_snapshot,
            )
            current_page_count = _compile_and_measure_pages(invocation=invocation)
            with open(yaml_path, "r", encoding="utf-8") as yaml_file:
                last_valid_yaml_snapshot = yaml_file.read()
        except Exception as exc:
            _restore_yaml_snapshot(
                yaml_path=yaml_path,
                snapshot_text=last_valid_yaml_snapshot,
            )
            attempts.append(
                TailorAttemptRecord(
                    phase="content",
                    attempt_index=content_index,
                    page_count=current_page_count,
                    success=False,
                    message=f"Failed content pass: {exc}",
                )
            )
            return TailorRunResult(
                success=False,
                failure_reason=str(exc),
                output_tex_path=invocation.output_tex_path,
                output_pdf_path=invocation.output_pdf_path,
                final_page_count=current_page_count,
                attempts=attempts,
                active_git_branch=active_branch,
            )

        if current_page_count <= invocation.page_limit:
            attempts.append(
                TailorAttemptRecord(
                    phase="content",
                    attempt_index=content_index,
                    page_count=current_page_count,
                    success=True,
                    message="Content pass satisfied page limit",
                )
            )
            return TailorRunResult(
                success=True,
                output_tex_path=invocation.output_tex_path,
                output_pdf_path=invocation.output_pdf_path,
                final_page_count=current_page_count,
                attempts=attempts,
                active_git_branch=active_branch,
            )

        attempts.append(
            TailorAttemptRecord(
                phase="content",
                attempt_index=content_index,
                page_count=current_page_count,
                success=False,
                message="Compiled successfully but exceeds one-page limit",
            )
        )

    try:
        current_resume = load_resume_yaml(yaml_path)
        ensure_locked_sections_unchanged(
            current_resume, locked_snapshot=locked_snapshot
        )

        compressed_resume = apply_balanced_layout_compression(
            resume_content=current_resume
        )
        save_resume_yaml(path=yaml_path, resume_content=compressed_resume)
        current_page_count = _compile_and_measure_pages(invocation=invocation)

        if current_page_count <= invocation.page_limit:
            attempts.append(
                TailorAttemptRecord(
                    phase="layout",
                    attempt_index=0,
                    page_count=current_page_count,
                    success=True,
                    message="Balanced layout compression satisfied page limit",
                )
            )
            return TailorRunResult(
                success=True,
                output_tex_path=invocation.output_tex_path,
                output_pdf_path=invocation.output_pdf_path,
                final_page_count=current_page_count,
                attempts=attempts,
                active_git_branch=active_branch,
            )

        attempts.append(
            TailorAttemptRecord(
                phase="layout",
                attempt_index=0,
                page_count=current_page_count,
                success=False,
                message="Balanced layout compression still exceeds one-page limit",
            )
        )
        raise ResumePageFitError(
            "Could not reduce resume to one page after content retries and "
            "balanced layout compression"
        )
    except Exception as exc:
        _restore_yaml_snapshot(
            yaml_path=yaml_path,
            snapshot_text=last_valid_yaml_snapshot,
        )
        if not attempts or attempts[-1].phase != "layout":
            attempts.append(
                TailorAttemptRecord(
                    phase="layout",
                    attempt_index=0,
                    page_count=current_page_count,
                    success=False,
                    message=f"Layout pass failed: {exc}",
                )
            )
        return TailorRunResult(
            success=False,
            failure_reason=str(exc),
            output_tex_path=invocation.output_tex_path,
            output_pdf_path=invocation.output_pdf_path,
            final_page_count=current_page_count,
            attempts=attempts,
            active_git_branch=active_branch,
        )
