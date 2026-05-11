"""Scenario tests for `run_tailor_review_pipeline`.

Purpose:
    The handoff calls out `run_tailor_review_pipeline` as the cognitive-
    complexity hotspot (5+ short-circuit branches, retry+3-way path).
    Each test below pins one documented behavioral-contract branch by
    monkeypatching the LLM calls and the render/compile step, then asserts
    the resulting `TailorRunResult`, `tailor_runs` row, and (where
    applicable) the `review_runs` row.

    Mocks land on the module-bound names (`pipeline.call_tailor`,
    `pipeline.call_reviewer`, `pipeline._render_and_compile_variant`) so
    pipeline-internal call sites resolve to the stubs.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any, cast

import pytest
import pytest_asyncio
import yaml

from src.agents.resume_tailor import pipeline as pipeline_module
from src.agents.resume_tailor.pipeline import run_tailor_review_pipeline
from src.agents.resume_tailor.pipeline_schemas import ReviewerVerdict
from src.database.db_manager import DatabaseManager
from src.models.job_posting import JobPosting

from tests.helpers.pipeline_factories import (
    make_reviewer_result,
    make_tailor_result,
    resume_yaml_fixture_path,
    single_valid_edit,
)


def _candidate_profile_yaml(tmp_path: Path) -> Path:
    """Write a tiny candidate profile YAML and return the path."""

    candidate_path = tmp_path / "candidate.yaml"
    candidate_path.write_text(
        yaml.safe_dump({"summary": "A short test profile"}),
        encoding="utf-8",
    )
    return candidate_path


async def _seed_pipeline_inputs(
    db: DatabaseManager,
    *,
    job_hash: str,
) -> int:
    """Insert one QUALIFIED job and one PENDING tailor row.

    Purpose:
        Provide the row IDs that the pipeline expects to update.
    """

    posting = JobPosting(
        source="manual",
        source_url="https://example.com/" + job_hash,
        company="ACME",
        title="Engineer",
        description="Job description",
    )
    db_dict = posting.to_db_dict()
    db_dict["job_hash"] = job_hash
    await db.insert_job(db_dict)
    inserted = await db.insert_user_triggered_tailor_run(job_hash=job_hash)
    assert inserted is not None
    return cast(int, inserted["id"])


def _make_compile_stub(
    *,
    base_pages: int = 1,
    v1_pages: int = 1,
    v2_pages: int = 1,
) -> Any:
    """Return a stub that emulates `_render_and_compile_variant` per variant.

    Purpose:
        Avoid running `latexmk` / `pdfinfo` in tests. Each variant directory
        receives a placeholder YAML and a stub PDF path so downstream code
        can still concatenate paths into the report.
    """

    page_counts = {
        "base": base_pages,
        "tailored_v1": v1_pages,
        "tailored_v2": v2_pages,
    }

    def _stub(
        *,
        resume_content: Any,
        variant_dir: Path,
        variant_name: str,
    ) -> tuple[Path, Path, Path, int]:
        variant_dir.mkdir(parents=True, exist_ok=True)
        yaml_path = variant_dir / f"{variant_name}.yaml"
        tex_path = variant_dir / f"{variant_name}.tex"
        pdf_path = variant_dir / f"{variant_name}.pdf"
        yaml_path.write_text("placeholder", encoding="utf-8")
        tex_path.write_text("placeholder", encoding="utf-8")
        pdf_path.write_text("placeholder", encoding="utf-8")
        return yaml_path, tex_path, pdf_path, page_counts[variant_name]

    return _stub


@pytest_asyncio.fixture
async def db(tmp_path: Path) -> AsyncGenerator[DatabaseManager, None]:
    """Provide a fresh DB with full schema migrated."""

    manager = DatabaseManager(str(tmp_path / "pipeline.db"))
    await manager.connect()
    await manager.create_tables()
    yield manager
    await manager.close()


@pytest.mark.asyncio
async def test_job_not_found_records_failure_without_review_row(
    db: DatabaseManager,
    tmp_path: Path,
) -> None:
    """Missing job → FAILED row with `job_not_found:`; no review row created."""

    # Insert a tailor row that points at a nonexistent job_hash.
    inserter = await db.insert_user_triggered_tailor_run(job_hash="dead" * 10)
    assert inserter is not None

    result = await run_tailor_review_pipeline(
        db=db,
        tailor_run_id=cast(int, inserter["id"]),
        job_hash="dead" * 10,
        base_resume_yaml_path=resume_yaml_fixture_path(),
        candidate_profile_yaml_path=_candidate_profile_yaml(tmp_path),
        output_dir=tmp_path / "out",
        record_costs=False,
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.startswith("job_not_found:")

    row = await db.get_tailor_run(cast(int, inserter["id"]))
    assert row is not None
    assert row["status"] == "FAILED"
    assert row["error"] == result.error

    review_rows = await db.get_review_runs_for_tailor_run(cast(int, inserter["id"]))
    assert review_rows == []


@pytest.mark.asyncio
async def test_base_resume_missing_records_load_failure(
    db: DatabaseManager,
    tmp_path: Path,
) -> None:
    """Unloadable base YAML → FAILED with `base_resume_load_failed:`."""

    tailor_run_id = await _seed_pipeline_inputs(db, job_hash="aa" * 20)
    missing_path = tmp_path / "does_not_exist.yaml"

    result = await run_tailor_review_pipeline(
        db=db,
        tailor_run_id=tailor_run_id,
        job_hash="aa" * 20,
        base_resume_yaml_path=missing_path,
        candidate_profile_yaml_path=_candidate_profile_yaml(tmp_path),
        output_dir=tmp_path / "out",
        record_costs=False,
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.startswith("base_resume_load_failed:")
    row = await db.get_tailor_run(tailor_run_id)
    assert row is not None
    assert row["status"] == "FAILED"


@pytest.mark.asyncio
async def test_zero_applicable_edits_short_circuits_to_no_improvement(
    db: DatabaseManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All-invalid edits → SUCCESS NO_IMPROVEMENT; reviewer never invoked."""

    tailor_run_id = await _seed_pipeline_inputs(db, job_hash="bb" * 20)
    reviewer_calls: list[str] = []

    async def _tailor_stub(user_message: str) -> Any:
        return make_tailor_result(edits=[])  # empty edits → applied_v1 = 0

    async def _reviewer_stub(user_message: str) -> Any:
        reviewer_calls.append(user_message)
        raise AssertionError("Reviewer should not be invoked for 0 edits")

    monkeypatch.setattr(pipeline_module, "call_tailor", _tailor_stub)
    monkeypatch.setattr(pipeline_module, "call_reviewer", _reviewer_stub)
    monkeypatch.setattr(
        pipeline_module,
        "_render_and_compile_variant",
        _make_compile_stub(),
    )

    result = await run_tailor_review_pipeline(
        db=db,
        tailor_run_id=tailor_run_id,
        job_hash="bb" * 20,
        base_resume_yaml_path=resume_yaml_fixture_path(),
        candidate_profile_yaml_path=_candidate_profile_yaml(tmp_path),
        output_dir=tmp_path / "out",
        record_costs=False,
    )

    assert result.success is True
    assert result.verdict == "NO_IMPROVEMENT"
    assert result.selected_pdf_path is not None and "base" in result.selected_pdf_path
    assert reviewer_calls == []

    row = await db.get_tailor_run(tailor_run_id)
    assert row is not None
    assert row["status"] == "SUCCESS"
    assert "base" in str(row["artifact_pdf_path"])

    reviews = await db.get_review_runs_for_tailor_run(tailor_run_id)
    assert len(reviews) == 1
    assert reviews[0]["verdict"] == "NO_IMPROVEMENT"


