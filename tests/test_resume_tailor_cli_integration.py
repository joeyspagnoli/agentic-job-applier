"""Validate CLI-level resume-tailor tool and runner contracts.

Purpose:
    Exercise subprocess-style CLI usage for resume-tailor commands so path
    forwarding and command-chain behavior stay stable across refactors.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts import run_resume_tailor as run_tailor_script
from src.agents.resume_tailor_pi.schemas import TailorRunResult
from src.database.db_manager import DatabaseManager
from src.models.job_posting import JobPosting

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_resume_tailor_tools_command(
    *,
    args: list[str],
    cwd: Path,
    extra_env: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any]]:
    """Run one `scripts.resume_tailor_tools` command and parse JSON output.

    Purpose:
        Keep subprocess command execution and payload parsing centralized for
        CLI integration tests.
    Args:
        args: Argument tokens passed to `scripts.resume_tailor_tools`.
        cwd: Working directory used for subprocess execution.
        extra_env: Optional environment overrides for the command.
    Output:
        Returns `(returncode, payload_dict)` parsed from command stdout.
    """

    command_environment = dict(os.environ)
    if extra_env is not None:
        command_environment.update(extra_env)

    existing_pythonpath = command_environment.get("PYTHONPATH", "")
    pythonpath_entries = [str(REPO_ROOT)]
    if existing_pythonpath.strip() != "":
        pythonpath_entries.append(existing_pythonpath)
    command_environment["PYTHONPATH"] = os.pathsep.join(pythonpath_entries)

    completed_process = subprocess.run(
        [sys.executable, "-m", "scripts.resume_tailor_tools", *args],
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
        env=command_environment,
    )
    if completed_process.stdout.strip() == "":
        payload = {
            "ok": False,
            "error": (
                f"Command returned empty stdout. stderr:\n{completed_process.stderr}"
            ),
        }
        return completed_process.returncode, payload

    payload = json.loads(completed_process.stdout)
    return completed_process.returncode, payload


async def _insert_job_record(database_path: Path, *, company_name: str) -> str:
    """Insert one job row and return its deduplication hash.

    Purpose:
        Provide deterministic DB fixtures for CLI tests without duplicating
        setup boilerplate in each test body.
    Args:
        database_path: SQLite path where the test job should be inserted.
        company_name: Company name value stored on the inserted row.
    Output:
        Returns the inserted job hash string.
    """

    async with DatabaseManager(str(database_path)) as db_manager:
        await db_manager.create_tables()
        await db_manager.migrate_agent_schema()
        job_posting = JobPosting(
            source="test",
            source_url=f"https://example.com/{company_name.lower()}",
            company=company_name,
            title="Applied AI Engineer",
            description="Ship production AI features",
        )
        await db_manager.insert_job(job_posting.to_db_dict())
    return job_posting.job_hash


def _write_fake_latexmk(binary_path: Path) -> None:
    """Write a deterministic fake `latexmk` executable for compile tests.

    Purpose:
        Remove external TeX dependency from CLI chain tests while still testing
        real subprocess invocation and artifact path wiring.
    Args:
        binary_path: Destination executable path named `latexmk`.
    Output:
        Returns `None` after writing and chmod-ing the fake executable.
    """

    binary_path.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                "set -eu",
                "last_arg=''",
                'for current_arg in "$@"; do',
                '  last_arg="$current_arg"',
                "done",
                'stem="${last_arg%.tex}"',
                "printf '%%PDF-1.4\\n%%EOF\\n' > \"${stem}.pdf\"",
                'printf \'Output written on %s (1 page, 1024 bytes).\\n\' "${stem}.pdf" > "${stem}.log"',
            ]
        ),
        encoding="utf-8",
    )
    binary_path.chmod(binary_path.stat().st_mode | stat.S_IXUSR)


def test_db_get_job_context_honors_database_path(tmp_path: Path) -> None:
    """Verify CLI DB lookup reads from the caller-provided database path.

    Purpose:
        Prevent regressions where `db-get-job-context` accidentally reads the
        default DB path instead of an explicit `--database-path` argument.
    Args:
        tmp_path: Pytest temporary directory fixture.
    Output:
        Returns `None`; test passes when explicit path controls lookup source.
    """

    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    primary_db_path = tmp_path / "primary.db"
    secondary_db_path = tmp_path / "secondary.db"
    primary_job_hash = asyncio.run(
        _insert_job_record(primary_db_path, company_name="PrimaryCo")
    )
    asyncio.run(_insert_job_record(secondary_db_path, company_name="SecondaryCo"))

    success_code, success_payload = _run_resume_tailor_tools_command(
        args=[
            "db-get-job-context",
            "--database-path",
            str(primary_db_path),
            "--job-hash",
            primary_job_hash,
        ],
        cwd=workspace_dir,
    )

    failure_code, failure_payload = _run_resume_tailor_tools_command(
        args=[
            "db-get-job-context",
            "--database-path",
            str(secondary_db_path),
            "--job-hash",
            primary_job_hash,
        ],
        cwd=workspace_dir,
    )

    assert success_code == 0
    assert success_payload["ok"] is True
    assert success_payload["result"]["job"]["company"] == "PrimaryCo"

    assert failure_code == 1
    assert failure_payload["ok"] is False
    assert "No job found" in failure_payload["error"]


def test_resume_tailor_tools_command_chain_supports_snapshot_and_recovery(
    tmp_path: Path,
) -> None:
    """Verify CLI chain supports YAML edits, compile, page checks, and restore.

    Purpose:
        Cover the agent-like command flow end-to-end, including explicit
        snapshot backup/restore recovery commands for flaky edit paths.
    Args:
        tmp_path: Pytest temporary directory fixture.
    Output:
        Returns `None`; test passes when command chain produces expected state.
    """

    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    working_yaml_path = workspace_dir / "resume_content.yaml"
    working_tex_path = workspace_dir / "resume.tex"
    working_pdf_path = workspace_dir / "resume.pdf"
    snapshot_yaml_path = workspace_dir / "resume.snapshot.yaml"
    saved_payload_path = workspace_dir / "save_payload.json"

    shutil.copy2(
        REPO_ROOT / "tests" / "fixtures" / "resume_content_populated.yaml",
        working_yaml_path,
    )

    fake_bin_dir = workspace_dir / "bin"
    fake_bin_dir.mkdir()
    _write_fake_latexmk(fake_bin_dir / "latexmk")
    command_env = {"PATH": f"{fake_bin_dir}:{os.environ['PATH']}"}

    load_code, load_payload = _run_resume_tailor_tools_command(
        args=["load-resume-yaml", "--path", str(working_yaml_path)],
        cwd=workspace_dir,
        extra_env=command_env,
    )
    assert load_code == 0
    assert load_payload["ok"] is True

    resume_payload = load_payload["result"]["content"]
    original_bullet_text = resume_payload["experience"]["listings"][0]["bullets"][0][
        "text"
    ]
    resume_payload["experience"]["listings"][0]["bullets"][0]["text"] = (
        "Delivered ML ranking system improving conversion by 17%."
    )
    saved_payload_path.write_text(json.dumps(resume_payload), encoding="utf-8")

    save_code, save_payload = _run_resume_tailor_tools_command(
        args=[
            "save-resume-yaml",
            "--path",
            str(working_yaml_path),
            "--content-file",
            str(saved_payload_path),
        ],
        cwd=workspace_dir,
        extra_env=command_env,
    )
    assert save_code == 0
    assert save_payload["ok"] is True

    backup_code, backup_payload = _run_resume_tailor_tools_command(
        args=[
            "backup-resume-yaml",
            "--path",
            str(working_yaml_path),
            "--snapshot-path",
            str(snapshot_yaml_path),
        ],
        cwd=workspace_dir,
        extra_env=command_env,
    )
    assert backup_code == 0
    assert backup_payload["ok"] is True
    assert Path(backup_payload["result"]["snapshot_path"]).exists()

    resume_payload["experience"]["listings"][0]["bullets"][0]["text"] = (
        "Temporary bad edit that should be rolled back."
    )
    saved_payload_path.write_text(json.dumps(resume_payload), encoding="utf-8")
    _run_resume_tailor_tools_command(
        args=[
            "save-resume-yaml",
            "--path",
            str(working_yaml_path),
            "--content-file",
            str(saved_payload_path),
        ],
        cwd=workspace_dir,
        extra_env=command_env,
    )

    restore_code, restore_payload = _run_resume_tailor_tools_command(
        args=[
            "restore-resume-yaml",
            "--path",
            str(working_yaml_path),
            "--snapshot-path",
            str(snapshot_yaml_path),
        ],
        cwd=workspace_dir,
        extra_env=command_env,
    )
    assert restore_code == 0
    assert restore_payload["ok"] is True

    verify_code, verify_payload = _run_resume_tailor_tools_command(
        args=["load-resume-yaml", "--path", str(working_yaml_path)],
        cwd=workspace_dir,
        extra_env=command_env,
    )
    assert verify_code == 0
    assert verify_payload["ok"] is True
    restored_bullet_text = verify_payload["result"]["content"]["experience"][
        "listings"
    ][0]["bullets"][0]["text"]
    assert restored_bullet_text != original_bullet_text
    assert restored_bullet_text == (
        "Delivered ML ranking system improving conversion by 17%."
    )

    render_code, render_payload = _run_resume_tailor_tools_command(
        args=[
            "render-resume-tex",
            "--yaml-path",
            str(working_yaml_path),
            "--tex-out",
            str(working_tex_path),
        ],
        cwd=workspace_dir,
        extra_env=command_env,
    )
    assert render_code == 0
    assert render_payload["ok"] is True
    assert Path(render_payload["result"]["tex_path"]).exists()

    compile_code, compile_payload = _run_resume_tailor_tools_command(
        args=[
            "compile-resume",
            "--tex-path",
            str(working_tex_path),
            "--pdf-out",
            str(working_pdf_path),
        ],
        cwd=workspace_dir,
        extra_env=command_env,
    )
    assert compile_code == 0
    assert compile_payload["ok"] is True
    assert Path(compile_payload["result"]["pdf_path"]).exists()

    page_count_code, page_count_payload = _run_resume_tailor_tools_command(
        args=[
            "get-page-count",
            "--pdf-path",
            str(working_pdf_path),
            "--log-path",
            str(working_tex_path.with_suffix(".log")),
        ],
        cwd=workspace_dir,
        extra_env=command_env,
    )
    assert page_count_code == 0
    assert page_count_payload["ok"] is True
    assert page_count_payload["result"]["page_count"] == 1


def test_run_resume_tailor_forwards_database_path_to_invocation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify runner payload preserves explicit database path in invocation.

    Purpose:
        Protect the prompt/runtime contract so non-default DB locations are
        forwarded into `TailorInvocationContract`.
    Args:
        monkeypatch: Pytest fixture used to patch runner dependencies.
        tmp_path: Pytest temporary directory fixture.
    Output:
        Returns `None`; test passes when invocation carries caller DB path.
    """

    captured_invocation: dict[str, str] = {}
    database_path = tmp_path / "custom_jobs.db"
    resume_yaml_path = tmp_path / "resume_content.yaml"
    shutil.copy2(Path("config/resume_content.yaml").resolve(), resume_yaml_path)

    async def fake_db_get_job_context(**_: object) -> dict[str, str]:
        """Return one deterministic job payload for runner preflight.

        Purpose:
            Remove SQLite dependency from CLI wiring test while preserving the
            runner's preflight call pattern.
        Args:
            **_: Ignored keyword arguments passed by the runner.
        Output:
            Returns a minimal fake job payload.
        """

        return {"job_hash": "hash123"}

    def fake_run_resume_tailor_pipeline(*, invocation: Any) -> TailorRunResult:
        """Capture invocation payload and return deterministic success output.

        Purpose:
            Assert argument forwarding behavior without invoking runtime loops.
        Args:
            invocation: Runtime invocation payload from runner main.
        Output:
            Returns a deterministic successful `TailorRunResult`.
        """

        captured_invocation["database_path"] = invocation.database_path
        return TailorRunResult(
            success=True,
            output_tex_path=invocation.output_tex_path,
            output_pdf_path=invocation.output_pdf_path,
            final_page_count=1,
            attempts=[],
            active_git_branch=None,
        )

    monkeypatch.setattr(
        run_tailor_script, "db_get_job_context", fake_db_get_job_context
    )
    monkeypatch.setattr(
        run_tailor_script,
        "run_resume_tailor_pipeline",
        fake_run_resume_tailor_pipeline,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_resume_tailor.py",
            "--job-hash",
            "hash123",
            "--database-path",
            str(database_path),
            "--resume-yaml-path",
            str(resume_yaml_path),
            "--output-dir",
            str(tmp_path / "outputs"),
            "--pi-coding-agent-command",
            "echo test",
        ],
    )

    exit_code = run_tailor_script.main()

    assert exit_code == 0
    assert captured_invocation["database_path"] == str(database_path.resolve())
