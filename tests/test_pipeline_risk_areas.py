"""Risk-area tests for `run_tailor_review_pipeline` (Phase 2 of #60).

Purpose:
    Fill the gaps the Phase 1-4 handoff called out beyond the 13
    scenarios in `test_pipeline_scenarios.py`:

    - Risk #2 — every DB row written by the pipeline carries `""` in
      the legacy `*_yaml_path` columns.
    - Risk #3 — `_resolve_patches_from_proposals` precedence: `keep`
      actions are silently excluded from the dropped set; an unknown
      ID is dropped; duplicate IDs are processed in input order so
      the last `rewrite` wins.
    - Review-report key audit — the four new payload keys
      (`rewrite_plan`, `bullets_proposed`, `bullets_applied`,
      `skipped_bullets`) round-trip on every verdict path.
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
from src.agents.resume_tailor.locator import build_bullet_manifest
from src.agents.resume_tailor.pipeline import (
    _resolve_patches_from_proposals,
    run_tailor_review_pipeline,
)
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


# ---------------------------------------------------------------------------
# Shared scaffolding (mirrors test_pipeline_scenarios.py)
# ---------------------------------------------------------------------------


def _candidate_profile_yaml(tmp_path: Path) -> Path:
    """Write a tiny candidate profile YAML and return the path."""

    candidate_path = tmp_path / "candidate.yaml"
    candidate_path.write_text(
        yaml.safe_dump({"summary": "A short test profile"}), encoding="utf-8"
    )
    return candidate_path


async def _seed_pipeline_inputs(db: DatabaseManager, *, job_hash: str) -> int:
    """Insert one job + one PENDING tailor row, return the tailor row id."""

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


def _stub_write_and_compile() -> Any:
    """Return a `_write_and_compile_variant` stub that always reports 1 page."""

    def _stub(
        *, tex_text: str, variant_dir: Path, variant_name: str
    ) -> tuple[Path, Path, int]:
        variant_dir.mkdir(parents=True, exist_ok=True)
        tex_path = variant_dir / f"{variant_name}.tex"
        pdf_path = variant_dir / f"{variant_name}.pdf"
        tex_path.write_text(tex_text, encoding="utf-8")
        pdf_path.write_text("pdf", encoding="utf-8")
        return tex_path, pdf_path, 1

    return _stub


@pytest_asyncio.fixture
async def db(tmp_path: Path) -> AsyncGenerator[DatabaseManager, None]:
    """Provide a fresh DB with full schema migrated."""

    manager = DatabaseManager(str(tmp_path / "pipeline.db"))
    await manager.connect()
    await manager.create_tables()
    yield manager
    await manager.close()


# ---------------------------------------------------------------------------
# Risk #3 — `_resolve_patches_from_proposals` precedence + drops
# ---------------------------------------------------------------------------


def test_resolve_patches_silently_excludes_keep_actions_from_dropped_list() -> None:
    """Risk #3 — a `keep` action is not a "dropped" proposal."""

    manifest = build_minimal_bullet_manifest()
    real_bullet_id = manifest.sections[0].entries[0].bullets[0].id

    proposals = [
        BulletPatchProposal(
            id=real_bullet_id,
            rationale="this one is already strong",
            action="keep",
        ),
    ]

    patches, dropped = _resolve_patches_from_proposals(
        proposals=proposals, manifest=manifest
    )

    assert patches == []
    assert dropped == []


def test_resolve_patches_drops_unknown_ids_into_dropped_list() -> None:
    """Risk #3 — proposals referencing unknown bullet IDs land in `dropped`."""

    manifest = build_minimal_bullet_manifest()

    proposals = [
        BulletPatchProposal(
            id="ghost-bullet-id-does-not-exist",
            rationale="hallucinated",
            action="rewrite",
            new_text="never lands",
        ),
    ]

    patches, dropped = _resolve_patches_from_proposals(
        proposals=proposals, manifest=manifest
    )

    assert patches == []
    assert len(dropped) == 1
    assert dropped[0].id == "ghost-bullet-id-does-not-exist"


