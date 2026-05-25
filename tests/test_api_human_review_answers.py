"""Contract tests for the human-review answers endpoint and queue shape.

Covers Bug B fixes:

* ``GET /api/human-review`` prefers the finisher's
  ``deferred_questions_json`` over the older ``unresolved_fields_json``
  when both are present, so reviewers see the human-readable labels
  the finisher captured (e.g. ``"Gender"``) instead of the legacy
  ``"Unresolved field"`` placeholder.
* The legacy fallback never surfaces ``"Unresolved field"``; it now
  degrades to the ``field_id`` and finally to ``"(no label)"``.
* ``POST /api/human-review/{id}/answers`` persists the reviewer-typed
  payload to ``apply_handoffs.user_answers_json`` and a subsequent
  GET returns it on the row.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import main as api_main
from src.database.db_manager import DatabaseManager
from src.models.job_posting import JobPosting


async def _seed_one_handoff(
    db_path: Path,
    *,
    deferred_questions_json: str | None,
    unresolved_fields_json: str | None,
) -> int:
    """Seed one job + review + apply + handoff row; return the handoff id.

    Purpose:
        Build a deterministic fixture row the API test can read back.
        Inserts directly via SQL where possible to avoid pulling in
        the full apply-runner stack.
    Args:
        db_path: Temp SQLite database path.
        deferred_questions_json: Pre-serialized JSON for the
            finisher-deferred questions column.
        unresolved_fields_json: Pre-serialized JSON for the legacy
            unresolved-fields column.
    Returns:
        Primary key of the inserted ``apply_handoffs`` row.
    """

    async with DatabaseManager(str(db_path)) as db:
        await db.create_tables()
        await db.migrate_apply_schema()

        job = JobPosting(
            source="greenhouse_test",
            source_url="https://example.com/jobs/test",
            company="Cloudflare",
            title="ML Engineer Intern",
            description="A test posting.",
        )
        job_hash = job.job_hash
        await db.insert_job(job.to_db_dict())

        assert db.conn is not None
        conn = db.conn
        # Seed a tailor_run + review_runs + apply_runs chain so the
        # NOT NULL constraints (review_runs.tailor_run_id,
        # apply_runs.review_run_id) are satisfied.
        await conn.execute(
            """
            INSERT INTO tailor_runs (job_hash, status, started_at)
            VALUES (?, 'SUCCESS', CURRENT_TIMESTAMP)
            """,
            (job_hash,),
        )
        tailor_cursor = await conn.execute("SELECT last_insert_rowid() AS id")
        tailor_row = await tailor_cursor.fetchone()
        assert tailor_row is not None
        tailor_run_id = int(tailor_row["id"])

        await conn.execute(
            """
            INSERT INTO review_runs (job_hash, tailor_run_id, status, verdict, started_at)
            VALUES (?, ?, 'SUCCESS', 'TAILORED', CURRENT_TIMESTAMP)
            """,
            (job_hash, tailor_run_id),
        )
        review_cursor = await conn.execute(
            "SELECT last_insert_rowid() AS id"
        )
        review_row = await review_cursor.fetchone()
        assert review_row is not None
        review_run_id = int(review_row["id"])

        await conn.execute(
            """
            INSERT INTO apply_runs (job_hash, review_run_id, status, claim_token, started_at)
            VALUES (?, ?, 'SUCCESS', 'tok', CURRENT_TIMESTAMP)
            """,
            (job_hash, review_run_id),
        )
        apply_cursor = await conn.execute("SELECT last_insert_rowid() AS id")
        apply_row = await apply_cursor.fetchone()
        assert apply_row is not None
        apply_run_id = int(apply_row["id"])
        await conn.commit()

        await db.record_apply_handoff(
            apply_run_id=apply_run_id,
            job_hash=job_hash,
            review_run_id=review_run_id,
            apply_outcome="NEEDS_REVIEW",
            resume_source="TAILORED",
            resume_pdf_path="/tmp/resume.pdf",
            confidence_score=0.42,
            confidence_report_json=None,
            unresolved_fields_json=unresolved_fields_json,
            screenshot_path=None,
            dom_snapshot_path=None,
            ats_platform="greenhouse",
            page_url="https://example.com",
            deferred_questions_json=deferred_questions_json,
            finisher_diagnostics_json=None,
        )

        cursor = await db.conn.execute(
            "SELECT id FROM apply_handoffs WHERE apply_run_id = ?",
            (apply_run_id,),
        )
        row = await cursor.fetchone()
        assert row is not None
        return int(row["id"])


@pytest.fixture
def human_review_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TestClient, Path, Path]:
    """Build an isolated TestClient pointed at a fresh temp SQLite file
    and a redirected answer-cache YAML path.

    Returns:
        Tuple of (client, database_path, answer_cache_path). The cache
        file is rewritten under ``tmp_path`` so the POST /answers
        endpoint never touches ``data/answer_cache.yaml`` in the
        working tree.
    """

    db_path = tmp_path / "jobs.db"
    monkeypatch.setattr(api_main, "resolve_database_path", lambda: db_path)

    from api.routers import human_review as _hr_router  # noqa: PLC0415

    cache_path = tmp_path / "answer_cache.yaml"
    monkeypatch.setattr(
        _hr_router, "_resolve_answer_cache_path", lambda: cache_path
    )
    return TestClient(api_main.app), db_path, cache_path


def test_get_human_review_prefers_deferred_questions_over_unresolved_fields(
    human_review_client: tuple[TestClient, Path, Path],
) -> None:
    """When both JSON blobs are populated, the API surfaces the finisher's
    deferred questions (which carry real labels) and ignores the legacy
    placeholder list (which carries only nulls).
    """

    client, db_path, _cache_path = human_review_client

    deferred = json.dumps(
        [
            {
                "field_id": "e368",
                "label": "Gender",
                "field_type": "combobox",
                "category": "eeo",
                "reason": "EEO field; Tier 3.",
            }
        ]
    )
    legacy = json.dumps([{"field_id": None, "label": None}])

    asyncio.run(
        _seed_one_handoff(
            db_path,
            deferred_questions_json=deferred,
            unresolved_fields_json=legacy,
        )
    )

    response = client.get("/api/human-review", params={"page_size": 50})
    assert response.status_code == 200

    payload = response.json()
    assert payload["ok"] is True
    assert payload["total_items"] == 1
    item = payload["items"][0]

    fields = item["unresolved_fields"]
    assert len(fields) == 1
    assert fields[0]["field_id"] == "e368"
    assert fields[0]["field_name"] == "Gender"
    assert fields[0]["reasoning"] == "EEO field; Tier 3."
    # The reviewer must never see the prior placeholder text.
    assert all(field["field_name"] != "Unresolved field" for field in fields)


def test_get_human_review_falls_back_to_field_id_when_label_missing(
    human_review_client: tuple[TestClient, Path, Path],
) -> None:
    """Legacy rows lacking a label degrade to field_id, not the literal
    ``"Unresolved field"`` placeholder.
    """

    client, db_path, _cache_path = human_review_client

    legacy_only = json.dumps([{"field_id": "fallback_id_42"}])

    asyncio.run(
        _seed_one_handoff(
            db_path,
            deferred_questions_json=None,
            unresolved_fields_json=legacy_only,
        )
    )

    response = client.get("/api/human-review", params={"page_size": 50})
    assert response.status_code == 200
    item = response.json()["items"][0]
    fields = item["unresolved_fields"]
    assert fields[0]["field_name"] == "fallback_id_42"
    assert "Unresolved field" not in [field["field_name"] for field in fields]


def test_post_answers_persists_and_subsequent_get_returns_them(
    human_review_client: tuple[TestClient, Path, Path],
) -> None:
    """POST writes user_answers_json; GET surfaces the round-tripped list."""

    client, db_path, _cache_path = human_review_client

    deferred = json.dumps(
        [
            {"field_id": "e368", "label": "Gender", "field_type": "combobox",
             "category": "eeo", "reason": "EEO."},
            {"field_id": "e385", "label": "Hispanic/Latino?",
             "field_type": "combobox", "category": "eeo", "reason": "EEO."},
        ]
    )
    handoff_id = asyncio.run(
        _seed_one_handoff(
            db_path,
            deferred_questions_json=deferred,
            unresolved_fields_json=None,
        )
    )

    save = client.post(
        f"/api/human-review/{handoff_id}/answers",
        json={
            "answers": [
                {"field_id": "e368", "answer": "Female"},
                {"field_id": "e385", "answer": "No"},
            ]
        },
    )
    assert save.status_code == 200, save.text
    assert save.json()["ok"] is True
    assert save.json()["user_answers"] == [
        {"field_id": "e368", "answer": "Female"},
        {"field_id": "e385", "answer": "No"},
    ]

    queue = client.get("/api/human-review", params={"page_size": 50})
    assert queue.status_code == 200
    item = queue.json()["items"][0]
    assert item["user_answers"] == [
        {"field_id": "e368", "answer": "Female"},
        {"field_id": "e385", "answer": "No"},
    ]


def test_post_answers_returns_404_for_missing_handoff(
    human_review_client: tuple[TestClient, Path, Path],
) -> None:
    """Posting answers to a non-existent handoff yields a 404."""

    client, db_path, _cache_path = human_review_client

    # Initialize an empty database so the apply_handoffs table exists.
    async def _init() -> None:
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            await db.migrate_apply_schema()

    asyncio.run(_init())

    response = client.post(
        "/api/human-review/9999/answers",
        json={"answers": [{"field_id": "x", "answer": "y"}]},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "HANDOFF_NOT_FOUND"


def test_post_answers_overwrites_prior_payload(
    human_review_client: tuple[TestClient, Path, Path],
) -> None:
    """A second POST replaces the first; the GET reflects only the latest."""

    client, db_path, _cache_path = human_review_client

    deferred = json.dumps(
        [{"field_id": "e1", "label": "Q1", "field_type": "text",
          "category": "other", "reason": "n/a"}]
    )
    handoff_id = asyncio.run(
        _seed_one_handoff(
            db_path,
            deferred_questions_json=deferred,
            unresolved_fields_json=None,
        )
    )

    client.post(
        f"/api/human-review/{handoff_id}/answers",
        json={"answers": [{"field_id": "e1", "answer": "first"}]},
    )
    client.post(
        f"/api/human-review/{handoff_id}/answers",
        json={"answers": [{"field_id": "e1", "answer": "second"}]},
    )

    item = client.get("/api/human-review").json()["items"][0]
    assert item["user_answers"] == [{"field_id": "e1", "answer": "second"}]


# ---------------------------------------------------------------------------
# Bug F — POST /answers also appends to the persistent answer cache so
# subsequent finisher runs reuse the human's response instead of deferring
# the same questions again.
# ---------------------------------------------------------------------------


def _deferred_questions_for_cache_seeding() -> str:
    """Build a deferred-questions blob mixing EEO + company-specific prompts.

    Returns:
        JSON string suitable for the ``deferred_questions_json`` column.
        ``Gender`` is anonymized (EEO answers reuse across companies);
        ``Why do you want to work at Cloudflare?`` is company-specific
        (motivation prompts mention the company by name).
    """

    return json.dumps(
        [
            {
                "field_id": "e1",
                "label": "Gender",
                "field_type": "combobox",
                "category": "eeo",
                "reason": "EEO field; Tier 3.",
            },
            {
                "field_id": "e2",
                "label": "Why do you want to work at Cloudflare?",
                "field_type": "textarea",
                "category": "motivation",
                "reason": "Open-ended motivation prompt.",
            },
            {
                "field_id": "e3",
                "label": "(no label)",
                "field_type": "checkbox",
                "category": "other",
                "reason": "Placeholder row from the legacy payload.",
            },
        ]
    )


def test_post_answers_appends_to_persistent_answer_cache(
    human_review_client: tuple[TestClient, Path, Path],
) -> None:
    """Each saved answer lands in ``data/answer_cache.yaml`` so the next
    apply for any company can fuzzy-match it without re-deferring.
    """

    from src.agents.apply_finisher.answer_cache import load_answer_cache

    client, db_path, cache_path = human_review_client

    handoff_id = asyncio.run(
        _seed_one_handoff(
            db_path,
            deferred_questions_json=_deferred_questions_for_cache_seeding(),
            unresolved_fields_json=None,
        )
    )

    response = client.post(
        f"/api/human-review/{handoff_id}/answers",
        json={
            "answers": [
                {"field_id": "e1", "answer": "Female"},
                {
                    "field_id": "e2",
                    "answer": "I admire Cloudflare's edge-network mission.",
                },
                # Empty-answer rows must be skipped, not written.
                {"field_id": "e3", "answer": ""},
            ]
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    summaries = {entry["field_id"]: entry for entry in body["cache_seeded"]}
    assert summaries["e1"].get("skipped") is None
    assert summaries["e1"]["company_specific"] is False
    assert summaries["e2"]["company_specific"] is True
    assert summaries["e3"]["skipped"] == "empty_answer"

    # The on-disk cache now resolves both answers via lookup.
    cache = load_answer_cache(cache_path)

    gender_hit = cache.lookup("Gender", company="Cloudflare")
    assert gender_hit is not None
    assert gender_hit.entry.answer == "Female"

    motivation_hit = cache.lookup(
        "Why do you want to work at Cloudflare?", company="Cloudflare"
    )
    assert motivation_hit is not None
    assert "Cloudflare" in motivation_hit.entry.answer

    # The anonymized EEO answer should also fuzz-match for a different
    # company so reuse spans every future apply.
    cross_company_hit = cache.lookup("Gender", company="OtherCorp")
    assert cross_company_hit is not None
    assert cross_company_hit.entry.answer == "Female"

    # The motivation answer is locked to Cloudflare — a different
    # company must not see it.
    other_company_motivation = cache.lookup(
        "Why do you want to work at Cloudflare?", company="OtherCorp"
    )
    assert other_company_motivation is None


def test_post_answers_skips_placeholder_label_rows(
    human_review_client: tuple[TestClient, Path, Path],
) -> None:
    """``(no label)`` placeholder rows are never appended to the cache —
    writing them would make every future blank field a fake match.
    """

    from src.agents.apply_finisher.answer_cache import load_answer_cache

    client, db_path, cache_path = human_review_client

    handoff_id = asyncio.run(
        _seed_one_handoff(
            db_path,
            deferred_questions_json=_deferred_questions_for_cache_seeding(),
            unresolved_fields_json=None,
        )
    )

    response = client.post(
        f"/api/human-review/{handoff_id}/answers",
        json={
            "answers": [
                {"field_id": "e3", "answer": "I should not be saved."},
            ]
        },
    )
    assert response.status_code == 200
    summaries = {entry["field_id"]: entry for entry in response.json()["cache_seeded"]}
    assert summaries["e3"]["skipped"] == "placeholder_label"

    cache = load_answer_cache(cache_path)
    assert cache.lookup("(no label)", company="Cloudflare") is None


def test_post_answers_is_idempotent_across_repeat_saves(
    human_review_client: tuple[TestClient, Path, Path],
) -> None:
    """Re-saving the same answer twice does not duplicate the cache row.

    The dedup contract is ``cache.lookup`` returning an exact-normalized
    hit with the same answer string; the second POST then short-circuits
    with ``skipped="duplicate"``.
    """

    import yaml

    from src.agents.apply_finisher.answer_cache import load_answer_cache

    client, db_path, cache_path = human_review_client

    deferred = _deferred_questions_for_cache_seeding()
    handoff_id = asyncio.run(
        _seed_one_handoff(
            db_path,
            deferred_questions_json=deferred,
            unresolved_fields_json=None,
        )
    )

    payload = {
        "answers": [
            {"field_id": "e1", "answer": "Female"},
            {
                "field_id": "e2",
                "answer": "I admire Cloudflare's edge-network mission.",
            },
        ]
    }
    first = client.post(
        f"/api/human-review/{handoff_id}/answers", json=payload
    )
    second = client.post(
        f"/api/human-review/{handoff_id}/answers", json=payload
    )

    assert first.status_code == 200
    assert second.status_code == 200

    first_summary = {entry["field_id"]: entry for entry in first.json()["cache_seeded"]}
    second_summary = {entry["field_id"]: entry for entry in second.json()["cache_seeded"]}
    assert first_summary["e1"].get("skipped") is None
    assert second_summary["e1"]["skipped"] == "duplicate"
    assert second_summary["e2"]["skipped"] == "duplicate"

    # Only one entry per (label, answer) pair lands in YAML on disk.
    raw = yaml.safe_load(cache_path.read_text(encoding="utf-8")) or {}
    entries = raw.get("entries") or []
    labels = [entry.get("question_text") for entry in entries]
    assert labels.count("Gender") == 1
    assert labels.count("Why do you want to work at Cloudflare?") == 1

    # Reloading still returns the same hits.
    cache = load_answer_cache(cache_path)
    assert cache.lookup("Gender", company="Cloudflare") is not None
    assert (
        cache.lookup(
            "Why do you want to work at Cloudflare?", company="Cloudflare"
        )
        is not None
    )


def test_post_answers_company_specific_heuristic_mixes_correctly(
    human_review_client: tuple[TestClient, Path, Path],
) -> None:
    """Answers that name the company are filed under the company-specific
    bucket; everything else stays anonymized so it reuses across applies.
    """

    import yaml

    client, db_path, cache_path = human_review_client

    handoff_id = asyncio.run(
        _seed_one_handoff(
            db_path,
            deferred_questions_json=_deferred_questions_for_cache_seeding(),
            unresolved_fields_json=None,
        )
    )

    response = client.post(
        f"/api/human-review/{handoff_id}/answers",
        json={
            "answers": [
                {"field_id": "e1", "answer": "Female"},
                {
                    "field_id": "e2",
                    "answer": "I admire Cloudflare's edge-network mission.",
                },
            ]
        },
    )
    assert response.status_code == 200

    raw = yaml.safe_load(cache_path.read_text(encoding="utf-8")) or {}
    entries = {entry["question_text"]: entry for entry in (raw.get("entries") or [])}
    assert entries["Gender"]["company_specific"] is False
    assert entries["Gender"]["company"] is None
    assert entries["Why do you want to work at Cloudflare?"]["company_specific"] is True
    assert entries["Why do you want to work at Cloudflare?"]["company"] == "Cloudflare"