@pytest.mark.asyncio
async def test_reviewer_picks_tailored_records_tailored_verdict(
    db: DatabaseManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """1-page v1 + reviewer `tailored_better` → SUCCESS TAILORED with v1 paths."""

    tailor_run_id = await _seed_pipeline_inputs(db, job_hash="cc" * 20)

    async def _tailor_stub(user_message: str) -> Any:
        return make_tailor_result(edits=[single_valid_edit()])

    async def _reviewer_stub(user_message: str) -> Any:
        return make_reviewer_result(verdict=ReviewerVerdict.TAILORED_BETTER)

    monkeypatch.setattr(pipeline_module, "call_tailor", _tailor_stub)
    monkeypatch.setattr(pipeline_module, "call_reviewer", _reviewer_stub)
    monkeypatch.setattr(
        pipeline_module,
        "_render_and_compile_variant",
        _make_compile_stub(base_pages=1, v1_pages=1),
    )

    result = await run_tailor_review_pipeline(
        db=db,
        tailor_run_id=tailor_run_id,
        job_hash="cc" * 20,
        base_resume_yaml_path=resume_yaml_fixture_path(),
        candidate_profile_yaml_path=_candidate_profile_yaml(tmp_path),
        output_dir=tmp_path / "out",
        record_costs=False,
    )

    assert result.success is True
    assert result.verdict == "TAILORED"
    assert result.selected_pdf_path is not None
    assert "tailored_v1" in result.selected_pdf_path


@pytest.mark.asyncio
async def test_reviewer_picks_no_improvement_returns_base_paths(
    db: DatabaseManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reviewer says `no_meaningful_improvement` → SUCCESS NO_IMPROVEMENT, base paths."""

    tailor_run_id = await _seed_pipeline_inputs(db, job_hash="dd" * 20)

    async def _tailor_stub(user_message: str) -> Any:
        return make_tailor_result(edits=[single_valid_edit()])

    async def _reviewer_stub(user_message: str) -> Any:
        return make_reviewer_result(verdict=ReviewerVerdict.NO_MEANINGFUL_IMPROVEMENT)

    monkeypatch.setattr(pipeline_module, "call_tailor", _tailor_stub)
    monkeypatch.setattr(pipeline_module, "call_reviewer", _reviewer_stub)
    monkeypatch.setattr(
        pipeline_module,
        "_render_and_compile_variant",
        _make_compile_stub(base_pages=1, v1_pages=1),
    )

    result = await run_tailor_review_pipeline(
        db=db,
        tailor_run_id=tailor_run_id,
        job_hash="dd" * 20,
        base_resume_yaml_path=resume_yaml_fixture_path(),
        candidate_profile_yaml_path=_candidate_profile_yaml(tmp_path),
        output_dir=tmp_path / "out",
        record_costs=False,
    )

    assert result.success is True
    assert result.verdict == "NO_IMPROVEMENT"
    assert result.selected_pdf_path is not None
    assert "base" in result.selected_pdf_path

    # tailor_runs.artifact_* still points at tailored_v1
    row = await db.get_tailor_run(tailor_run_id)
    assert row is not None
    assert "tailored_v1" in str(row["artifact_pdf_path"])


@pytest.mark.asyncio
async def test_overflow_after_trim_returns_page_fit_failed_without_reviewer(
    db: DatabaseManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """v1 > 1 page and trim still > 1 page → SUCCESS PAGE_FIT_FAILED; no reviewer."""

    tailor_run_id = await _seed_pipeline_inputs(db, job_hash="ee" * 20)
    tailor_calls: list[str] = []
    trim_calls: list[str] = []
    reviewer_calls: list[str] = []

    async def _tailor_stub(user_message: str) -> Any:
        tailor_calls.append(user_message)
        return make_tailor_result(edits=[single_valid_edit()])

    async def _trim_stub(user_message: str) -> Any:
        trim_calls.append(user_message)
        return make_tailor_result(edits=[single_valid_edit()])

    async def _reviewer_stub(user_message: str) -> Any:
        reviewer_calls.append(user_message)
        raise AssertionError("Reviewer should not run on PAGE_FIT_FAILED")

    monkeypatch.setattr(pipeline_module, "call_tailor", _tailor_stub)
    monkeypatch.setattr(pipeline_module, "call_trim", _trim_stub)
    monkeypatch.setattr(pipeline_module, "call_reviewer", _reviewer_stub)
    monkeypatch.setattr(
        pipeline_module,
        "_render_and_compile_variant",
        _make_compile_stub(base_pages=1, v1_pages=2),
    )

    result = await run_tailor_review_pipeline(
        db=db,
        tailor_run_id=tailor_run_id,
        job_hash="ee" * 20,
        base_resume_yaml_path=resume_yaml_fixture_path(),
        candidate_profile_yaml_path=_candidate_profile_yaml(tmp_path),
        output_dir=tmp_path / "out",
        record_costs=False,
    )

    assert result.success is True
    assert result.verdict == "PAGE_FIT_FAILED"
    assert "base" in str(result.selected_pdf_path)
    assert len(trim_calls) == 1
    assert reviewer_calls == []

    reviews = await db.get_review_runs_for_tailor_run(tailor_run_id)
    assert len(reviews) == 1
    assert reviews[0]["verdict"] == "PAGE_FIT_FAILED"
    report = json.loads(str(reviews[0]["review_report_json"]))
    assert report["reason"] == "page_fit_failed"


@pytest.mark.asyncio
async def test_trim_brings_below_limit_then_reviewer_picks_tailored(
    db: DatabaseManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """v1 > 1 page → trim succeeds → reviewer runs → TAILORED."""

    tailor_run_id = await _seed_pipeline_inputs(db, job_hash="ff" * 20)
    call_log: list[str] = []
    page_counts = iter([1, 2, 1])  # base, v1, trimmed_v1

    async def _tailor_stub(user_message: str) -> Any:
        call_log.append("tailor")
        return make_tailor_result(edits=[single_valid_edit()])

    async def _trim_stub(user_message: str) -> Any:
        call_log.append("trim")
        return make_tailor_result(edits=[single_valid_edit()])

    async def _reviewer_stub(user_message: str) -> Any:
        call_log.append("reviewer")
        return make_reviewer_result(verdict=ReviewerVerdict.TAILORED_BETTER)

    def _stub_compile(
        *, resume_content: Any, variant_dir: Path, variant_name: str
    ) -> tuple[Path, Path, Path, int]:
        variant_dir.mkdir(parents=True, exist_ok=True)
        yaml_path = variant_dir / f"{variant_name}.yaml"
        tex_path = variant_dir / f"{variant_name}.tex"
        pdf_path = variant_dir / f"{variant_name}.pdf"
        for path in (yaml_path, tex_path, pdf_path):
            path.write_text("placeholder", encoding="utf-8")
        return yaml_path, tex_path, pdf_path, next(page_counts)

    monkeypatch.setattr(pipeline_module, "call_tailor", _tailor_stub)
    monkeypatch.setattr(pipeline_module, "call_trim", _trim_stub)
    monkeypatch.setattr(pipeline_module, "call_reviewer", _reviewer_stub)
    monkeypatch.setattr(pipeline_module, "_render_and_compile_variant", _stub_compile)

    result = await run_tailor_review_pipeline(
        db=db,
        tailor_run_id=tailor_run_id,
        job_hash="ff" * 20,
        base_resume_yaml_path=resume_yaml_fixture_path(),
        candidate_profile_yaml_path=_candidate_profile_yaml(tmp_path),
        output_dir=tmp_path / "out",
        record_costs=False,
    )

    assert result.success is True
    assert result.verdict == "TAILORED"
    assert "tailor" in call_log and "trim" in call_log and "reviewer" in call_log


@pytest.mark.asyncio
async def test_base_better_triggers_retry_and_three_way_picks_tailored(
    db: DatabaseManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`base_better` on 2-way → retry → fitting v2 → 3-way TAILORED on v2."""

    tailor_run_id = await _seed_pipeline_inputs(db, job_hash="00" * 20)
    reviewer_verdicts = iter(
        [ReviewerVerdict.BASE_BETTER, ReviewerVerdict.TAILORED_BETTER]
    )

    async def _tailor_stub(user_message: str) -> Any:
        return make_tailor_result(edits=[single_valid_edit()])

    async def _reviewer_stub(user_message: str) -> Any:
        return make_reviewer_result(
            verdict=next(reviewer_verdicts),
            feedback_for_retry="Try more impact verbs.",
        )

    monkeypatch.setattr(pipeline_module, "call_tailor", _tailor_stub)
    monkeypatch.setattr(pipeline_module, "call_reviewer", _reviewer_stub)
    monkeypatch.setattr(
        pipeline_module,
        "_render_and_compile_variant",
        _make_compile_stub(base_pages=1, v1_pages=1, v2_pages=1),
    )

    result = await run_tailor_review_pipeline(
        db=db,
        tailor_run_id=tailor_run_id,
        job_hash="00" * 20,
        base_resume_yaml_path=resume_yaml_fixture_path(),
        candidate_profile_yaml_path=_candidate_profile_yaml(tmp_path),
        output_dir=tmp_path / "out",
        record_costs=False,
    )

    assert result.success is True
    assert result.verdict == "TAILORED"
    assert "tailored_v2" in str(result.selected_pdf_path)

    row = await db.get_tailor_run(tailor_run_id)
    assert row is not None
    assert "tailored_v2" in str(row["artifact_pdf_path"])


@pytest.mark.asyncio
async def test_base_better_then_retry_with_zero_edits_skips_three_way(
    db: DatabaseManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`base_better` → retry returns 0 edits → no 3-way; final verdict is BASE."""

    tailor_run_id = await _seed_pipeline_inputs(db, job_hash="11" * 20)
    tailor_outputs = iter([[single_valid_edit()], []])  # first run normal, retry empty
    reviewer_calls: list[str] = []

    async def _tailor_stub(user_message: str) -> Any:
        return make_tailor_result(edits=next(tailor_outputs))

    async def _reviewer_stub(user_message: str) -> Any:
        reviewer_calls.append(user_message)
        return make_reviewer_result(
            verdict=ReviewerVerdict.BASE_BETTER,
            feedback_for_retry="Try harder.",
        )

    monkeypatch.setattr(pipeline_module, "call_tailor", _tailor_stub)
    monkeypatch.setattr(pipeline_module, "call_reviewer", _reviewer_stub)
    monkeypatch.setattr(
        pipeline_module,
        "_render_and_compile_variant",
        _make_compile_stub(base_pages=1, v1_pages=1),
    )

    result = await run_tailor_review_pipeline(
        db=db,
        tailor_run_id=tailor_run_id,
        job_hash="11" * 20,
        base_resume_yaml_path=resume_yaml_fixture_path(),
        candidate_profile_yaml_path=_candidate_profile_yaml(tmp_path),
        output_dir=tmp_path / "out",
        record_costs=False,
    )

    assert result.success is True
    assert result.verdict == "BASE"
    assert "base" in str(result.selected_pdf_path)
    # 2-way is the only reviewer call; no 3-way pass happens.
    assert len(reviewer_calls) == 1


@pytest.mark.asyncio
async def test_uncaught_exception_records_pipeline_failed(
    db: DatabaseManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exception anywhere inside the try block → FAILED `pipeline_failed:` (truncated)."""

    tailor_run_id = await _seed_pipeline_inputs(db, job_hash="22" * 20)

    async def _tailor_stub(user_message: str) -> Any:
        raise RuntimeError("simulated provider blow-up")

    monkeypatch.setattr(pipeline_module, "call_tailor", _tailor_stub)
    monkeypatch.setattr(
        pipeline_module,
        "_render_and_compile_variant",
        _make_compile_stub(),
    )

    result = await run_tailor_review_pipeline(
        db=db,
        tailor_run_id=tailor_run_id,
        job_hash="22" * 20,
        base_resume_yaml_path=resume_yaml_fixture_path(),
        candidate_profile_yaml_path=_candidate_profile_yaml(tmp_path),
        output_dir=tmp_path / "out",
        record_costs=False,
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.startswith("pipeline_failed:")
    assert "simulated provider blow-up" in result.error

    row = await db.get_tailor_run(tailor_run_id)
    assert row is not None
    assert row["status"] == "FAILED"
    assert str(row["error"]).startswith("pipeline_failed:")


@pytest.mark.asyncio
async def test_pipeline_does_not_mutate_base_resume_yaml(
    db: DatabaseManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Base resume YAML is byte-identical before/after a successful run.

    Purpose:
        Explicitly assert the `config/resume_content.yaml` immutability
        invariant flagged in the handoff Risk Areas.
    """

    tailor_run_id = await _seed_pipeline_inputs(db, job_hash="33" * 20)
    source_yaml = resume_yaml_fixture_path()
    working_copy = tmp_path / "resume_content.yaml"
    working_copy.write_bytes(source_yaml.read_bytes())
    expected_bytes = working_copy.read_bytes()

    async def _tailor_stub(user_message: str) -> Any:
        return make_tailor_result(edits=[single_valid_edit()])

    async def _reviewer_stub(user_message: str) -> Any:
        return make_reviewer_result(verdict=ReviewerVerdict.TAILORED_BETTER)

    monkeypatch.setattr(pipeline_module, "call_tailor", _tailor_stub)
    monkeypatch.setattr(pipeline_module, "call_reviewer", _reviewer_stub)
    monkeypatch.setattr(
        pipeline_module,
        "_render_and_compile_variant",
        _make_compile_stub(base_pages=1, v1_pages=1),
    )

    await run_tailor_review_pipeline(
        db=db,
        tailor_run_id=tailor_run_id,
        job_hash="33" * 20,
        base_resume_yaml_path=working_copy,
        candidate_profile_yaml_path=_candidate_profile_yaml(tmp_path),
        output_dir=tmp_path / "out",
        record_costs=False,
    )

    assert working_copy.read_bytes() == expected_bytes
