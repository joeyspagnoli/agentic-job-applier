"""Tool functions for pi-mono resume-tailor workflows.

Purpose:
    Expose deterministic tool primitives for DB context retrieval, YAML IO,
    rendering, compilation, and page-count checks.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from src.database.db_manager import DatabaseManager

from src.agents.resume_tailor_adk.compiler import compile_resume_tex
from src.agents.resume_tailor_adk.compiler import get_pdf_page_count
from src.agents.resume_tailor_adk.renderer import render_resume_yaml_to_tex
from src.agents.resume_tailor_adk.yaml_io import load_resume_yaml_dict
from src.agents.resume_tailor_adk.yaml_io import save_resume_yaml_dict


async def db_get_job_context(
    *,
    database_path: str | Path,
    job_hash: str | None = None,
    job_id: int | None = None,
) -> dict[str, Any]:
    """Fetch one job context record directly from SQLite.

    Purpose:
        Provide the primary tool path for the tailor agent to retrieve job
        context without injecting full job text into prompts upfront.
    Args:
        database_path: SQLite database path for this repository.
        job_hash: Optional deduplication hash selector.
        job_id: Optional numeric row ID selector.
    Output:
        Returns the selected job context mapping.
    Raises:
        ValueError: When selector fields are invalid.
        RuntimeError: When the selected job does not exist.
    """

    async with DatabaseManager(str(database_path)) as db:
        await db.create_tables()
        await db.migrate_agent_schema()
        context_row = await db.get_resume_tailor_job_context(
            job_hash=job_hash,
            job_id=job_id,
        )

    if context_row is None:
        if job_hash is not None:
            raise RuntimeError(f"No job found for job_hash={job_hash}")
        raise RuntimeError(f"No job found for job_id={job_id}")

    return context_row


def load_resume_yaml_tool(*, path: str | Path) -> dict[str, Any]:
    """Load canonical resume YAML for tool consumers.

    Purpose:
        Provide a JSON-serializable view of canonical YAML content for
        non-Python tool consumers.
    Args:
        path: Filesystem path to canonical resume YAML.
    Output:
        Returns the validated resume payload as a dictionary.
    """

    return load_resume_yaml_dict(path)


def save_resume_yaml_tool(*, path: str | Path, content: dict[str, Any]) -> None:
    """Validate and save canonical resume YAML from tool consumers.

    Purpose:
        Provide a safe write path for model/tool workflows that submit full
        resume payloads as JSON objects.
    Args:
        path: Destination YAML path.
        content: Canonical resume payload mapping.
    Output:
        Returns `None` after successful validation and save.
    """

    save_resume_yaml_dict(path=path, payload=content)


def backup_resume_yaml_tool(*, path: str | Path, snapshot_path: str | Path) -> str:
    """Copy canonical resume YAML to a snapshot path for rollback recovery.

    Purpose:
        Create an explicit on-disk checkpoint the agent can restore from when
        a direct edit or tool save path introduces invalid resume content.
    Args:
        path: Source canonical resume YAML path.
        snapshot_path: Destination snapshot YAML path.
    Output:
        Returns absolute snapshot path string.
    """

    source_path = Path(path).resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"Resume YAML file not found: {source_path}")

    destination_path = Path(snapshot_path).resolve()
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination_path)
    return str(destination_path)


def restore_resume_yaml_tool(*, path: str | Path, snapshot_path: str | Path) -> str:
    """Restore canonical resume YAML from a previously created snapshot file.

    Purpose:
        Provide a deterministic rollback operation the agent can execute after
        malformed edits, lock violations, or compile failures.
    Args:
        path: Destination canonical resume YAML path to restore.
        snapshot_path: Snapshot YAML path used as restore source.
    Output:
        Returns absolute restored destination path string.
    Raises:
        FileNotFoundError: When the provided snapshot file does not exist.
    """

    resolved_snapshot_path = Path(snapshot_path).resolve()
    if not resolved_snapshot_path.exists():
        raise FileNotFoundError(
            f"Resume YAML snapshot file not found: {resolved_snapshot_path}"
        )

    snapshot_content = load_resume_yaml_dict(resolved_snapshot_path)
    save_resume_yaml_dict(path=path, payload=snapshot_content)
    return str(Path(path).resolve())


def render_resume_tex_tool(*, yaml_path: str | Path, tex_out: str | Path) -> str:
    """Render canonical YAML to a LaTeX artifact path.

    Purpose:
        Expose deterministic rendering behavior as a tool-callable function.
    Args:
        yaml_path: Source canonical YAML path.
        tex_out: Destination `.tex` output path.
    Output:
        Returns absolute `.tex` path string for downstream tool chaining.
    """

    rendered_path = render_resume_yaml_to_tex(
        yaml_path=yaml_path,
        tex_output_path=tex_out,
    )
    return str(rendered_path)


def compile_resume_tool(*, tex_path: str | Path, pdf_out: str | Path) -> str:
    """Compile one LaTeX resume into a PDF artifact path.

    Purpose:
        Expose deterministic `latexmk` compile behavior as a tool-callable
        function for runtime loops and agent instructions.
    Args:
        tex_path: Source `.tex` path to compile.
        pdf_out: Destination `.pdf` path.
    Output:
        Returns absolute `.pdf` path string.
    """

    compiled_pdf_path = compile_resume_tex(
        tex_path=tex_path,
        pdf_output_path=pdf_out,
    )
    return str(compiled_pdf_path)


def get_page_count_tool(
    *, pdf_path: str | Path, log_path: str | Path | None = None
) -> int:
    """Get PDF page count with `pdfinfo` primary and log fallback.

    Purpose:
        Provide one-page checks as a tool-callable primitive for runtime loops
        and external agent orchestration.
    Args:
        pdf_path: PDF artifact path to inspect.
        log_path: Optional `.log` path for fallback page-count parsing.
    Output:
        Returns the parsed page count integer.
    """

    return get_pdf_page_count(pdf_path=pdf_path, log_path=log_path)


def dumps_tool_payload(payload: dict[str, Any]) -> str:
    """Serialize tool payload dictionaries as deterministic JSON strings.

    Purpose:
        Keep CLI outputs stable and machine-readable across tool subcommands.
    Args:
        payload: Tool payload mapping to serialize.
    Output:
        Returns compact JSON text with stable key ordering.
    """

    return json.dumps(payload, sort_keys=True)