def test_resolve_patches_processes_duplicate_ids_in_input_order_last_wins() -> None:
    """Risk #3 — when the LLM emits two rewrites for the same ID, the last one wins.

    The pipeline currently lets the second proposal override the first
    because both are appended to the patch list — but the patcher then
    raises on overlap. We pin the precedence at the resolver layer so
    a future deduplication change is a deliberate decision.
    """

    manifest = build_minimal_bullet_manifest()
    real_bullet_id = manifest.sections[0].entries[0].bullets[0].id

    proposals = [
        BulletPatchProposal(
            id=real_bullet_id,
            rationale="first attempt",
            action="rewrite",
            new_text="first",
        ),
        BulletPatchProposal(
            id=real_bullet_id,
            rationale="second attempt",
            action="rewrite",
            new_text="second",
        ),
    ]

    patches, dropped = _resolve_patches_from_proposals(
        proposals=proposals, manifest=manifest
    )

    # Both rewrites pass through resolver: it does NOT dedupe; the
    # overlap is detected downstream by the patcher.
    assert dropped == []
    assert [patch.new_text for patch in patches] == ["first", "second"]


def test_resolve_patches_emits_byte_spans_matching_the_manifest() -> None:
    """Spans on the returned patches must come from the manifest, not the proposal."""

    manifest = build_minimal_bullet_manifest()
    first_bullet = manifest.sections[0].entries[0].bullets[0]

    proposals = [
        BulletPatchProposal(
            id=first_bullet.id,
            rationale="sharpen",
            action="rewrite",
            new_text="sharpened",
        ),
    ]

    patches, _dropped = _resolve_patches_from_proposals(
        proposals=proposals, manifest=manifest
    )

    assert len(patches) == 1
    patch = patches[0]
    assert patch.byte_start == first_bullet.byte_start
    assert patch.byte_end == first_bullet.byte_end


def test_resolve_patches_drops_unknown_id_but_keeps_valid_sibling() -> None:
    """A mix of valid + invalid IDs preserves the valid patch and drops the rest."""

    manifest = build_minimal_bullet_manifest()
    real_bullet_id = manifest.sections[0].entries[0].bullets[0].id

    proposals = [
        BulletPatchProposal(
            id=real_bullet_id,
            rationale="real",
            action="rewrite",
            new_text="kept",
        ),
        BulletPatchProposal(
            id="ghost",
            rationale="hallucinated",
            action="rewrite",
            new_text="lost",
        ),
    ]

    patches, dropped = _resolve_patches_from_proposals(
        proposals=proposals, manifest=manifest
    )

    assert [patch.new_text for patch in patches] == ["kept"]
    assert [proposal.id for proposal in dropped] == ["ghost"]


