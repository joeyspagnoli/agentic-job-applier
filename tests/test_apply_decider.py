"""Test the apply-decider prompt, parser, and batch persistence workflow."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from scripts import process_new_jobs
from src.agents.root_apply_decider import (
    ApplyDecision,
    GateDebugInfo,
    GateRunResult,
    build_gate_payload,
    parse_gate_response,
)
from src.database.db_manager import DatabaseManager
from src.models.job_posting import JobPosting


def test_build_gate_payload_contains_candidate_policy_and_job_fields():
    """Verify the gate payload contains the expected candidate and job sections.

    Purpose:
        Ensure the prompt builder includes the compact policy context and the
        normalized job fields the gate needs to make a decision.
    Args:
        None.
    Output:
        Returns `None`; the test passes when the rendered payload includes the
        expected candidate and job content.
    """

    job = {
        "company": "Capital One",
        "title": "Technology Internship Program",
        "source": "workday",
        "source_url": "https://example.com/job",
        "location": "McLean, VA",
        "is_remote": False,
        "job_type": "Internship",
        "salary_min": 5300000,
        "salary_max": 6500000,
        "salary_currency": "USD",
        "salary_source": "direct",
        "description": "Build backend systems and internal developer tools.",
        "requirements": "Pursuing a bachelor's degree in computer science.",
    }

    # The rendered payload should remain readable while still carrying the
    # policy and job data that drive the binary gate decision.
    payload = build_gate_payload(job)

    assert "Candidate Context" in payload
    assert "US only" in payload
    assert "Technology Internship Program" in payload
    assert "USD $53,000 - $65,000" in payload
    assert "Build backend systems" in payload


def test_parse_gate_response_recovers_json_and_optional_debug_fields():
    """Verify JSON output is parsed into the required decision and debug info.

    Purpose:
        Confirm that the parser accepts the expected JSON response shape and
        preserves optional metadata without making it required for success.
    Args:
        None.
    Output:
        Returns `None`; the test passes when the parsed result includes both
        the required decision and the optional debug fields.
    """

    raw_response = json.dumps(
        {
            "decision": "APPLY",
            "confidence": 0.91,
            "explanation": "Strong internship fit in a serious technology organization.",
            "preference_matches": ["internship", "real engineering work"],
            "preference_conflicts": [],
        }
    )

    result = parse_gate_response(
        raw_response,
        provider="openai",
        model="openai/gpt-5-mini",
    )

    assert result.decision == ApplyDecision.APPLY
    assert result.debug.confidence == pytest.approx(0.91)
    assert result.debug.preference_matches == ["internship", "real engineering work"]
    assert result.parse_mode == "json_recovered"


def test_parse_gate_response_recovers_text_only_decision():
    """Verify the parser can recover APPLY or SKIP from plain text responses.

    Purpose:
        Keep the workflow resilient when the model returns prose instead of the
        expected JSON object while still making the binary gate decision usable.
    Args:
        None.
    Output:
        Returns `None`; the test passes when the decision is recovered from
        plain text and the parse mode reflects that fallback path.
    """

    result = parse_gate_response(
        "Decision: SKIP because this is a full-time retail SWE role.",
        provider="openai",
        model="openai/gpt-5-mini",
    )

    assert result.decision == ApplyDecision.SKIP
    assert result.parse_mode == "text_recovered"
    assert result.debug.explanation is None


@pytest.mark.asyncio
async def test_process_once_records_apply_result(monkeypatch: pytest.MonkeyPatch):
    """Verify the batch processor persists a recovered APPLY decision.

    Purpose:
        Confirm that the batch workflow updates status and stores the serialized
        gate payload when the decider succeeds.
    Args:
        monkeypatch: Pytest fixture used to replace live model behavior.
    Output:
        Returns `None`; the test passes when the job becomes `QUALIFIED` and
        the stored `agent_result` JSON contains the expected decision payload.
    """

    async def fake_run_decider_for_job(**_: object) -> GateRunResult:
        """Return a stable fake gate result for batch-processing tests.

        Purpose:
            Replace the live ADK/model path so the persistence workflow can be
            tested deterministically and without network calls.
        Args:
            **_: Ignored keyword arguments from the production call site.
        Output:
            Returns a deterministic `GateRunResult`.
        """

        return GateRunResult(
            decision=ApplyDecision.APPLY,
            debug=GateDebugInfo(
                confidence=0.88,
                explanation="Aligned internship role at a strong company.",
                preference_matches=["internship", "strong company"],
                preference_conflicts=[],
            ),
            raw_response='{"decision":"APPLY"}',
            provider="openai",
            model="openai/gpt-5-mini",
            parse_mode="json_recovered",
        )

    monkeypatch.setattr(process_new_jobs, "get_decider_model", lambda: object())
    monkeypatch.setattr(process_new_jobs, "build_root_agent", lambda model: object())
    monkeypatch.setattr(process_new_jobs, "_run_decider_for_job", fake_run_decider_for_job)

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            await db.migrate_agent_schema()

            job = JobPosting(
                source="test",
                source_url="https://example.com/job/1",
                company="Capital One",
                title="Technology Internship Program",
                location="McLean, VA",
                job_type="Internship",
                description="Build software for internal platforms.",
                requirements="Pursuing a bachelor's degree.",
            )
            await db.insert_job(job.to_db_dict())

            processed = await process_new_jobs._process_once(db=db, limit=10)
            stored_job = await db.get_job_by_hash(job.job_hash)

    assert processed == 1
    assert stored_job is not None
    assert stored_job["status"] == "QUALIFIED"

    persisted_result = json.loads(stored_job["agent_result"])
    assert persisted_result["decision"] == "APPLY"
    assert persisted_result["provider"] == "openai"


@pytest.mark.asyncio
async def test_process_once_marks_agent_failure_when_decision_is_unrecoverable(
    monkeypatch: pytest.MonkeyPatch,
):
    """Verify unrecoverable model output is recorded as an agent failure.

    Purpose:
        Confirm that the workflow only marks a run failed when the parser cannot
        recover APPLY or SKIP from the model response.
    Args:
        monkeypatch: Pytest fixture used to replace live model behavior.
    Output:
        Returns `None`; the test passes when the failure metadata is recorded
        and the job is excluded from normal successful processing.
    """

    async def fake_run_decider_for_job(**_: object) -> GateRunResult:
        """Raise a stable parser error for failure-path testing.

        Purpose:
            Simulate the one case where the gate workflow should mark a job as
            failed: when no APPLY or SKIP decision can be recovered.
        Args:
            **_: Ignored keyword arguments from the production call site.
        Output:
            Raises a `ValueError` describing the unrecoverable parse failure.
        """

        raise ValueError("Could not recover APPLY or SKIP from model response")

    monkeypatch.setattr(process_new_jobs, "get_decider_model", lambda: object())
    monkeypatch.setattr(process_new_jobs, "build_root_agent", lambda model: object())
    monkeypatch.setattr(process_new_jobs, "_run_decider_for_job", fake_run_decider_for_job)

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            await db.migrate_agent_schema()

            job = JobPosting(
                source="test",
                source_url="https://example.com/job/2",
                company="Retail Co",
                title="Full Time Engineer",
                job_type="Full-time",
                description="A role with unclear output formatting.",
            )
            await db.insert_job(job.to_db_dict())

            processed = await process_new_jobs._process_once(db=db, limit=10)
            stored_job = await db.get_job_by_hash(job.job_hash)

    assert processed == 0
    assert stored_job is not None
    assert stored_job["agent_failed_at"] is not None
    assert "Could not recover APPLY or SKIP" in stored_job["agent_error"]
