"""Tailor-run router (opt-in user-triggered resume tailoring).

Backs the JobsPage `[Tailor resume]` button and the Tailored Resumes
sidebar tab. Exposes:

* `POST /api/jobs/{job_hash}/tailor` — enqueue a BackgroundTask run.
* `GET /api/tailor-runs/{id}` — read the latest state for that row.
* `DELETE /api/tailor-runs/{id}` — soft-delete + best-effort artifact cleanup.

The BackgroundTask handler opens its own `DatabaseManager` so the
pipeline does not share a connection with the originating request — the
pipeline's per-stage writes can outlive the HTTP response.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks
from loguru import logger

from src.agents.resume_tailor import run_tailor_review_pipeline
from src.database._mixins.system_settings import TAILOR_MODE_KEY
from src.database.db_manager import DatabaseManager
from src.utils.cost_tracking import PIPELINE_STAGE_TAILOR, check_budget_before_claim

from api.config import (
    SETTINGS_PROFILE_PATH,
    SETTINGS_RESUME_PATH,
    TAILORED_RESUME_DIR,
)
from api.errors import _raise_api_error
from api.services.tailored_resume import _validate_job_hash

router = APIRouter(prefix="/api", tags=["tailor-runs"])

AUTONOMOUS_MODE = "autonomous"


async def _run_pipeline_background(
    *,
    db_path: str,
    tailor_run_id: int,
    job_hash: str,
    output_dir: Path,
) -> None:
    """Execute the resume-tailor pipeline inside a FastAPI BackgroundTask.

    Purpose:
        Run the pipeline on the request's lifecycle without blocking the
        HTTP response. Each invocation opens its own database connection
        because BackgroundTasks outlive request-scoped resources.
    Args:
        db_path: SQLite database path.
        tailor_run_id: Primary key of the PENDING tailor_runs row.
        job_hash: Stable job identifier.
        output_dir: Per-run artifact directory.
    Output:
        Returns `None`. Pipeline errors are caught and logged so they
        cannot escape the BackgroundTask runner.
    """

    try:
        async with DatabaseManager(db_path) as db:
            await db.create_tables()
            await run_tailor_review_pipeline(
                db=db,
                tailor_run_id=tailor_run_id,
                job_hash=job_hash,
                base_resume_yaml_path=SETTINGS_RESUME_PATH,
                candidate_profile_yaml_path=SETTINGS_PROFILE_PATH,
                output_dir=output_dir,
            )
    except Exception as exc:
        logger.exception(
            "BackgroundTask tailor pipeline failed: run_id={} job_hash={} error={}",
            tailor_run_id,
            job_hash,
            exc,
        )


def _serialize_tailor_run_row(row: dict[str, Any]) -> dict[str, Any]:
    """Render one tailor_runs row into the dashboard's JSON payload.

    Purpose:
        Keep the response shape consistent across the POST, GET, and
        `/api/jobs?has_tailor_run=1` endpoints. The `pdf_url` field is
        intentionally only set on SUCCESS; clients fall back to the
        existing `/api/jobs/{hash}/resume` download endpoint.
    Args:
        row: Raw `tailor_runs` row mapping.
    Output:
        Returns a JSON-serializable dict.
    """

    job_hash = str(row.get("job_hash") or "")
    pdf_url: Optional[str] = None
    if str(row.get("status") or "") == "SUCCESS" and job_hash:
        pdf_url = f"/api/jobs/{job_hash}/resume"

    return {
        "id": int(row["id"]),
        "job_hash": job_hash,
        "status": str(row.get("status") or ""),
        "page_count": row.get("page_count"),
        "error": row.get("error"),
        "started_at": str(row.get("started_at") or ""),
        "completed_at": row.get("completed_at"),
        "deleted_at": row.get("deleted_at"),
        "pdf_url": pdf_url,
    }


@router.post("/jobs/{job_hash}/tailor", status_code=202)
async def enqueue_tailor_run(
    job_hash: str,
    background_tasks: BackgroundTasks,
) -> dict[str, object]:
    """Enqueue a user-triggered tailor pipeline run.

    Purpose:
        Insert a PENDING tailor_runs row and schedule the resume-tailor pipeline
        as a FastAPI BackgroundTask. Rejects with 409 when the user has
        opted out of manual runs (`autonomous` mode) or when a non-deleted
        active row already exists for this job.
    Args:
        job_hash: Stable job identifier from the URL.
        background_tasks: Injected by FastAPI; schedules the pipeline.
    Output:
        Returns `{ok, tailor_run_id, status, job_hash}` on enqueue.
    Raises:
        HTTPException: 404 when the job does not exist; 409 when mode
            disallows manual runs or an active run already exists; 422
            when the job hash is malformed.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    validated_hash = _validate_job_hash(job_hash)
    db_path = str(_main.resolve_database_path())

    async with DatabaseManager(db_path) as db:
        await db.create_tables()

        job_row = await db.get_job_by_hash(validated_hash)
        if job_row is None:
            _raise_api_error(
                status_code=404,
                code="JOB_NOT_FOUND",
                message="Job not found for the supplied hash.",
                details={"job_hash": validated_hash},
            )

        mode = await db.get_automation_mode(TAILOR_MODE_KEY)
        if mode == AUTONOMOUS_MODE:
            _raise_api_error(
                status_code=409,
                code="MODE_AUTONOMOUS",
                message=(
                    "Manual tailor runs are disabled while automation mode is "
                    "set to autonomous."
                ),
                details={"tailor_mode": mode},
            )

        if not await check_budget_before_claim(db=db, stage=PIPELINE_STAGE_TAILOR):
            _raise_api_error(
                status_code=409,
                code="BUDGET_EXCEEDED",
                message=(
                    "Monthly budget exceeded — raise the budget in Settings "
                    "before triggering more tailor runs."
                ),
                details={"stage": PIPELINE_STAGE_TAILOR},
            )

        claim_result = await db.insert_user_triggered_tailor_run(
            job_hash=validated_hash
        )
        if claim_result is None:
            _raise_api_error(
                status_code=409,
                code="RUN_ALREADY_EXISTS",
                message=(
                    "An active tailor run already exists for this job. "
                    "Delete it before re-tailoring."
                ),
                details={"job_hash": validated_hash},
            )

        tailor_run_id = int(claim_result["id"])

    run_output_dir = TAILORED_RESUME_DIR / validated_hash
    background_tasks.add_task(
        _run_pipeline_background,
        db_path=db_path,
        tailor_run_id=tailor_run_id,
        job_hash=validated_hash,
        output_dir=run_output_dir,
    )

    return {
        "ok": True,
        "tailor_run_id": tailor_run_id,
        "status": "PENDING",
        "job_hash": validated_hash,
    }


