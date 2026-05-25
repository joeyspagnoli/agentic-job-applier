"""Apply-run router (manual user-triggered browser application).

Backs the dashboard `[Apply]` button. Exposes:

* `POST /api/jobs/{job_hash}/apply` — enqueue a browser-apply run.
* `GET /api/apply-runs/{id}` — read the latest state for that row.
* `DELETE /api/apply-runs/{id}` — soft-delete + free the in-flight slot.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from loguru import logger

from src.database._mixins.apply import ApplyRunInFlightError
from src.database._mixins.apply import NoReviewRunError
from src.database.db_manager import DatabaseManager

from api.errors import _raise_api_error
from api.services.tailored_resume import _validate_job_hash

router = APIRouter(prefix="/api", tags=["apply-runs"])


def _serialize_apply_run_row(row: dict[str, Any]) -> dict[str, Any]:
    """Render one apply_runs row into the dashboard's JSON payload.

    Purpose:
        Keep the response shape consistent across the POST and GET
        endpoints. Only fields relevant to the dashboard polling loop
        and status display are included.
    Args:
        row: Raw `apply_runs` row mapping.
    Output:
        Returns a JSON-serializable dict.
    """

    return {
        "id": int(row["id"]),
        "job_hash": str(row.get("job_hash") or ""),
        "review_run_id": int(row["review_run_id"]),
        "status": str(row.get("status") or ""),
        "outcome": row.get("outcome"),
        "error": row.get("error"),
        "ats_platform": row.get("ats_platform"),
        "page_url": row.get("page_url"),
        "confidence_score": row.get("confidence_score"),
        "started_at": str(row.get("started_at") or ""),
        "completed_at": row.get("completed_at"),
        "deleted_at": row.get("deleted_at"),
    }


@router.post("/jobs/{job_hash}/apply", status_code=200)
async def enqueue_apply_run(job_hash: str) -> dict[str, object]:
    """Enqueue a user-triggered browser-apply run.

    Purpose:
        Insert a PENDING apply_runs row tied to the most recent SUCCESS
        review run for the job. Rejects with 409 when a non-deleted
        PENDING apply run already exists for this job, and with 422 when
        no eligible review run has completed.
    Args:
        job_hash: Stable job identifier from the URL.
    Output:
        Returns `{run_id, status}` on enqueue.
    Raises:
        HTTPException: 400 when the job hash is malformed; 409 when a run
            is already in flight; 422 when no review run exists yet.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    validated_hash = _validate_job_hash(job_hash)
    db_path = str(_main.resolve_database_path())

    async with DatabaseManager(db_path) as db:
        await db.create_tables()

        try:
            result = await db.enqueue_apply_run_for_job(job_hash=validated_hash)
        except ApplyRunInFlightError as exc:
            logger.info(
                "Apply run already in flight: job_hash={} run_id={} status={}",
                validated_hash,
                exc.run_id,
                exc.status,
            )
            _raise_api_error(
                status_code=409,
                code="APPLY_RUN_IN_FLIGHT",
                message="An apply run is already in flight for this job.",
                details={"run_id": exc.run_id, "status": exc.status},
            )
        except NoReviewRunError:
            _raise_api_error(
                status_code=422,
                code="NO_REVIEW_RUN",
                message="Job has no completed review yet.",
                details={"job_hash": validated_hash},
            )

    return {"run_id": int(result["id"]), "status": str(result["status"])}


@router.get("/apply-runs/{run_id}")
async def get_apply_run(run_id: int) -> dict[str, object]:
    """Return the current state of one apply run by primary key.

    Purpose:
        Drive the dashboard polling loop while a browser-apply run is
        PENDING and serve the final state on completion.
    Args:
        run_id: Primary key of the target apply_runs row.
    Output:
        Returns `{ok: True, apply_run: {...}}`.
    Raises:
        HTTPException: 404 when no non-deleted row matches.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    db_path = str(_main.resolve_database_path())
    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        row = await db.get_apply_run(run_id)

    if row is None:
        _raise_api_error(
            status_code=404,
            code="APPLY_RUN_NOT_FOUND",
            message="Apply run not found.",
            details={"run_id": run_id},
        )

    return {"ok": True, "apply_run": _serialize_apply_run_row(row)}


@router.delete("/apply-runs/{run_id}", status_code=204)
async def delete_apply_run(run_id: int) -> None:
    """Soft-delete one apply run to free the per-job in-flight slot.

    Purpose:
        Allow re-enqueueing after a failure without losing the row for
        audit. Mirrors the tailor-runs soft-delete semantics exactly.
    Args:
        run_id: Primary key of the apply_runs row to soft-delete.
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

        # Use get_apply_run which already filters out deleted rows.
        row = await db.get_apply_run(run_id)
        if row is None:
            # Distinguish never-existed from already-deleted by checking
            # the raw row without the deleted_at filter.
            conn = db._require_conn()
            raw_cursor = await conn.execute(
                "SELECT deleted_at FROM apply_runs WHERE id = ?",
                (run_id,),
            )
            raw_row = await raw_cursor.fetchone()
            if raw_row is not None and raw_row["deleted_at"] is not None:
                _raise_api_error(
                    status_code=404,
                    code="APPLY_RUN_ALREADY_DELETED",
                    message="Apply run was already deleted.",
                    details={"run_id": run_id},
                )
            _raise_api_error(
                status_code=404,
                code="APPLY_RUN_NOT_FOUND",
                message="Apply run not found.",
                details={"run_id": run_id},
            )

        await db.soft_delete_apply_run(run_id)

    return None
