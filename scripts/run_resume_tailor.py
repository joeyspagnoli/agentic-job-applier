#!/usr/bin/env python3
"""Run the pi-mono YAML-canonical resume-tailor workflow.

Purpose:
    Provide a scriptable entrypoint that executes the one-page enforced
    tailoring loop using the pi-coding-agent harness and local tools.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from src.agents.resume_tailor_pi import TailorInvocationContract
from src.agents.resume_tailor_pi import run_resume_tailor_pipeline
from src.agents.resume_tailor_pi.tools import db_get_job_context
from src.utils.paths import resolve_database_path
from src.utils.paths import resolve_repo_root


def _build_default_output_paths(
    *,
    output_dir: Path,
    job_hash: str | None,
    job_id: int | None,
) -> tuple[Path, Path]:
    """Build default TeX/PDF output paths for one tailoring run.

    Purpose:
        Keep output artifact locations predictable for operators and tests.
    Args:
        output_dir: Base output directory for tailored artifacts.
        job_hash: Optional deduplication hash selector.
        job_id: Optional numeric job ID selector.
    Output:
        Returns tuple of `(tex_path, pdf_path)` default artifact paths.
    """

    run_token = job_hash if job_hash is not None else f"job_{job_id}"
    run_directory = output_dir / run_token
    tex_path = run_directory / "resume_tailored.tex"
    pdf_path = run_directory / "resume_tailored.pdf"
    return tex_path, pdf_path


def build_parser() -> argparse.ArgumentParser:
    """Build command-line parser for resume-tailor execution.

    Purpose:
        Keep script flags explicit for invocation contract, outputs, and
        optional branch handling.
    Args:
        None.
    Output:
        Returns configured argparse parser.
    """

    parser = argparse.ArgumentParser(description="Run pi-mono resume tailor loop")
    selector_group = parser.add_mutually_exclusive_group(required=True)
    selector_group.add_argument("--job-hash", type=str)
    selector_group.add_argument("--job-id", type=int)

    parser.add_argument(
        "--database-path",
        type=str,
        default=str(resolve_database_path()),
        help="SQLite database path used for job lookup",
    )
    parser.add_argument(
        "--resume-yaml-path",
        type=str,
        default="config/resume_content.yaml",
        help="Canonical resume YAML path",
    )
    parser.add_argument(
        "--render-template-path",
        type=str,
        default="",
        help="Reserved for future renderer templating; unused in V1",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/tailored_resumes",
        help="Base directory for generated resume artifacts",
    )
    parser.add_argument("--output-tex-path", type=str)
    parser.add_argument("--output-pdf-path", type=str)
    parser.add_argument("--page-limit", type=int, default=1)
    parser.add_argument("--content-readjust-attempts", type=int, default=2)
    parser.add_argument("--layout-bounds-profile", type=str, default="balanced")
    parser.add_argument(
        "--pi-coding-agent-command",
        type=str,
        help="Legacy shell command used to invoke pi-coding-agent",
    )
    parser.add_argument(
        "--pi-coding-agent-command-argv-json",
        type=str,
        help=(
            "JSON array of command argv tokens for pi-coding-agent subprocess "
            "invocation"
        ),
    )
    parser.add_argument(
        "--pi-coding-agent-workspace-dir",
        type=str,
        help="Working directory used for pi-coding-agent subprocess execution",
    )
    parser.add_argument(
        "--pi-coding-agent-timeout-seconds",
        type=int,
        default=14_400,
        help="Timeout for each pi-coding-agent subprocess invocation",
    )
    parser.add_argument(
        "--pi-coding-agent-env-allowlist",
        type=str,
        help=(
            "Comma-separated environment variable allowlist for pi-coding-agent "
            "subprocess execution"
        ),
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help=(
            "Model to pass to pi (e.g. openai/openai/gpt-5.1-mini-codex). "
            "Falls back to RESUME_TAILOR_MODEL env var. "
            "Note: if --pi-coding-agent-command-argv-json already includes --model, "
            "this flag will append a second --model token."
        ),
    )
    parser.add_argument(
        "--create-git-branch",
        action="store_true",
        help="Create and checkout a new branch before tailoring edits",
    )
    parser.add_argument(
        "--branch-prefix",
        type=str,
        default="resume-tailor",
        help="Branch prefix used when --create-git-branch is set",
    )
    parser.add_argument(
        "--branch-base-ref",
        type=str,
        help="Explicit base branch/ref used for new branch creation",
    )
    parser.add_argument(
        "--branch-allow-dirty",
        action="store_true",
        help="Allow branch creation even when repository has uncommitted changes",
    )
    return parser


def main() -> int:
    """Execute one resume-tailor run from command-line parameters.

    Purpose:
        Validate job selector and paths, run the one-page loop, and emit
        machine-readable run results for operators and automation.
    Args:
        None.
    Output:
        Returns process exit code `0` on success and `1` on failure.
    """

    parser = build_parser()
    args = parser.parse_args()

    repo_root = resolve_repo_root()
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir

    default_tex_path, default_pdf_path = _build_default_output_paths(
        output_dir=output_dir,
        job_hash=args.job_hash,
        job_id=args.job_id,
    )
    tex_path = Path(args.output_tex_path) if args.output_tex_path else default_tex_path
    pdf_path = Path(args.output_pdf_path) if args.output_pdf_path else default_pdf_path

    if not tex_path.is_absolute():
        tex_path = repo_root / tex_path
    if not pdf_path.is_absolute():
        pdf_path = repo_root / pdf_path

    resume_yaml_path = Path(args.resume_yaml_path)
    if not resume_yaml_path.is_absolute():
        resume_yaml_path = repo_root / resume_yaml_path

    database_path = Path(args.database_path)
    if not database_path.is_absolute():
        database_path = repo_root / database_path

    try:
        asyncio.run(
            db_get_job_context(
                database_path=str(database_path.resolve()),
                job_hash=args.job_hash,
                job_id=args.job_id,
            )
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"Job lookup failed: {exc}"}))
        return 1

    command_argv: list[str] | None = None
    if args.pi_coding_agent_command_argv_json:
        try:
            parsed_command_argv = json.loads(args.pi_coding_agent_command_argv_json)
        except json.JSONDecodeError as exc:
            print(
                json.dumps({"ok": False, "error": f"Invalid command argv JSON: {exc}"})
            )
            return 1
        if not isinstance(parsed_command_argv, list) or not all(
            isinstance(token, str) and token.strip() != ""
            for token in parsed_command_argv
        ):
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": (
                            "--pi-coding-agent-command-argv-json must be a JSON "
                            "array of non-empty strings"
                        ),
                    }
                )
            )
            return 1
        command_argv = [token.strip() for token in parsed_command_argv]

    env_allowlist: list[str] | None = None
    if args.pi_coding_agent_env_allowlist:
        env_allowlist = [
            variable_name.strip()
            for variable_name in args.pi_coding_agent_env_allowlist.split(",")
            if variable_name.strip() != ""
        ]

    model: str | None = args.model or os.environ.get("RESUME_TAILOR_MODEL") or "openai/gpt-5.1-codex-mini"

    invocation_payload: dict[str, object] = {
        "job_ref": {"job_hash": args.job_hash, "job_id": args.job_id},
        "database_path": str(database_path.resolve()),
        "resume_yaml_path": str(resume_yaml_path.resolve()),
        "render_template_path": args.render_template_path,
        "output_tex_path": str(tex_path.resolve()),
        "output_pdf_path": str(pdf_path.resolve()),
        "page_limit": args.page_limit,
        "content_readjust_attempts": args.content_readjust_attempts,
        "layout_bounds_profile": args.layout_bounds_profile,
        "pi_model": model,
        "pi_coding_agent_command": args.pi_coding_agent_command,
        "pi_coding_agent_command_argv": command_argv,
        "pi_coding_agent_workspace_dir": args.pi_coding_agent_workspace_dir,
        "pi_coding_agent_timeout_seconds": args.pi_coding_agent_timeout_seconds,
        "create_git_branch": args.create_git_branch,
        "branch_prefix": args.branch_prefix,
        "branch_base_ref": args.branch_base_ref,
        "branch_allow_dirty": args.branch_allow_dirty,
    }
    if env_allowlist is not None:
        invocation_payload["pi_coding_agent_env_allowlist"] = env_allowlist

    invocation = TailorInvocationContract.model_validate(invocation_payload)

    run_result = run_resume_tailor_pipeline(invocation=invocation)
    print(run_result.model_dump_json(indent=2))
    return 0 if run_result.success else 1


if __name__ == "__main__":
    sys.exit(main())
