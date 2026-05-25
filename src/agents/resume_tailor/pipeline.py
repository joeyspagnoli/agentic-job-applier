"""Orchestrator for the tailor → patch → compile → reviewer → pick pipeline.

Public entry point: `run_tailor_review_pipeline`. Both the worker
daemon (`scripts/process_qualified_jobs.py`) and the API
BackgroundTasks path (`POST /api/jobs/{hash}/tailor`) call this same
function. Each LLM stage is one structured Instructor call validated
against a Pydantic schema (see `pipeline_schemas.py`).

Phase 2 (#60) replaced the YAML-edit-list flow with a `.tex`
manifest + byte-offset patcher flow. Stages, in order (plan §7):

 1. Mark the tailor run RUNNING.
 2. Load job context.
 3. Read + re-validate the user's `.tex` (skip compile check — Phase 0
    enforced it at upload time; we just guard against drift).
 4. Compile the base PDF.
 5. Build the deterministic bullet manifest.
 6. Tailor LLM call → `TailorOutput`.
 7. Resolve patches, sanitize, apply via `patcher.apply_patches`.
 8. Compile tailored_v1 PDF.
 9. Page-fit retry: one trim LLM call when >1 page; still >1 page →
    verdict=PAGE_FIT_FAILED, ship base, return.
10. Zero applicable edits → verdict=NO_IMPROVEMENT, ship base, return.
11. Reviewer LLM call (single, rubric + factuality veto).
12. If verdict=base_better → re-tailor with feedback once → re-apply
    → recompile → 3-way reviewer.
13. Persist tailor_runs + review_runs.

The on-disk `.tex` is never mutated by a tailor run — every patched
variant lives in a per-run artifact dir.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import yaml
from loguru import logger

from src.database.db_manager import DatabaseManager
from src.providers.types import CompletionResponse
from src.utils.cost_tracking import (
    PIPELINE_STAGE_REVIEW,
    PIPELINE_STAGE_TAILOR,
    record_llm_call_cost,
)

from .compiler import compile_resume_tex, get_pdf_page_count
from .db_verdict import DBReviewVerdict
from .jd_enricher import _maybe_enrich_job_description
from .llm import (
    LlmCallResult,
    call_reviewer,
    call_tailor,
    call_trim,
)
from .locator import build_bullet_manifest
from .manifest import BulletManifest
from .patcher import BulletPatch, apply_patches, write_patched_tex_atomically
from .pipeline_schemas import (
    BulletPatchProposal,
    ReviewerOutput,
    ReviewerScores,
    ReviewerVerdict,
    TailorOutput,
    TailorRunResult,
)
from .validator import validate_resume_tex

PAGE_LIMIT = 1
BASE_VARIANT_NAME = "base"
TAILORED_V1_VARIANT_NAME = "tailored_v1"
TAILORED_V2_VARIANT_NAME = "tailored_v2"


def _format_candidate_profile_snippet(profile_yaml_path: Path) -> str:
    """Read candidate profile YAML into a short prompt snippet.

    Purpose:
        Give the tailor model a compact summary of the candidate's
        strongest areas and experience highlights without dumping the
        full profile document.
    Args:
        profile_yaml_path: Filesystem path to
            `config/candidate_profile.yaml`.
    Output:
        YAML-formatted string slice containing the profile, truncated
        to a safe size for the prompt context.
    """

    if not profile_yaml_path.exists():
        return "(no candidate profile available)"
    with open(profile_yaml_path, "r", encoding="utf-8") as profile_file:
        loaded = yaml.safe_load(profile_file) or {}
    # The full file is small in this repo; safe to embed verbatim.
    return yaml.safe_dump(loaded, sort_keys=False, allow_unicode=False)


def _format_job_snippet(job_row: dict[str, Any]) -> str:
    """Render one job row into a prompt-friendly text block.

    Purpose:
        Keep job context compact and deterministic across agents.
    Args:
        job_row: Mapping of job_postings columns for the target job.
    Output:
        Multi-line text block bracketed by `<job_posting>` tags so the
        model treats it as untrusted content.
    """

    fields = (
        f"title: {job_row.get('title') or ''}",
        f"company: {job_row.get('company') or ''}",
        f"location: {job_row.get('location') or ''}",
        f"is_remote: {job_row.get('is_remote')}",
        f"job_type: {job_row.get('job_type') or ''}",
        f"description:\n{job_row.get('description') or ''}",
        f"requirements:\n{job_row.get('requirements') or ''}",
    )
    body = "\n".join(fields)
    return f"<job_posting>\n{body}\n</job_posting>"


def _load_user_tex(tex_path: Path) -> str:
    """Read the user's `.tex` file from disk.

    Purpose:
        Centralize the read so the read site can be monkeypatched in
        tests and so errors carry a meaningful path in the message.
    Args:
        tex_path: Filesystem path to the user's `config/resume.tex`.
    Output:
        Raw `.tex` text.
    Raises:
        FileNotFoundError: When the path does not exist.
    """

    return Path(tex_path).read_text(encoding="utf-8")


def _format_manifest_block(manifest: BulletManifest) -> str:
    """Render a `BulletManifest` as a JSON block for the tailor prompt.

    Purpose:
        Give the LLM a compact view of every bullet it may rewrite +
        the entry header it lives under. The `byte_start` / `byte_end`
        offsets are included only as informational hints — the LLM
        emits IDs, never offsets.
    Args:
        manifest: Manifest emitted by `build_bullet_manifest`.
    Output:
        JSON text inside a `<bullet_manifest>` tag.
    """

    payload = manifest.model_dump(mode="json")
    body = json.dumps(payload, indent=2, ensure_ascii=False)
    return f"<bullet_manifest>\n{body}\n</bullet_manifest>"


def _format_tex_variant(*, label: str, tex_text: str) -> str:
    """Wrap one `.tex` variant in a labeled block for the reviewer.

    Purpose:
        Reviewer prompts compare 2 or 3 variants side-by-side. The
        labeled tag makes the boundary obvious without leaking the
        prompt into the model's reasoning.
    Args:
        label: Tag label (`base`, `tailored_v1`, `tailored_v2`).
        tex_text: Full `.tex` text of the variant.
    Output:
        `<resume label="...">{tex}</resume>` block.
    """

    return f'<resume label="{label}">\n{tex_text}\n</resume>'


def _build_tailor_message(
    *,
    job_block: str,
    manifest: BulletManifest,
    candidate_profile_text: str,
    retry_feedback: Optional[str] = None,
) -> str:
    """Assemble the tailor agent's user-role message.

    Purpose:
        Keep prompt assembly out of `run_tailor_review_pipeline` so
        the orchestrator stays focused on control flow.
    Args:
        job_block: Pre-formatted `<job_posting>` block.
        manifest: Bullet manifest the tailor may edit.
        candidate_profile_text: YAML candidate profile snippet.
        retry_feedback: Optional reviewer feedback that drives a
            re-tailor attempt.
    Output:
        Assembled user-role message text.
    """

    sections = [
        job_block,
        f"<candidate_profile>\n{candidate_profile_text}\n</candidate_profile>",
        _format_manifest_block(manifest),
    ]
    if retry_feedback:
        sections.append(
            "<retry_feedback>\n"
            "Your previous attempt was rated weaker than the base resume. "
            "Address this critique:\n"
            f"{retry_feedback}\n"
            "</retry_feedback>"
        )
    return "\n\n".join(sections)


def _build_trim_message(
    *,
    job_block: str,
    manifest: BulletManifest,
    measured_page_count: int,
) -> str:
    """Assemble the trim agent's user-role message.

    Purpose:
        Tell the trim agent how far over the page budget the current
        variant is so it doesn't over-trim.
    Args:
        job_block: Pre-formatted `<job_posting>` block.
        manifest: Manifest built from the overflowing tailored `.tex`.
        measured_page_count: Page count of the overflowing variant.
    Output:
        Assembled user-role message text.
    """

    return "\n\n".join(
        (
            job_block,
            _format_manifest_block(manifest),
            f"<overflow>\nMeasured page count: {measured_page_count}. "
            f"Trim to {PAGE_LIMIT} page.\n</overflow>",
        )
    )


def _build_reviewer_message(
    *,
    job_block: str,
    base_tex: str,
    tailored_v1_tex: str,
    tailored_v2_tex: Optional[str],
    feedback_for_retry: Optional[str],
) -> str:
    """Assemble the reviewer prompt body covering 2 or 3 `.tex` variants.

    Purpose:
        Keep the reviewer stateless — the prompt body carries every
        variant and any retry feedback. The verdict semantics differ
        for 2-way and 3-way comparisons; the prompt makes the count
        explicit.
    Args:
        job_block: Pre-formatted `<job_posting>` block.
        base_tex: Base `.tex` text.
        tailored_v1_tex: First tailor attempt `.tex` text.
        tailored_v2_tex: Optional second tailor attempt `.tex` text.
        feedback_for_retry: Optional feedback that motivated the retry.
    Output:
        Assembled user-role message text.
    """

    parts: list[str] = [
        job_block,
        _format_tex_variant(label="base", tex_text=base_tex),
        _format_tex_variant(label="tailored_v1", tex_text=tailored_v1_tex),
    ]
    if tailored_v2_tex is not None:
        parts.append(_format_tex_variant(label="tailored_v2", tex_text=tailored_v2_tex))
        if feedback_for_retry:
            parts.append(
                "<retry_feedback>\n"
                f"{feedback_for_retry}\n"
                "</retry_feedback>"
            )
        parts.append(
            "Compare base, tailored_v1, and tailored_v2. Pick the strongest. "
            "Do not use base_better for a 3-way comparison."
        )
    else:
        parts.append("Compare base and tailored_v1. Pick the better one.")
    return "\n\n".join(parts)


def _resolve_patches_from_proposals(
    *,
    proposals: list[BulletPatchProposal],
    manifest: BulletManifest,
) -> tuple[list[BulletPatch], list[BulletPatchProposal]]:
    """Map tailor-LLM proposals onto byte-offset patches via the manifest.

    Purpose:
        The tailor emits bullet IDs; the patcher needs `(byte_start,
        byte_end)`. This lookup also drops proposals that reference
        unknown IDs or `keep` actions, returning the dropped set so
        the pipeline can record `all_edits_dropped` distinctly from
        `tailor_bailed`.
    Args:
        proposals: Per-bullet decisions emitted by the tailor LLM.
        manifest: Manifest the IDs were drawn from.
    Output:
        Tuple `(patches, dropped_proposals)`. `patches` covers only
        proposals with `action="rewrite"` whose ID matched a manifest
        bullet. `dropped_proposals` contains everything else (unknown
        IDs only — `keep` actions are intentionally excluded from the
        dropped list since they're not edits).
    """

    bullet_index: dict[str, tuple[int, int]] = {}
    for section in manifest.sections:
        for entry in section.entries:
            for bullet in entry.bullets:
                bullet_index[bullet.id] = (bullet.byte_start, bullet.byte_end)

    patches: list[BulletPatch] = []
    dropped: list[BulletPatchProposal] = []
    for proposal in proposals:
        if proposal.action != "rewrite":
            continue
        span = bullet_index.get(proposal.id)
        if span is None:
            logger.warning(
                "Tailor proposal references unknown bullet id {!r}; dropping",
                proposal.id,
            )
            dropped.append(proposal)
            continue
        byte_start, byte_end = span
        patches.append(
            BulletPatch(
                bullet_id=proposal.id,
                byte_start=byte_start,
                byte_end=byte_end,
                new_text=proposal.new_text,
            )
        )

    return patches, dropped


def _write_and_compile_variant(
    *,
    tex_text: str,
    variant_dir: Path,
    variant_name: str,
) -> tuple[Path, Path, int]:
    """Write `tex_text` to `variant_dir/<name>.tex` and compile to PDF.

    Purpose:
        Centralize the per-variant file output so the orchestrator's
        control flow stays readable.
    Args:
        tex_text: Patched `.tex` text to write.
        variant_dir: Directory that holds the variant's artifacts.
        variant_name: Filename stem (e.g. `tailored_v1`).
    Output:
        Tuple `(tex_path, pdf_path, page_count)`.
    """

    variant_dir.mkdir(parents=True, exist_ok=True)
    tex_path = variant_dir / f"{variant_name}.tex"
    pdf_path = variant_dir / f"{variant_name}.pdf"

    write_patched_tex_atomically(tex_text=tex_text, target_path=tex_path)
    compile_resume_tex(tex_path=tex_path, pdf_output_path=pdf_path)
    log_path = tex_path.with_suffix(".log")
    page_count = get_pdf_page_count(pdf_path=pdf_path, log_path=log_path)
    return tex_path, pdf_path, page_count


def _select_final_variant(
    *,
    verdict: ReviewerVerdict,
    base_artifacts: tuple[Path, Path],
    tailored_artifacts: tuple[Path, Path],
) -> tuple[str, tuple[Path, Path]]:
    """Resolve the reviewer verdict into a stored verdict + artifact pair.

    Purpose:
        Keep the verdict-to-artifact mapping centralized so the DB
        write path is straightforward.
    Args:
        verdict: Reviewer's verdict enum.
        base_artifacts: `(tex, pdf)` paths for the base variant.
        tailored_artifacts: `(tex, pdf)` paths for the chosen tailored
            variant.
    Output:
        Tuple `(db_verdict_string, (tex, pdf))` for persistence.
    """

    if verdict == ReviewerVerdict.TAILORED_BETTER:
        return DBReviewVerdict.TAILORED.value, tailored_artifacts
    if verdict == ReviewerVerdict.BASE_BETTER:
        return DBReviewVerdict.BASE.value, base_artifacts
    return DBReviewVerdict.NO_IMPROVEMENT.value, base_artifacts


async def _record_cost(
    *,
    db: DatabaseManager,
    stage: str,
    job_hash: str,
    tailor_run_id: int,
    phase: str,
    call_result: LlmCallResult[Any],
) -> None:
    """Best-effort wrapper around `record_llm_call_cost`.

    Purpose:
        Cost recording is observational — never let a recording
        failure kill a real pipeline run. Token usage and cost flow in
        from the Instructor result so per-call metadata stays accurate
        without a second provider round-trip. A synthetic
        `CompletionResponse` is built from the `LlmCallResult` fields so
        `record_llm_call_cost` can persist the full cost breakdown.
    Args:
        db: Connected database manager.
        stage: Pipeline stage constant (`TAILOR` or `REVIEW`).
        job_hash: Stable job identifier.
        tailor_run_id: Owning tailor run primary key.
        phase: Short label distinguishing tailor / trim / retailor /
            two_way / three_way for analytics.
        call_result: Result of the Instructor call whose tokens are
            being recorded.
    Output:
        Returns `None`; errors are logged and swallowed.
    """

    try:
        # Derive the provider name from the qualified model prefix so the
        # recorder carries the right string without an extra import.
        provider_name = call_result.model.split("/")[0] if "/" in call_result.model else "openai"
        synthetic_response = CompletionResponse(
            content="",
            model=call_result.model,
            provider=provider_name,
            usage=call_result.usage,
            cost=call_result.cost,
        )
        await record_llm_call_cost(
            db=db,
            stage=stage,
            run_id=str(tailor_run_id),
            phase=phase,
            response=synthetic_response,
            job_hash=job_hash,
        )
    except Exception as exc:
        logger.warning("Cost recording failed (stage={}): {}", stage, exc)


async def run_tailor_review_pipeline(
    *,
    db: DatabaseManager,
    tailor_run_id: int,
    job_hash: str,
    base_resume_tex_path: str | Path,
    candidate_profile_yaml_path: str | Path,
    output_dir: str | Path,
    record_costs: bool = True,
) -> TailorRunResult:
    """Run the full tailor → patch → compile → reviewer → pick pipeline.

    Purpose:
        Single entry point used by both the autonomous worker daemon
        and the opt-in API BackgroundTask. The function owns every DB
        write for the run: marking the tailor row RUNNING, writing the
        artifact paths on success, recording the failure on hard
        errors, and inserting the matching review_runs row.
    Args:
        db: Connected database manager (already inside a context manager).
        tailor_run_id: Primary key of the PENDING tailor_runs row.
        job_hash: Stable job identifier.
        base_resume_tex_path: Path to the user's resume — interpreted
            as a `.tex` file in Phase 2+ (the kwarg name keeps the old
            spelling until Phase 3 renames it across callers).
        candidate_profile_yaml_path: Path to
            `config/candidate_profile.yaml`.
        output_dir: Per-run artifact directory; each variant gets a
            subdir.
        record_costs: When `True`, emit per-stage cost events.
    Output:
        Populated `TailorRunResult`.
    """

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    tex_path = Path(base_resume_tex_path)

    await db.mark_tailor_running(run_id=tailor_run_id)

    job_row = await db.get_resume_tailor_job_context(job_hash=job_hash)
    if job_row is None:
        return await _fail_run(
            db=db,
            tailor_run_id=tailor_run_id,
            job_hash=job_hash,
            error_message=f"job_not_found: {job_hash}",
        )

    # Opportunistic JD backfill for LinkedIn/iCIMS rows whose
    # discovery adapter only stored a placeholder or empty string.
    # The helper swallows every fetch failure and falls back to the
    # original row — by contract the tailor run continues either way.
    job_row = await _maybe_enrich_job_description(
        db=db,
        job_row=job_row,
        job_hash=job_hash,
    )

    # Load + re-validate the user's .tex. Phase 0 enforced the contract
    # at upload time, but we guard against on-disk drift between upload
    # and tailor run. The compile check is skipped — Phase 1's compiler
    # runs against the base PDF a few lines below and would catch any
    # compile-time failure anyway.
    try:
        base_tex_text = _load_user_tex(tex_path)
    except Exception as exc:
        return await _fail_run(
            db=db,
            tailor_run_id=tailor_run_id,
            job_hash=job_hash,
            error_message=f"base_resume_load_failed: {exc}",
        )

    contract_report = validate_resume_tex(base_tex_text, run_compile_check=False)
    if not contract_report.ok:
        codes = ",".join(error.code for error in contract_report.errors)
        return await _fail_run(
            db=db,
            tailor_run_id=tailor_run_id,
            job_hash=job_hash,
            error_message=f"invalid_resume_tex_at_runtime: {codes}",
        )

    candidate_profile_text = _format_candidate_profile_snippet(
        Path(candidate_profile_yaml_path)
    )
    job_block = _format_job_snippet(job_row)

    # Compile the base PDF first so the DB row always has an artifact
    # to fall back to if every later stage fails.
    base_variant_dir = output_dir / BASE_VARIANT_NAME
    try:
        base_tex_artifact, base_pdf_artifact, _ = _write_and_compile_variant(
            tex_text=base_tex_text,
            variant_dir=base_variant_dir,
            variant_name=BASE_VARIANT_NAME,
        )
    except Exception as exc:
        return await _fail_run(
            db=db,
            tailor_run_id=tailor_run_id,
            job_hash=job_hash,
            error_message=f"base_compile_failed: {exc}",
        )

    base_artifacts: tuple[Path, Path] = (base_tex_artifact, base_pdf_artifact)
    base_manifest = build_bullet_manifest(base_tex_text)

    try:
        tailor_message = _build_tailor_message(
            job_block=job_block,
            manifest=base_manifest,
            candidate_profile_text=candidate_profile_text,
        )
        tailor_call = await call_tailor(tailor_message)
        if record_costs:
            await _record_cost(
                db=db,
                stage=PIPELINE_STAGE_TAILOR,
                job_hash=job_hash,
                tailor_run_id=tailor_run_id,
                phase="tailor",
                call_result=tailor_call,
            )
        tailor_output: TailorOutput = tailor_call.parsed

        bullets_proposed_v1 = sum(
            1 for proposal in tailor_output.bullets if proposal.action == "rewrite"
        )
        v1_patches, v1_dropped = _resolve_patches_from_proposals(
            proposals=tailor_output.bullets,
            manifest=base_manifest,
        )

        if not v1_patches:
            # Distinguish "tailor proposed nothing" from "tailor
            # proposed rewrites but every ID was unknown and got
            # dropped". Same DB verdict either way (NO_IMPROVEMENT)
            # but different reason in the review_report.
            bail_reason = (
                "tailor_bailed" if bullets_proposed_v1 == 0 else "all_edits_dropped"
            )
            return await _ship_base_with_reason(
                db=db,
                tailor_run_id=tailor_run_id,
                job_hash=job_hash,
                base_tex_path=base_tex_artifact,
                base_pdf_path=base_pdf_artifact,
                review_payload={
                    "reason": bail_reason,
                    "rewrite_plan": tailor_output.rewrite_plan,
                    "bullets_proposed": bullets_proposed_v1,
                    "bullets_applied": 0,
                    "skipped_bullets": [
                        note.model_dump() for note in tailor_output.skipped_bullets
                    ],
                    "dropped_bullets": [
                        {"id": dropped.id, "rationale": dropped.rationale}
                        for dropped in v1_dropped
                    ],
                },
                verdict=DBReviewVerdict.NO_IMPROVEMENT.value,
                page_count=PAGE_LIMIT,
            )

        v1_tex_text = apply_patches(base_tex_text, v1_patches)
        v1_dir = output_dir / TAILORED_V1_VARIANT_NAME
        (
            v1_tex_artifact,
            v1_pdf_artifact,
            v1_page_count,
        ) = _write_and_compile_variant(
            tex_text=v1_tex_text,
            variant_dir=v1_dir,
            variant_name=TAILORED_V1_VARIANT_NAME,
        )

        # Page-fit trim pass — at most one extra LLM call.
        if v1_page_count > PAGE_LIMIT:
            trim_manifest = build_bullet_manifest(v1_tex_text)
            trim_message = _build_trim_message(
                job_block=job_block,
                manifest=trim_manifest,
                measured_page_count=v1_page_count,
            )
            trim_call = await call_trim(trim_message)
            if record_costs:
                await _record_cost(
                    db=db,
                    stage=PIPELINE_STAGE_TAILOR,
                    job_hash=job_hash,
                    tailor_run_id=tailor_run_id,
                    phase="trim",
                    call_result=trim_call,
                )
            trim_output: TailorOutput = trim_call.parsed
            trim_patches, _ = _resolve_patches_from_proposals(
                proposals=trim_output.bullets,
                manifest=trim_manifest,
            )
            if trim_patches:
                v1_tex_text = apply_patches(v1_tex_text, trim_patches)
                (
                    v1_tex_artifact,
                    v1_pdf_artifact,
                    v1_page_count,
                ) = _write_and_compile_variant(
                    tex_text=v1_tex_text,
                    variant_dir=v1_dir,
                    variant_name=TAILORED_V1_VARIANT_NAME,
                )

        if v1_page_count > PAGE_LIMIT:
            return await _ship_base_with_reason(
                db=db,
                tailor_run_id=tailor_run_id,
                job_hash=job_hash,
                base_tex_path=base_tex_artifact,
                base_pdf_path=base_pdf_artifact,
                review_payload={
                    "reason": "page_fit_failed",
                    "final_page_count": v1_page_count,
                },
                verdict=DBReviewVerdict.PAGE_FIT_FAILED.value,
                page_count=v1_page_count,
                # The base row in tailor_runs should still point at the
                # tailored artifact for debugging, even though we serve
                # the base PDF.
                artifact_tex_override=v1_tex_artifact,
                artifact_pdf_override=v1_pdf_artifact,
            )

        # Reviewer — 2-way base vs v1.
        reviewer_message = _build_reviewer_message(
            job_block=job_block,
            base_tex=base_tex_text,
            tailored_v1_tex=v1_tex_text,
            tailored_v2_tex=None,
            feedback_for_retry=None,
        )
        reviewer_call = await call_reviewer(reviewer_message)
        if record_costs:
            await _record_cost(
                db=db,
                stage=PIPELINE_STAGE_REVIEW,
                job_hash=job_hash,
                tailor_run_id=tailor_run_id,
                phase="two_way",
                call_result=reviewer_call,
            )
        reviewer_output: ReviewerOutput = reviewer_call.parsed

        v2_tex_text: Optional[str] = None
        v2_artifacts: Optional[tuple[Path, Path]] = None
        v2_page_count: Optional[int] = None

        # Re-tailor at most once when reviewer prefers the base resume.
        if reviewer_output.verdict == ReviewerVerdict.BASE_BETTER:
            feedback = (
                reviewer_output.feedback_for_retry or reviewer_output.rationale
            )
            retry_message = _build_tailor_message(
                job_block=job_block,
                manifest=base_manifest,
                candidate_profile_text=candidate_profile_text,
                retry_feedback=feedback,
            )
            retry_call = await call_tailor(retry_message)
            if record_costs:
                await _record_cost(
                    db=db,
                    stage=PIPELINE_STAGE_TAILOR,
                    job_hash=job_hash,
                    tailor_run_id=tailor_run_id,
                    phase="retailor",
                    call_result=retry_call,
                )
            retry_output: TailorOutput = retry_call.parsed
            retry_patches, _ = _resolve_patches_from_proposals(
                proposals=retry_output.bullets,
                manifest=base_manifest,
            )
            if retry_patches:
                candidate_v2_tex = apply_patches(base_tex_text, retry_patches)
                v2_dir = output_dir / TAILORED_V2_VARIANT_NAME
                (
                    v2_tex_artifact,
                    v2_pdf_artifact,
                    v2_page_count,
                ) = _write_and_compile_variant(
                    tex_text=candidate_v2_tex,
                    variant_dir=v2_dir,
                    variant_name=TAILORED_V2_VARIANT_NAME,
                )
                if v2_page_count <= PAGE_LIMIT:
                    v2_tex_text = candidate_v2_tex
                    v2_artifacts = (v2_tex_artifact, v2_pdf_artifact)

        # If a usable v2 exists, run a 3-way reviewer pass.
        if v2_tex_text is not None and v2_artifacts is not None:
            three_way_message = _build_reviewer_message(
                job_block=job_block,
                base_tex=base_tex_text,
                tailored_v1_tex=v1_tex_text,
                tailored_v2_tex=v2_tex_text,
                feedback_for_retry=reviewer_output.feedback_for_retry,
            )
            three_way_call = await call_reviewer(three_way_message)
            if record_costs:
                await _record_cost(
                    db=db,
                    stage=PIPELINE_STAGE_REVIEW,
                    job_hash=job_hash,
                    tailor_run_id=tailor_run_id,
                    phase="three_way",
                    call_result=three_way_call,
                )
            three_way_output: ReviewerOutput = three_way_call.parsed
            final_verdict = three_way_output.verdict
            final_scores_base = three_way_output.scores_base
            final_scores_tailored = three_way_output.scores_tailored
            final_rationale = three_way_output.rationale
            tailored_artifacts: tuple[Path, Path] = v2_artifacts
            tailored_page_count = v2_page_count or v1_page_count
        else:
            final_verdict = reviewer_output.verdict
            final_scores_base = reviewer_output.scores_base
            final_scores_tailored = reviewer_output.scores_tailored
            final_rationale = reviewer_output.rationale
            tailored_artifacts = (v1_tex_artifact, v1_pdf_artifact)
            tailored_page_count = v1_page_count

        db_verdict, selected_artifacts = _select_final_variant(
            verdict=final_verdict,
            base_artifacts=base_artifacts,
            tailored_artifacts=tailored_artifacts,
        )
        selected_tex, selected_pdf = selected_artifacts

        review_report_payload = {
            "verdict": final_verdict.value,
            "scores_base": final_scores_base.model_dump(),
            "scores_tailored": final_scores_tailored.model_dump(),
            "rationale": final_rationale,
            "rewrite_plan": tailor_output.rewrite_plan,
            "had_retry": v2_tex_text is not None,
            "bullets_proposed": bullets_proposed_v1,
            "bullets_applied": len(v1_patches),
            "skipped_bullets": [
                note.model_dump() for note in tailor_output.skipped_bullets
            ],
        }

        # YAML-path columns are semantically dead in Phase 2+; write
        # empty strings per plan §6 and let the future cleanup PR drop
        # the columns. Tex + PDF paths are the live source of truth.
        review_run_id = await db.insert_pipeline_review_run(
            job_hash=job_hash,
            tailor_run_id=tailor_run_id,
            verdict=db_verdict,
            selected_yaml_path="",
            selected_tex_path=str(selected_tex),
            selected_pdf_path=str(selected_pdf),
            review_report_json=json.dumps(review_report_payload),
            fallback_base_yaml_path="",
            fallback_base_tex_path=str(base_tex_artifact),
            fallback_base_pdf_path=str(base_pdf_artifact),
        )

        await db.record_tailor_success(
            run_id=tailor_run_id,
            artifact_yaml_path="",
            artifact_tex_path=str(tailored_artifacts[0]),
            artifact_pdf_path=str(tailored_artifacts[1]),
            page_count=tailored_page_count,
        )

        return TailorRunResult(
            success=True,
            job_hash=job_hash,
            tailor_run_id=tailor_run_id,
            review_run_id=review_run_id,
            verdict=db_verdict,
            selected_pdf_path=str(selected_pdf),
            selected_yaml_path="",
            selected_tex_path=str(selected_tex),
            page_count=tailored_page_count,
            scores_base=final_scores_base,
            scores_tailored=final_scores_tailored,
        )
    except Exception as exc:
        error_message = f"pipeline_failed: {exc}"
        logger.exception("Tailor pipeline failed for job {}", job_hash)
        await db.record_tailor_failure(
            run_id=tailor_run_id,
            error=error_message[:2000],
            next_retry_at=None,
        )
        return TailorRunResult(
            success=False,
            job_hash=job_hash,
            tailor_run_id=tailor_run_id,
            error=error_message,
        )


async def _fail_run(
    *,
    db: DatabaseManager,
    tailor_run_id: int,
    job_hash: str,
    error_message: str,
) -> TailorRunResult:
    """Record a hard failure on the tailor row and return the result.

    Purpose:
        Shared early-exit path so the orchestrator stays linear. Used
        for missing job rows, missing/invalid `.tex`, and compile
        failures on the base variant.
    Args:
        db: Connected database manager.
        tailor_run_id: Owning tailor run primary key.
        job_hash: Stable job identifier.
        error_message: Short error code + detail to persist.
    Output:
        Populated `TailorRunResult` with `success=False`.
    """

    await db.record_tailor_failure(
        run_id=tailor_run_id,
        error=error_message[:2000],
        next_retry_at=None,
    )
    return TailorRunResult(
        success=False,
        job_hash=job_hash,
        tailor_run_id=tailor_run_id,
        error=error_message,
    )


async def _ship_base_with_reason(
    *,
    db: DatabaseManager,
    tailor_run_id: int,
    job_hash: str,
    base_tex_path: Path,
    base_pdf_path: Path,
    review_payload: dict[str, Any],
    verdict: str,
    page_count: int,
    artifact_tex_override: Path | None = None,
    artifact_pdf_override: Path | None = None,
) -> TailorRunResult:
    """Persist a "ship the base PDF" verdict + return the result.

    Purpose:
        Three pipeline branches (`tailor_bailed`, `all_edits_dropped`,
        `page_fit_failed`) need the same DB write shape. This helper
        centralizes the persistence so the orchestrator branches stay
        short.
    Args:
        db: Connected database manager.
        tailor_run_id: Owning tailor run primary key.
        job_hash: Stable job identifier.
        base_tex_path: Path to the compiled base `.tex` artifact.
        base_pdf_path: Path to the compiled base PDF artifact.
        review_payload: JSON-serializable dict for `review_report_json`.
        verdict: DB verdict string from `DBReviewVerdict`.
        page_count: Page count to record on `tailor_runs`.
        artifact_tex_override: Optional override for the tailor_runs
            artifact_tex_path (page-fit-failed records the tailored
            artifact even though the base ships).
        artifact_pdf_override: Optional override for the tailor_runs
            artifact_pdf_path.
    Output:
        Populated `TailorRunResult`.
    """

    artifact_tex = artifact_tex_override or base_tex_path
    artifact_pdf = artifact_pdf_override or base_pdf_path

    review_run_id = await db.insert_pipeline_review_run(
        job_hash=job_hash,
        tailor_run_id=tailor_run_id,
        verdict=verdict,
        selected_yaml_path="",
        selected_tex_path=str(base_tex_path),
        selected_pdf_path=str(base_pdf_path),
        review_report_json=json.dumps(review_payload),
        fallback_base_yaml_path="",
        fallback_base_tex_path=str(base_tex_path),
        fallback_base_pdf_path=str(base_pdf_path),
    )
    await db.record_tailor_success(
        run_id=tailor_run_id,
        artifact_yaml_path="",
        artifact_tex_path=str(artifact_tex),
        artifact_pdf_path=str(artifact_pdf),
        page_count=page_count,
    )
    return TailorRunResult(
        success=True,
        job_hash=job_hash,
        tailor_run_id=tailor_run_id,
        review_run_id=review_run_id,
        verdict=verdict,
        selected_pdf_path=str(base_pdf_path),
        selected_yaml_path="",
        selected_tex_path=str(base_tex_path),
        page_count=page_count,
    )


__all__ = ["run_tailor_review_pipeline"]