@router.get("/tailor-runs/{run_id}")
async def get_tailor_run(run_id: int) -> dict[str, object]:
    """Return the current state of one tailor run by primary key.

    Purpose:
        Drive the JobsPage row's polling loop while a tailor run is
        RUNNING and serve the final state on completion.
    Args:
        run_id: Primary key of the target tailor_runs row.
    Output:
        Returns `{ok: True, tailor_run: {...}}`.
    Raises:
        HTTPException: 404 when no row matches.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    db_path = str(_main.resolve_database_path())
    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        row = await db.get_tailor_run(run_id)

    if row is None:
        _raise_api_error(
            status_code=404,
            code="TAILOR_RUN_NOT_FOUND",
            message="Tailor run not found.",
            details={"run_id": run_id},
        )

    return {"ok": True, "tailor_run": _serialize_tailor_run_row(row)}


@router.delete("/tailor-runs/{run_id}", status_code=204)
async def delete_tailor_run(run_id: int) -> None:
    """Soft-delete one tailor run and best-effort remove the artifacts.

    Purpose:
        Free the per-job single-slot constraint so the user can re-tailor.
        Soft-delete preserves the row for audit; the on-disk artifact
        directory is removed when present.
    Args:
        run_id: Primary key of the tailor_runs row to soft-delete.
    Output:
        Returns `None` (204 No Content).
    Raises:
        HTTPException: 404 when the row does not exist or was already
            soft-deleted.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    db_path = str(_main.resolve_database_path())
    async with DatabaseManager(db_path) as db:
        await db.create_tables()

        row = await db.get_tailor_run(run_id)
        if row is None:
            _raise_api_error(
                status_code=404,
                code="TAILOR_RUN_NOT_FOUND",
                message="Tailor run not found.",
                details={"run_id": run_id},
            )
        if row.get("deleted_at") is not None:
            _raise_api_error(
                status_code=404,
                code="TAILOR_RUN_ALREADY_DELETED",
                message="Tailor run was already deleted.",
                details={"run_id": run_id},
            )

        await db.soft_delete_tailor_run(run_id)

        # Best-effort artifact cleanup — never raise from the cleanup path.
        artifact_pdf = row.get("artifact_pdf_path")
        if isinstance(artifact_pdf, str) and artifact_pdf:
            artifact_dir = Path(artifact_pdf).parent
            try:
                if artifact_dir.exists():
                    shutil.rmtree(artifact_dir, ignore_errors=True)
            except OSError as exc:
                logger.warning(
                    "Tailor artifact cleanup failed for run_id={}: {}", run_id, exc
                )

    return None
