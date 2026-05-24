"""Scenario tests for `run_tailor_review_pipeline` (Phase 2).

Purpose:
    Phase 2 (#60) rewrote the pipeline to operate on the user's
    `.tex` resume + a bullet manifest + a byte-offset patcher. Each
    test below pins one documented behavioral-contract branch by
    monkeypatching the LLM calls and the write/compile step, then
    asserts the resulting `TailorRunResult`, `tailor_runs` row, and
    (where applicable) the `review_runs` row.

    Mocks land on the module-bound names (`pipeline.call_tailor`,
    `pipeline.call_reviewer`, `pipeline._write_and_compile_variant`)
    so pipeline-internal call sites resolve to the stubs.
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
from src.agents.resume_tailor.pipeline_schemas import (
    BulletPatchProposal,
    ReviewerVerdict,
    SkippedBulletNote,
)
from src.database.db_manager import DatabaseManager
from src.models.job_posting import JobPosting

from tests.helpers.pipeline_factories import (
    build_minimal_bullet_manifest,
    make_reviewer_result,
    make_tailor_result,
    resume_tex_fixture_path,
    single_valid_patch_proposal,
)


def _candidate_profile_yaml(tmp_path: Path) -> Path:
    """Write a tiny candidate profile YAML and return the path.

    Purpose:
        Phase-2 pipeline still reads the candidate profile YAML for
        the tailor prompt. Tests need a real-ish path to feed in.
    Args:
        tmp_path: pytest-provided per-test temp dir.
    Output:
        Path to the written YAML file.
    """

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
    Args:
        db: Connected database manager (per-test fresh DB).
        job_hash: Stable identifier for the fake job posting.
    Output:
        Primary key of the inserted tailor run.
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
    return int(inserted["id"])


def _make_write_compile_stub(
    *,
    base_pages: int = 1,
    v1_pages: int = 1,
    v2_pages: int = 1,
) -> Any:
    """Return a stub that emulates `_write_and_compile_variant`.

    Purpose:
        Avoid running tectonic / pdfinfo in tests. Each variant
        directory receives a placeholder PDF so downstream code can
        still concatenate paths into the report.
    Args:
        base_pages: Page count to report for the `base` variant.
        v1_pages: Page count to report for `tailored_v1`.
        v2_pages: Page count to report for `tailored_v2`.
    Output:
        Callable matching `_write_and_compile_variant`'s signature.
    """

    page_counts = {
        "base": base_pages,
        "tailored_v1": v1_pages,
        "tailored_v2": v2_pages,
    }

    def _stub(
        *,
        tex_text: str,
        variant_dir: Path,
        variant_name: str,
    ) -> tuple[Path, Path, int]:
        variant_dir.mkdir(parents=True, exist_ok=True)
        tex_path = variant_dir / f"{variant_name}.tex"
        pdf_path = variant_dir / f"{variant_name}.pdf"
        tex_path.write_text(tex_text, encoding="utf-8")
        pdf_path.write_text("placeholder-pdf", encoding="utf-8")
        return tex_path, pdf_path, page_counts[variant_name]

    return _stub


@pytest_asyncio.fixture
async def db(tmp_path: Path) -> AsyncGenerator[DatabaseManager, None]:
    """Provide a fresh DB with full schema migrated.

    Purpose:
        Each test gets an isolated SQLite file so concurrent runs
        don't share state through the tailor / review tables.
    """

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
    inserter = await db.insert_user_triggered_tailor_run(job_hash="dead" * 10)
    assert inserter is not None

    result = await run_tailor_review_pipeline(
        db=db,
        tailor_run_id=int(inserter["id"]),
        job_hash="dead" * 10,
        base_resume_tex_path=resume_tex_fixture_path(),
        candidate_profile_yaml_path=_candidate_profile_yaml(tmp_path),
        output_dir=tmp_path / "out",
        record_costs=False,
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.startswith("job_not_found:")

    row = await db.get_tailor_run(int(inserter["id"]))
    assert row is not None
    assert row["status"] == "FAILED"


@pytest.mark.asyncio
async def test_invalid_resume_tex_records_runtime_failure(
    db: DatabaseManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Point the pipeline at a non-conforming `.tex` (no tailorable
    # section). The validator should reject it at runtime, the
    # pipeline should record a structured failure.
    bad_tex = tmp_path / "broken.tex"
    bad_tex.write_text(
        "\\documentclass{article}\\begin{document}no sections\\end{document}",
        encoding="utf-8",
    )
    job_hash = "bbbb" * 10
    tailor_run_id = await _seed_pipeline_inputs(db, job_hash=job_hash)

    result = await run_tailor_review_pipeline(
        db=db,
        tailor_run_id=tailor_run_id,
        job_hash=job_hash,
        base_resume_tex_path=bad_tex,
        candidate_profile_yaml_path=_candidate_profile_yaml(tmp_path),
        output_dir=tmp_path / "out",
        record_costs=False,
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.startswith("invalid_resume_tex_at_runtime:")
    assert "CONTRACT_NO_TAILORABLE_SECTION" in result.error


@pytest.mark.asyncio
async def test_happy_path_tailored_wins_and_ships(
    db: DatabaseManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_hash = "happ" * 10
    tailor_run_id = await _seed_pipeline_inputs(db, job_hash=job_hash)

    async def _fake_tailor(_message: str) -> Any:
        return make_tailor_result(bullets=[single_valid_patch_proposal()])

    async def _fake_reviewer(_message: str) -> Any:
        return make_reviewer_result(verdict=ReviewerVerdict.TAILORED_BETTER)

    monkeypatch.setattr(pipeline_module, "call_tailor", _fake_tailor)
    monkeypatch.setattr(pipeline_module, "call_reviewer", _fake_reviewer)
    monkeypatch.setattr(
        pipeline_module, "_write_and_compile_variant", _make_write_compile_stub()
    )

    result = await run_tailor_review_pipeline(
        db=db,
        tailor_run_id=tailor_run_id,
        job_hash=job_hash,
        base_resume_tex_path=resume_tex_fixture_path(),
        candidate_profile_yaml_path=_candidate_profile_yaml(tmp_path),
        output_dir=tmp_path / "out",
        record_costs=False,
    )

    assert result.success is True
    assert result.verdict == "TAILORED"
    assert result.selected_tex_path is not None
    assert "tailored_v1" in result.selected_tex_path

    review_rows = await db.get_review_runs_for_tailor_run(tailor_run_id)
    assert len(review_rows) == 1
    review_payload = json.loads(cast(str, review_rows[0]["review_report_json"]))
    assert review_payload["had_retry"] is False
    assert review_payload["bullets_applied"] == 1


@pytest.mark.asyncio
async def test_zero_proposals_ships_base_with_tailor_bailed_reason(
    db: DatabaseManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_hash = "bail" * 10
    tailor_run_id = await _seed_pipeline_inputs(db, job_hash=job_hash)

    async def _fake_tailor(_message: str) -> Any:
        # Empty bullets list → tailor bailed.
        return make_tailor_result(bullets=[])

    monkeypatch.setattr(pipeline_module, "call_tailor", _fake_tailor)
    monkeypatch.setattr(
        pipeline_module, "_write_and_compile_variant", _make_write_compile_stub()
    )

    result = await run_tailor_review_pipeline(
        db=db,
        tailor_run_id=tailor_run_id,
        job_hash=job_hash,
        base_resume_tex_path=resume_tex_fixture_path(),
        candidate_profile_yaml_path=_candidate_profile_yaml(tmp_path),
        output_dir=tmp_path / "out",
        record_costs=False,
    )

    assert result.success is True
    assert result.verdict == "NO_IMPROVEMENT"
    assert result.selected_tex_path is not None
    assert "/base/" in result.selected_tex_path

    review_rows = await db.get_review_runs_for_tailor_run(tailor_run_id)
    assert len(review_rows) == 1
    review_payload = json.loads(cast(str, review_rows[0]["review_report_json"]))
    assert review_payload["reason"] == "tailor_bailed"


@pytest.mark.asyncio
async def test_all_proposals_dropped_for_unknown_ids(
    db: DatabaseManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_hash = "drop" * 10
    tailor_run_id = await _seed_pipeline_inputs(db, job_hash=job_hash)

    async def _fake_tailor(_message: str) -> Any:
        # Bullet ID that doesn't exist in the manifest → dropped.
        return make_tailor_result(
            bullets=[
                BulletPatchProposal(
                    id="ghost_bullet",
                    rationale="hallucinated",
                    action="rewrite",
                    new_text="never lands",
                )
            ]
        )

    monkeypatch.setattr(pipeline_module, "call_tailor", _fake_tailor)
    monkeypatch.setattr(
        pipeline_module, "_write_and_compile_variant", _make_write_compile_stub()
    )

    result = await run_tailor_review_pipeline(
        db=db,
        tailor_run_id=tailor_run_id,
        job_hash=job_hash,
        base_resume_tex_path=resume_tex_fixture_path(),
        candidate_profile_yaml_path=_candidate_profile_yaml(tmp_path),
        output_dir=tmp_path / "out",
        record_costs=False,
    )

    assert result.success is True
    assert result.verdict == "NO_IMPROVEMENT"

    review_payload = json.loads(
        cast(
            str,
            (await db.get_review_runs_for_tailor_run(tailor_run_id))[0][
                "review_report_json"
            ],
        )
    )
    assert review_payload["reason"] == "all_edits_dropped"
    assert review_payload["bullets_proposed"] == 1
    assert review_payload["bullets_applied"] == 0


@pytest.mark.asyncio
async def test_page_overflow_trim_pass_succeeds_and_reviewer_picks_tailored(
    db: DatabaseManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_hash = "trim" * 10
    tailor_run_id = await _seed_pipeline_inputs(db, job_hash=job_hash)

    async def _fake_tailor(_message: str) -> Any:
        return make_tailor_result(bullets=[single_valid_patch_proposal()])

    # Trim returns a different rewrite for the same bullet (shorter).
    async def _fake_trim(_message: str) -> Any:
        return make_tailor_result(
            bullets=[
                BulletPatchProposal(
                    id=single_valid_patch_proposal().id,
                    rationale="trim",
                    action="rewrite",
                    new_text="Shorter.",
                )
            ]
        )

    async def _fake_reviewer(_message: str) -> Any:
        return make_reviewer_result(verdict=ReviewerVerdict.TAILORED_BETTER)

    # v1 overflows; rerun after trim fits.
    compile_calls = {"count": 0}

    def _stub(
        *,
        tex_text: str,
        variant_dir: Path,
        variant_name: str,
    ) -> tuple[Path, Path, int]:
        variant_dir.mkdir(parents=True, exist_ok=True)
        tex_path = variant_dir / f"{variant_name}.tex"
        pdf_path = variant_dir / f"{variant_name}.pdf"
        tex_path.write_text(tex_text, encoding="utf-8")
        pdf_path.write_text("pdf", encoding="utf-8")
        if variant_name == "tailored_v1":
            compile_calls["count"] += 1
            return tex_path, pdf_path, 2 if compile_calls["count"] == 1 else 1
        return tex_path, pdf_path, 1

    monkeypatch.setattr(pipeline_module, "call_tailor", _fake_tailor)
    monkeypatch.setattr(pipeline_module, "call_trim", _fake_trim)
    monkeypatch.setattr(pipeline_module, "call_reviewer", _fake_reviewer)
    monkeypatch.setattr(pipeline_module, "_write_and_compile_variant", _stub)

    result = await run_tailor_review_pipeline(
        db=db,
        tailor_run_id=tailor_run_id,
        job_hash=job_hash,
        base_resume_tex_path=resume_tex_fixture_path(),
        candidate_profile_yaml_path=_candidate_profile_yaml(tmp_path),
        output_dir=tmp_path / "out",
        record_costs=False,
    )

    assert result.success is True
    assert result.verdict == "TAILORED"
    assert compile_calls["count"] == 2  # trim forced a recompile


@pytest.mark.asyncio
async def test_page_overflow_persists_after_trim_yields_page_fit_failed(
    db: DatabaseManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_hash = "fail" * 10
    tailor_run_id = await _seed_pipeline_inputs(db, job_hash=job_hash)

    async def _fake_tailor(_message: str) -> Any:
        return make_tailor_result(bullets=[single_valid_patch_proposal()])

    async def _fake_trim(_message: str) -> Any:
        return make_tailor_result(
            bullets=[
                BulletPatchProposal(
                    id=single_valid_patch_proposal().id,
                    rationale="trim",
                    action="rewrite",
                    new_text="Still long enough to overflow.",
                )
            ]
        )

    monkeypatch.setattr(pipeline_module, "call_tailor", _fake_tailor)
    monkeypatch.setattr(pipeline_module, "call_trim", _fake_trim)
    monkeypatch.setattr(
        pipeline_module,
        "_write_and_compile_variant",
        _make_write_compile_stub(v1_pages=2),
    )

    result = await run_tailor_review_pipeline(
        db=db,
        tailor_run_id=tailor_run_id,
        job_hash=job_hash,
        base_resume_tex_path=resume_tex_fixture_path(),
        candidate_profile_yaml_path=_candidate_profile_yaml(tmp_path),
        output_dir=tmp_path / "out",
        record_costs=False,
    )

    assert result.success is True
    assert result.verdict == "PAGE_FIT_FAILED"
    assert result.selected_tex_path is not None
    assert "/base/" in result.selected_tex_path

    review_payload = json.loads(
        cast(
            str,
            (await db.get_review_runs_for_tailor_run(tailor_run_id))[0][
                "review_report_json"
            ],
        )
    )
    assert review_payload["reason"] == "page_fit_failed"
    assert review_payload["final_page_count"] == 2


@pytest.mark.asyncio
async def test_reviewer_base_better_triggers_retry_and_3way_picks_tailored(
    db: DatabaseManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_hash = "retr" * 10
    tailor_run_id = await _seed_pipeline_inputs(db, job_hash=job_hash)

    tailor_iter = iter(
        [
            make_tailor_result(bullets=[single_valid_patch_proposal()]),
            make_tailor_result(bullets=[single_valid_patch_proposal()]),
        ]
    )
    reviewer_iter = iter(
        [
            make_reviewer_result(
                verdict=ReviewerVerdict.BASE_BETTER,
                feedback_for_retry="be more specific",
            ),
            make_reviewer_result(verdict=ReviewerVerdict.TAILORED_BETTER),
        ]
    )

    async def _fake_tailor(_message: str) -> Any:
        return next(tailor_iter)

    async def _fake_reviewer(_message: str) -> Any:
        return next(reviewer_iter)

    monkeypatch.setattr(pipeline_module, "call_tailor", _fake_tailor)
    monkeypatch.setattr(pipeline_module, "call_reviewer", _fake_reviewer)
    monkeypatch.setattr(
        pipeline_module, "_write_and_compile_variant", _make_write_compile_stub()
    )

    result = await run_tailor_review_pipeline(
        db=db,
        tailor_run_id=tailor_run_id,
        job_hash=job_hash,
        base_resume_tex_path=resume_tex_fixture_path(),
        candidate_profile_yaml_path=_candidate_profile_yaml(tmp_path),
        output_dir=tmp_path / "out",
        record_costs=False,
    )

    assert result.success is True
    assert result.verdict == "TAILORED"

    review_payload = json.loads(
        cast(
            str,
            (await db.get_review_runs_for_tailor_run(tailor_run_id))[0][
                "review_report_json"
            ],
        )
    )
    assert review_payload["had_retry"] is True


@pytest.mark.asyncio
async def test_factuality_veto_keeps_base_after_retry(
    db: DatabaseManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Both reviewer calls flag factuality=0 on the tailored variant.
    # Even the 3-way retry can't salvage; the final verdict ships base.
    job_hash = "veto" * 10
    tailor_run_id = await _seed_pipeline_inputs(db, job_hash=job_hash)

    tailor_iter = iter(
        [
            make_tailor_result(bullets=[single_valid_patch_proposal()]),
            make_tailor_result(bullets=[single_valid_patch_proposal()]),
        ]
    )
    reviewer_iter = iter(
        [
            make_reviewer_result(
                verdict=ReviewerVerdict.BASE_BETTER,
                feedback_for_retry="hallucinated employer",
                factuality_tailored=0,
            ),
            make_reviewer_result(
                verdict=ReviewerVerdict.BASE_BETTER,
                feedback_for_retry="still hallucinated",
                factuality_tailored=0,
            ),
        ]
    )

    async def _fake_tailor(_message: str) -> Any:
        return next(tailor_iter)

    async def _fake_reviewer(_message: str) -> Any:
        return next(reviewer_iter)

    monkeypatch.setattr(pipeline_module, "call_tailor", _fake_tailor)
    monkeypatch.setattr(pipeline_module, "call_reviewer", _fake_reviewer)
    monkeypatch.setattr(
        pipeline_module, "_write_and_compile_variant", _make_write_compile_stub()
    )

    result = await run_tailor_review_pipeline(
        db=db,
        tailor_run_id=tailor_run_id,
        job_hash=job_hash,
        base_resume_tex_path=resume_tex_fixture_path(),
        candidate_profile_yaml_path=_candidate_profile_yaml(tmp_path),
        output_dir=tmp_path / "out",
        record_costs=False,
    )

    assert result.success is True
    assert result.verdict == "BASE"
    review_payload = json.loads(
        cast(
            str,
            (await db.get_review_runs_for_tailor_run(tailor_run_id))[0][
                "review_report_json"
            ],
        )
    )
    assert review_payload["scores_tailored"]["factuality"] == 0


@pytest.mark.asyncio
async def test_reviewer_no_meaningful_improvement_ships_base(
    db: DatabaseManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_hash = "noim" * 10
    tailor_run_id = await _seed_pipeline_inputs(db, job_hash=job_hash)

    async def _fake_tailor(_message: str) -> Any:
        return make_tailor_result(bullets=[single_valid_patch_proposal()])

    async def _fake_reviewer(_message: str) -> Any:
        return make_reviewer_result(verdict=ReviewerVerdict.NO_MEANINGFUL_IMPROVEMENT)

    monkeypatch.setattr(pipeline_module, "call_tailor", _fake_tailor)
    monkeypatch.setattr(pipeline_module, "call_reviewer", _fake_reviewer)
    monkeypatch.setattr(
        pipeline_module, "_write_and_compile_variant", _make_write_compile_stub()
    )

    result = await run_tailor_review_pipeline(
        db=db,
        tailor_run_id=tailor_run_id,
        job_hash=job_hash,
        base_resume_tex_path=resume_tex_fixture_path(),
        candidate_profile_yaml_path=_candidate_profile_yaml(tmp_path),
        output_dir=tmp_path / "out",
        record_costs=False,
    )

    assert result.success is True
    assert result.verdict == "NO_IMPROVEMENT"


@pytest.mark.asyncio
async def test_base_compile_failure_records_hard_failure(
    db: DatabaseManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_hash = "comp" * 10
    tailor_run_id = await _seed_pipeline_inputs(db, job_hash=job_hash)

    def _failing_compile(**_kwargs: Any) -> Any:
        raise RuntimeError("tectonic exploded")

    monkeypatch.setattr(pipeline_module, "_write_and_compile_variant", _failing_compile)

    result = await run_tailor_review_pipeline(
        db=db,
        tailor_run_id=tailor_run_id,
        job_hash=job_hash,
        base_resume_tex_path=resume_tex_fixture_path(),
        candidate_profile_yaml_path=_candidate_profile_yaml(tmp_path),
        output_dir=tmp_path / "out",
        record_costs=False,
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.startswith("base_compile_failed:")


@pytest.mark.asyncio
async def test_unhandled_exception_in_tailor_records_pipeline_failure(
    db: DatabaseManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_hash = "boom" * 10
    tailor_run_id = await _seed_pipeline_inputs(db, job_hash=job_hash)

    async def _exploding_tailor(_message: str) -> Any:
        raise RuntimeError("llm went sideways")

    monkeypatch.setattr(pipeline_module, "call_tailor", _exploding_tailor)
    monkeypatch.setattr(
        pipeline_module, "_write_and_compile_variant", _make_write_compile_stub()
    )

    result = await run_tailor_review_pipeline(
        db=db,
        tailor_run_id=tailor_run_id,
        job_hash=job_hash,
        base_resume_tex_path=resume_tex_fixture_path(),
        candidate_profile_yaml_path=_candidate_profile_yaml(tmp_path),
        output_dir=tmp_path / "out",
        record_costs=False,
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.startswith("pipeline_failed:")


@pytest.mark.asyncio
async def test_review_report_carries_skipped_bullets_and_rewrite_plan(
    db: DatabaseManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Confirm the new plan §4.7 review_report extension (rewrite_plan,
    # skipped_bullets) actually round-trips through the DB.
    job_hash = "skip" * 10
    tailor_run_id = await _seed_pipeline_inputs(db, job_hash=job_hash)

    manifest = build_minimal_bullet_manifest()
    skipped_id = manifest.sections[0].entries[0].bullets[-1].id

    async def _fake_tailor(_message: str) -> Any:
        return make_tailor_result(
            rewrite_plan="Sharpen the leading bullet; skip the trailer.",
            bullets=[single_valid_patch_proposal()],
            skipped_bullets=[SkippedBulletNote(id=skipped_id, reason="already strong")],
        )

    async def _fake_reviewer(_message: str) -> Any:
        return make_reviewer_result(verdict=ReviewerVerdict.TAILORED_BETTER)

    monkeypatch.setattr(pipeline_module, "call_tailor", _fake_tailor)
    monkeypatch.setattr(pipeline_module, "call_reviewer", _fake_reviewer)
    monkeypatch.setattr(
        pipeline_module, "_write_and_compile_variant", _make_write_compile_stub()
    )

    await run_tailor_review_pipeline(
        db=db,
        tailor_run_id=tailor_run_id,
        job_hash=job_hash,
        base_resume_tex_path=resume_tex_fixture_path(),
        candidate_profile_yaml_path=_candidate_profile_yaml(tmp_path),
        output_dir=tmp_path / "out",
        record_costs=False,
    )

    review_payload = json.loads(
        cast(
            str,
            (await db.get_review_runs_for_tailor_run(tailor_run_id))[0][
                "review_report_json"
            ],
        )
    )
    assert review_payload["rewrite_plan"] == "Sharpen the leading bullet; skip the trailer."
    assert review_payload["skipped_bullets"] == [
        {"id": skipped_id, "reason": "already strong"}
    ]
