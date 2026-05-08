"""Failures router (unified stage failures + retry)."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from datetime import timedelta

from fastapi import APIRouter
from fastapi import Query

from src.database.db_manager import DatabaseManager

from api.config import DEFAULT_PAGE_SIZE
from api.config import MAX_PAGE_SIZE
from api.errors import _raise_api_error
from api.services.failure_records import collect_failure_rows
from api.services.failure_records import serialize_failure_record as _serialize_failure_record
from api.services.sources import _source_label
from api.services.system_scripts import _load_positive_int_env

router = APIRouter(prefix="/api/failures", tags=["failures"])


@router.get("")
async def get_failures(
    search: str = Query(default=""),
    stage: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> dict[str, object]:
    """Return unified failures feed across gate/tailor/review/apply stages.

    Purpose:
        Replace mock failures data with actionable stage failure records and
        summary stats needed by the failures page.
    Args:
        search: Optional text filter across company/title/error/stage fields.
        stage: Optional exact stage filter.
        status: Optional exact retry-status filter.
        page: 1-based page number.
        page_size: Number of rows per page.
    Output:
        Returns summary + paginated failures list.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    max_gate_retries = _load_positive_int_env("AGENT_MAX_RETRIES", 3)
    max_tailor_retries = _load_positive_int_env("TAILOR_MAX_RETRIES", 2)
    max_review_retries = _load_positive_int_env("REVIEW_MAX_RETRIES", 2)
    max_apply_retries = _load_positive_int_env("APPLY_MAX_RETRIES", 2)

    db_path = str(_main.resolve_database_path())
    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        await db.migrate_agent_schema()
        await db.migrate_tailor_schema()
        await db.migrate_review_schema()
        await db.migrate_apply_schema()

        gate_rows, tailor_rows, review_rows, apply_rows = await collect_failure_rows(db)

    records: list[dict[str, object]] = []

    for row in gate_rows:
        records.append(
            _serialize_failure_record(
                failure_id=f"GATE:{row['job_hash']}",
                stage="GATE",
                company=str(row["company"]),
                position=str(row["title"]),
                error_text=str(row["agent_error"] or "Unknown gate failure."),
                attempts=int(row["agent_retry_count"] or 0),
                max_attempts=max_gate_retries,
                status="EXHAUSTED",
                platform=_source_label(str(row["source"])),
                job_posting_url=str(row["source_url"]),
                event_time=str(row["agent_failed_at"]),
            )
        )

    for row in tailor_rows:
        records.append(
            _serialize_failure_record(
                failure_id=f"TAILOR:{row['id']}",
                stage="TAILORING",
                company=str(row["company"]),
                position=str(row["title"]),
                error_text=str(row["error"] or "Unknown tailor failure."),
                attempts=int(row["attempts"] or 0),
                max_attempts=max_tailor_retries,
                status="RETRYING" if row["next_retry_at"] is not None else "EXHAUSTED",
                platform=_source_label(str(row["source"])),
                job_posting_url=str(row["source_url"]),
                event_time=str(row["event_time"]),
            )
        )

    for row in review_rows:
        records.append(
            _serialize_failure_record(
                failure_id=f"REVIEW:{row['id']}",
                stage="REVIEW",
                company=str(row["company"]),
                position=str(row["title"]),
                error_text=str(row["error"] or "Unknown review failure."),
                attempts=int(row["attempts"] or 0),
                max_attempts=max_review_retries,
                status="RETRYING" if row["next_retry_at"] is not None else "EXHAUSTED",
                platform=_source_label(str(row["source"])),
                job_posting_url=str(row["source_url"]),
                event_time=str(row["event_time"]),
            )
        )

    for row in apply_rows:
        records.append(
            _serialize_failure_record(
                failure_id=f"APPLY:{row['id']}",
                stage="APPLY",
                company=str(row["company"]),
                position=str(row["title"]),
                error_text=str(row["error"] or "Unknown apply failure."),
                attempts=int(row["attempts"] or 0),
                max_attempts=max_apply_retries,
                status="RETRYING" if row["next_retry_at"] is not None else "EXHAUSTED",
                platform=_source_label(str(row["source"])),
                job_posting_url=str(row["source_url"]),
                event_time=str(row["event_time"]),
            )
        )

    records.sort(key=lambda item: str(item["time"]), reverse=True)

    filtered_records = records
    if stage is not None and stage.strip() != "":
        normalized_stage = stage.strip().upper()
        filtered_records = [
            item
            for item in filtered_records
            if str(item["stage"]).upper() == normalized_stage
        ]
    if status is not None and status.strip() != "":
        normalized_status = status.strip().upper()
        filtered_records = [
            item
            for item in filtered_records
            if str(item["status"]).upper() == normalized_status
        ]
    if search.strip():
        search_value = search.strip().lower()
        filtered_records = [
            item
            for item in filtered_records
            if search_value in str(item["company"]).lower()
            or search_value in str(item["position"]).lower()
            or search_value in str(item["error_code"]).lower()
            or search_value in str(item["stage"]).lower()
        ]

    total_items = len(filtered_records)
    offset = (page - 1) * page_size
    page_items = filtered_records[offset : offset + page_size]
    total_pages = max((total_items + page_size - 1) // page_size, 1)

    stage_counts: dict[str, int] = {}
    for item in records:
        stage_label = str(item["stage"])
        stage_counts[stage_label] = stage_counts.get(stage_label, 0) + 1

    most_failing_stage = "NONE"
    most_failing_count = 0
    if stage_counts:
        most_failing_stage, most_failing_count = max(
            stage_counts.items(),
            key=lambda item: item[1],
        )

    last_24h_cutoff = datetime.now(tz=UTC) - timedelta(hours=24)
    last_24h_count = 0
    for item in records:
        try:
            item_time = datetime.fromisoformat(str(item["time"]).replace(" ", "T"))
        except ValueError:
            continue
        if item_time.tzinfo is None:
            item_time = item_time.replace(tzinfo=UTC)
        if item_time >= last_24h_cutoff:
            last_24h_count += 1

    exhausted_count = len([item for item in records if item["status"] == "EXHAUSTED"])
    retry_success_rate = (
        0.0
        if len(records) == 0
        else max(0.0, ((len(records) - exhausted_count) / len(records)) * 100.0)
    )

    return {
        "ok": True,
        "summary": {
            "total_failures": len(records),
            "last_24_hours": last_24h_count,
            "most_failing_stage": {
                "stage": most_failing_stage,
                "count": most_failing_count,
            },
            "retry_success_rate_pct": retry_success_rate,
        },
        "page": page,
        "page_size": page_size,
        "total_items": total_items,
        "total_pages": total_pages,
        "items": page_items,
    }


@router.post("/{failure_id}/retry")
async def retry_failure(failure_id: str) -> dict[str, object]:
    """Requeue one failed stage record based on its stage-qualified ID.

    Purpose:
        Implement stage-specific retry semantics requested by the dashboard,
        including gate/tailor/review/apply reset behavior.
    Args:
        failure_id: Stage-qualified identifier in `<STAGE>:<id>` format.
    Output:
        Returns canonical mutation success payload.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    if ":" not in failure_id:
        _raise_api_error(
            status_code=400,
            code="INVALID_FAILURE_ID",
            message="Failure ID must use '<STAGE>:<id>' format.",
        )

    stage_key, stage_value = failure_id.split(":", maxsplit=1)
    stage_key = stage_key.strip().upper()

    db_path = str(_main.resolve_database_path())
    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        await db.migrate_agent_schema()
        await db.migrate_tailor_schema()
        await db.migrate_review_schema()
        await db.migrate_apply_schema()

        assert db.conn is not None
        conn = db.conn

        if stage_key == "GATE":
            await db.reset_agent_failure_state(stage_value)
            return {"ok": True, "failure_id": failure_id, "requeued": True}

        if stage_key == "TAILOR":
            cursor = await conn.execute(
                "SELECT job_hash FROM tailor_runs WHERE id = ?",
                (int(stage_value),),
            )
            row = await cursor.fetchone()
            if row is None:
                _raise_api_error(
                    status_code=404,
                    code="FAILURE_NOT_FOUND",
                    message="Tailor failure record was not found.",
                )
            await db.reset_tailor_failure_state(job_hash=str(row["job_hash"]))
            return {"ok": True, "failure_id": failure_id, "requeued": True}

        if stage_key == "REVIEW":
            cursor = await conn.execute(
                "SELECT job_hash FROM review_runs WHERE id = ?",
                (int(stage_value),),
            )
            row = await cursor.fetchone()
            if row is None:
                _raise_api_error(
                    status_code=404,
                    code="FAILURE_NOT_FOUND",
                    message="Review failure record was not found.",
                )
            deleted_count = await db.reset_review_failure_state(
                job_hash=str(row["job_hash"])
            )
            return {
                "ok": True,
                "failure_id": failure_id,
                "requeued": deleted_count > 0,
                "deleted_failures": deleted_count,
            }

        if stage_key == "APPLY":
            cursor = await conn.execute(
                "SELECT job_hash FROM apply_runs WHERE id = ?",
                (int(stage_value),),
            )
            row = await cursor.fetchone()
            if row is None:
                _raise_api_error(
                    status_code=404,
                    code="FAILURE_NOT_FOUND",
                    message="Apply failure record was not found.",
                )
            deleted_count = await db.reset_apply_failure_state(
                job_hash=str(row["job_hash"])
            )
            return {
                "ok": True,
                "failure_id": failure_id,
                "requeued": deleted_count > 0,
                "deleted_failures": deleted_count,
            }

    _raise_api_error(
        status_code=409,
        code="NON_RETRIABLE_FAILURE",
        message="This failure stage is not retriable.",
    )
    raise AssertionError("Unreachable: _raise_api_error always raises HTTPException.")
