#!/usr/bin/env python3
"""Expose resume-tailor helper functions as deterministic CLI tools.

Purpose:
    Provide a tools-first command surface that pi-coding-agent can call for DB
    context retrieval, YAML IO, rendering, compile, and page-count checks.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from src.agents.resume_tailor_pi.tools import compile_resume_tool
from src.agents.resume_tailor_pi.tools import backup_resume_yaml_tool
from src.agents.resume_tailor_pi.tools import db_get_job_context
from src.agents.resume_tailor_pi.tools import dumps_tool_payload
from src.agents.resume_tailor_pi.tools import get_page_count_tool
from src.agents.resume_tailor_pi.tools import load_resume_yaml_tool
from src.agents.resume_tailor_pi.tools import render_resume_tex_tool
from src.agents.resume_tailor_pi.tools import restore_resume_yaml_tool
from src.agents.resume_tailor_pi.tools import save_resume_yaml_tool
from src.utils.paths import resolve_database_path


def _emit_success(payload: dict[str, Any]) -> int:
    """Print a success payload and return zero exit status.

    Purpose:
        Keep command output shape deterministic for automation clients.
    Args:
        payload: Result payload to include under `result`.
    Output:
        Returns process exit code `0`.
    """

    print(dumps_tool_payload({"ok": True, "result": payload}))
    return 0


def _emit_error(error_message: str) -> int:
    """Print an error payload and return non-zero exit status.

    Purpose:
        Keep failure output machine-readable for upstream orchestrators.
    Args:
        error_message: Error text to include in output payload.
    Output:
        Returns process exit code `1`.
    """

    print(dumps_tool_payload({"ok": False, "error": error_message}))
    return 1


def _parse_content_payload(
    *,
    content_json: str | None,
    content_file: str | None,
) -> dict[str, Any]:
    """Parse save payload from JSON string or JSON file input.

    Purpose:
        Support large YAML save operations without forcing shell-escaped inline
        JSON strings.
    Args:
        content_json: Optional raw JSON string payload.
        content_file: Optional JSON file path payload.
    Output:
        Returns parsed dictionary payload for YAML save operations.
    Raises:
        ValueError: When inputs are missing, both provided, or invalid JSON.
    """

    has_json = content_json is not None
    has_file = content_file is not None
    if has_json == has_file:
        raise ValueError("Provide exactly one of --content-json or --content-file")

    if content_json is not None:
        parsed_payload = json.loads(content_json)
    else:
        assert content_file is not None
        with open(
            Path(content_file).resolve(), "r", encoding="utf-8"
        ) as content_handle:
            parsed_payload = json.load(content_handle)

    if not isinstance(parsed_payload, dict):
        raise ValueError("Resume content payload must be a JSON object")
    return parsed_payload


def build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for resume-tailor tool commands.

    Purpose:
        Centralize command definitions for deterministic tool invocation.
    Args:
        None.
    Output:
        Returns configured top-level argparse parser.
    """

    parser = argparse.ArgumentParser(description="Resume tailor tool commands")
    subparsers = parser.add_subparsers(dest="command", required=True)

    db_parser = subparsers.add_parser(
        "db-get-job-context",
        help="Load one job context row from SQLite by job hash or id",
    )
    db_parser.add_argument(
        "--database-path", type=str, default=str(resolve_database_path())
    )
    db_selector = db_parser.add_mutually_exclusive_group(required=True)
    db_selector.add_argument("--job-hash", type=str)
    db_selector.add_argument("--job-id", type=int)

    load_parser = subparsers.add_parser(
        "load-resume-yaml",
        help="Load canonical resume YAML",
    )
    load_parser.add_argument("--path", type=str, required=True)

    save_parser = subparsers.add_parser(
        "save-resume-yaml",
        help="Validate and save canonical resume YAML",
    )
    save_parser.add_argument("--path", type=str, required=True)
    save_parser.add_argument("--content-json", type=str)
    save_parser.add_argument("--content-file", type=str)

    backup_parser = subparsers.add_parser(
        "backup-resume-yaml",
        help="Create a YAML snapshot used for rollback",
    )
    backup_parser.add_argument("--path", type=str, required=True)
    backup_parser.add_argument("--snapshot-path", type=str, required=True)

    restore_parser = subparsers.add_parser(
        "restore-resume-yaml",
        help="Restore canonical YAML from a snapshot",
    )
    restore_parser.add_argument("--path", type=str, required=True)
    restore_parser.add_argument("--snapshot-path", type=str, required=True)

    render_parser = subparsers.add_parser(
        "render-resume-tex",
        help="Render canonical YAML to LaTeX",
    )
    render_parser.add_argument("--yaml-path", type=str, required=True)
    render_parser.add_argument("--tex-out", type=str, required=True)

    compile_parser = subparsers.add_parser(
        "compile-resume",
        help="Compile LaTeX resume to PDF",
    )
    compile_parser.add_argument("--tex-path", type=str, required=True)
    compile_parser.add_argument("--pdf-out", type=str, required=True)

    page_parser = subparsers.add_parser(
        "get-page-count",
        help="Extract PDF page count",
    )
    page_parser.add_argument("--pdf-path", type=str, required=True)
    page_parser.add_argument("--log-path", type=str)

    return parser


def main() -> int:
    """Execute one resume-tailor tool subcommand.

    Purpose:
        Route CLI subcommands to typed tool functions and emit deterministic
        JSON responses for automation clients.
    Args:
        None.
    Output:
        Returns process exit code `0` on success and `1` on failure.
    """

    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "db-get-job-context":
            job_context = asyncio.run(
                db_get_job_context(
                    database_path=args.database_path,
                    job_hash=args.job_hash,
                    job_id=args.job_id,
                )
            )
            return _emit_success({"job": job_context})

        if args.command == "load-resume-yaml":
            content_payload = load_resume_yaml_tool(path=args.path)
            return _emit_success({"content": content_payload})

        if args.command == "save-resume-yaml":
            parsed_content = _parse_content_payload(
                content_json=args.content_json,
                content_file=args.content_file,
            )
            save_resume_yaml_tool(path=args.path, content=parsed_content)
            return _emit_success({"path": str(Path(args.path).resolve())})

        if args.command == "backup-resume-yaml":
            snapshot_path = backup_resume_yaml_tool(
                path=args.path,
                snapshot_path=args.snapshot_path,
            )
            return _emit_success({"snapshot_path": snapshot_path})

        if args.command == "restore-resume-yaml":
            restored_path = restore_resume_yaml_tool(
                path=args.path,
                snapshot_path=args.snapshot_path,
            )
            return _emit_success({"path": restored_path})

        if args.command == "render-resume-tex":
            tex_path = render_resume_tex_tool(
                yaml_path=args.yaml_path,
                tex_out=args.tex_out,
            )
            return _emit_success({"tex_path": tex_path})

        if args.command == "compile-resume":
            pdf_path = compile_resume_tool(tex_path=args.tex_path, pdf_out=args.pdf_out)
            return _emit_success({"pdf_path": pdf_path})

        if args.command == "get-page-count":
            page_count = get_page_count_tool(
                pdf_path=args.pdf_path,
                log_path=args.log_path,
            )
            return _emit_success({"page_count": page_count})

        return _emit_error(f"Unsupported command: {args.command}")
    except Exception as exc:
        return _emit_error(str(exc))


if __name__ == "__main__":
    sys.exit(main())