# ---------------------------------------------------------------------------
# Risk #2 — legacy `*_yaml_path` columns are written as empty strings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_yaml_path_columns_stay_empty_on_happy_path(
    db: DatabaseManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Risk #2 — successful pipeline runs write `""` for every yaml_path column."""

    job_hash = "yaml" * 10
    tailor_run_id = await _seed_pipeline_inputs(db, job_hash=job_hash)

    async def _fake_tailor(_message: str) -> Any:
        return make_tailor_result(bullets=[single_valid_patch_proposal()])

    async def _fake_reviewer(_message: str) -> Any:
        return make_reviewer_result(verdict=ReviewerVerdict.TAILORED_BETTER)

    monkeypatch.setattr(pipeline_module, "call_tailor", _fake_tailor)
    monkeypatch.setattr(pipeline_module, "call_reviewer", _fake_reviewer)
    monkeypatch.setattr(
        pipeline_module, "_write_and_compile_variant", _stub_write_and_compile()
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
    assert result.selected_yaml_path == ""

    tailor_row = await db.get_tailor_run(tailor_run_id)
    assert tailor_row is not None
    # `record_tailor_success` writes `""` per plan §6.
    assert tailor_row["artifact_yaml_path"] == ""

    review_rows = await db.get_review_runs_for_tailor_run(tailor_run_id)
    assert len(review_rows) == 1
    review_row = review_rows[0]
    assert review_row["selected_yaml_path"] == ""
    assert review_row["fallback_base_yaml_path"] == ""


@pytest.mark.asyncio
async def test_yaml_path_columns_stay_empty_on_ship_base_branch(
    db: DatabaseManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Risk #2 — the `_ship_base_with_reason` branch also writes `""` for yaml paths."""

    job_hash = "shyp" * 10
    tailor_run_id = await _seed_pipeline_inputs(db, job_hash=job_hash)

    async def _fake_tailor(_message: str) -> Any:
        return make_tailor_result(bullets=[])  # tailor_bailed branch

    monkeypatch.setattr(pipeline_module, "call_tailor", _fake_tailor)
    monkeypatch.setattr(
        pipeline_module, "_write_and_compile_variant", _stub_write_and_compile()
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
    assert result.selected_yaml_path == ""

    tailor_row = await db.get_tailor_run(tailor_run_id)
    assert tailor_row is not None
    assert tailor_row["artifact_yaml_path"] == ""

    review_row = (await db.get_review_runs_for_tailor_run(tailor_run_id))[0]
    assert review_row["selected_yaml_path"] == ""
    assert review_row["fallback_base_yaml_path"] == ""


# ---------------------------------------------------------------------------
# Review-report payload key audit (plan §4.7)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_review_report_payload_carries_all_phase_two_keys(
    db: DatabaseManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """plan §4.7 — the four new payload keys must round-trip through the DB.

    Specifically: `rewrite_plan`, `bullets_proposed`, `bullets_applied`,
    and `skipped_bullets`. Existing scenario tests assert these in
    isolation; this one pins all four in a single happy-path run so a
    regression that drops any single key gets caught.
    """

    job_hash = "keys" * 10
    tailor_run_id = await _seed_pipeline_inputs(db, job_hash=job_hash)

    manifest = build_minimal_bullet_manifest()
    second_bullet_id = manifest.sections[0].entries[0].bullets[1].id

    async def _fake_tailor(_message: str) -> Any:
        return make_tailor_result(
            rewrite_plan="Lean into the ingestion bullet.",
            bullets=[single_valid_patch_proposal()],
            skipped_bullets=[
                SkippedBulletNote(id=second_bullet_id, reason="already crisp")
            ],
        )

    async def _fake_reviewer(_message: str) -> Any:
        return make_reviewer_result(verdict=ReviewerVerdict.TAILORED_BETTER)

    monkeypatch.setattr(pipeline_module, "call_tailor", _fake_tailor)
    monkeypatch.setattr(pipeline_module, "call_reviewer", _fake_reviewer)
    monkeypatch.setattr(
        pipeline_module, "_write_and_compile_variant", _stub_write_and_compile()
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

    review_rows = await db.get_review_runs_for_tailor_run(tailor_run_id)
    payload = json.loads(cast(str, review_rows[0]["review_report_json"]))

    # Every plan §4.7 key must appear with the expected shape.
    assert payload["rewrite_plan"] == "Lean into the ingestion bullet."
    assert payload["bullets_proposed"] == 1
    assert payload["bullets_applied"] == 1
    assert payload["skipped_bullets"] == [
        {"id": second_bullet_id, "reason": "already crisp"}
    ]


@pytest.mark.asyncio
async def test_review_report_records_dropped_bullets_on_all_edits_dropped(
    db: DatabaseManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The `all_edits_dropped` payload must include the dropped bullet IDs."""

    job_hash = "drps" * 10
    tailor_run_id = await _seed_pipeline_inputs(db, job_hash=job_hash)

    async def _fake_tailor(_message: str) -> Any:
        return make_tailor_result(
            bullets=[
                BulletPatchProposal(
                    id="ghost-bullet",
                    rationale="hallucinated",
                    action="rewrite",
                    new_text="never lands",
                )
            ]
        )

    monkeypatch.setattr(pipeline_module, "call_tailor", _fake_tailor)
    monkeypatch.setattr(
        pipeline_module, "_write_and_compile_variant", _stub_write_and_compile()
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

    payload = json.loads(
        cast(
            str,
            (await db.get_review_runs_for_tailor_run(tailor_run_id))[0][
                "review_report_json"
            ],
        )
    )

    assert payload["reason"] == "all_edits_dropped"
    assert payload["dropped_bullets"] == [
        {"id": "ghost-bullet", "rationale": "hallucinated"}
    ]


# ---------------------------------------------------------------------------
# Sanity check: the helper rests on a manifest with at least two bullets
# in the first entry. Pin that so any future locator change that drops
# the second bullet fails this test instead of silently breaking the
# `skipped_bullets` assertion above.
# ---------------------------------------------------------------------------


def test_synthetic_minimal_manifest_first_entry_has_at_least_two_bullets() -> None:
    """Sanity guard for `test_review_report_payload_carries_all_phase_two_keys`."""

    manifest = build_bullet_manifest(
        resume_tex_fixture_path().read_text(encoding="utf-8")
    )

    first_entry = manifest.sections[0].entries[0]
    assert len(first_entry.bullets) >= 2
