"""Orchestrator for the ADK tailor → render → reviewer → pick pipeline.

Public entry point: `run_tailor_review_pipeline`. Both the worker daemon
(`scripts/process_qualified_jobs.py`) and the API BackgroundTasks path
(`POST /api/jobs/{hash}/tailor`) call this same function.

Stages, in order:

1. Mark the tailor run RUNNING.
2. Load base resume YAML, candidate profile YAML, and job posting row.
3. Run the tailor agent (1 LLM call) → in-memory bullet edits.
4. Render the tailored variant; compile to PDF.
5. If >1 page → trim agent (1 LLM call), re-render, recompile.
6. If still >1 page → fall back to base PDF with verdict PAGE_FIT_FAILED.
7. Otherwise run the reviewer (1 LLM call, 2-way).
8. If verdict is `base_better` → re-tailor with feedback once, re-review
   (1 LLM call, 3-way).
9. Persist the selected artifacts on `tailor_runs` and `review_runs`.
10. Return `TailorRunResult`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import yaml
from google.adk.agents import BaseAgent
from loguru import logger

from src.database.db_manager import DatabaseManager
from src.utils.cost_tracking import (
    PIPELINE_STAGE_REVIEW,
    PIPELINE_STAGE_TAILOR,
    record_stage_cost_event,
)

from .agents import (
    REVIEWER_PROVIDER,
    TAILOR_PROVIDER,
    build_reviewer_agent,
    build_tailor_agent,
    extract_first_json_object,
    get_reviewer_model_name,
    get_tailor_model_name,
    run_agent_once,
)
from .compiler import compile_resume_tex, get_pdf_page_count
from .pipeline_schemas import (
    EDITABLE_SECTION_IDS,
    BulletEdit,
    ReviewerOutput,
    ReviewerScores,
    ReviewerVerdict,
    TailorOutput,
    TailorRunResult,
)
from .renderer import render_resume_tex
from .schemas import (
    ResumeBullet,
    ResumeContent,
    SkillListing,
)
from .yaml_io import load_resume_yaml, save_resume_yaml

PAGE_LIMIT = 1
BASE_VARIANT_NAME = "base"
TAILORED_V1_VARIANT_NAME = "tailored_v1"
TAILORED_V2_VARIANT_NAME = "tailored_v2"

VERDICT_TAILORED_DB = "TAILORED"
VERDICT_BASE_DB = "BASE"
VERDICT_NO_IMPROVEMENT_DB = "NO_IMPROVEMENT"
VERDICT_PAGE_FIT_FAILED_DB = "PAGE_FIT_FAILED"
VERDICT_FAIL_DB = "FAIL"


def _format_candidate_profile_snippet(profile_yaml_path: Path) -> str:
    """Read candidate profile YAML into a short prompt snippet.

    Purpose:
        Give the tailor model a compact summary of the candidate's
        strongest areas and experience highlights without dumping the
        full profile document.
    Args:
        profile_yaml_path: Filesystem path to `config/candidate_profile.yaml`.
    Output:
        Returns a YAML-formatted string slice containing the profile,
        truncated to a safe size for the prompt context.
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
        Returns a multi-line text block bracketed by `<job_posting>` tags
        so the model treats it as untrusted content.
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


def _format_resume_for_prompt(
    resume_content: ResumeContent,
    *,
    label: str,
) -> str:
    """Render one resume variant as YAML text inside a labeled tag.

    Purpose:
        Provide the agents with the exact bullet IDs they must reference
        in their edits while making the variant boundary obvious.
    Args:
        resume_content: Canonical resume model to serialize.
        label: Tag label (e.g. `base`, `tailored_v1`).
    Output:
        Returns the YAML text wrapped in `<resume label="...">` tags.
    """

    payload = resume_content.model_dump(mode="json")
    body = yaml.safe_dump(payload, sort_keys=False, allow_unicode=False, width=120)
    return f'<resume label="{label}">\n{body}\n</resume>'


def _parse_tailor_output(raw_response: str) -> TailorOutput:
    """Parse a raw tailor/trim model response into `TailorOutput`.

    Purpose:
        Survive responses that include preamble or fenced markdown by
        recovering the first JSON object before validating.
    Args:
        raw_response: Full raw text returned by the tailor or trim agent.
    Output:
        Returns a validated `TailorOutput`.
    Raises:
        ValueError: When no JSON object can be recovered or it does not
            match the expected schema.
    """

    parsed = extract_first_json_object(raw_response)
    if parsed is None:
        raise ValueError("tailor_invalid_json: no JSON object recovered")
    return TailorOutput.model_validate(parsed)


def _parse_reviewer_output(raw_response: str) -> ReviewerOutput:
    """Parse a raw reviewer model response into `ReviewerOutput`.

    Purpose:
        Mirror `_parse_tailor_output` for the reviewer-side schema so
        both agents share recovery semantics.
    Args:
        raw_response: Full raw text returned by the reviewer agent.
    Output:
        Returns a validated `ReviewerOutput`.
    Raises:
        ValueError: When no JSON object can be recovered or it does not
            match the expected schema.
    """

    parsed = extract_first_json_object(raw_response)
    if parsed is None:
        raise ValueError("reviewer_invalid_json: no JSON object recovered")
    return ReviewerOutput.model_validate(parsed)


def _apply_edits_in_memory(
    resume_content: ResumeContent,
    edits: list[BulletEdit],
) -> tuple[ResumeContent, int]:
    """Apply bullet edits to a deep copy of the resume.

    Purpose:
        Honor the invariant that the on-disk base resume YAML is never
        mutated. Edits that reference unknown sections/listings/bullets
        are skipped with a warning rather than aborting the run.
    Args:
        resume_content: Canonical base resume to clone and mutate.
        edits: Bullet edits emitted by the tailor or trim agent.
    Output:
        Returns a tuple of `(new_resume_content, applied_count)`.
    """

    working_copy = resume_content.model_copy(deep=True)
    applied = 0

    for edit in edits:
        section_id = edit.section.strip().lower()
        if section_id not in EDITABLE_SECTION_IDS:
            logger.warning("Skipping edit: non-editable section {!r}", edit.section)
            continue

        target_section: Any = getattr(working_copy, section_id, None)
        listings = getattr(target_section, "listings", None)
        if listings is None:
            logger.warning("Skipping edit: section {!r} has no listings", section_id)
            continue

        listing = next((item for item in listings if item.id == edit.listing_id), None)
        if listing is None:
            logger.warning(
                "Skipping edit: listing_id={!r} not found in section {!r}",
                edit.listing_id,
                section_id,
            )
            continue

        if section_id == "skills_achievements":
            if not isinstance(listing, SkillListing):
                continue
            # Whole-row rewrite for skill rows; empty text disables the row.
            new_text = edit.new_text.strip()
            if new_text == "":
                listing.enabled = False
            else:
                listing.text = new_text
            applied += 1
            continue

        if edit.bullet_id is None:
            logger.warning(
                "Skipping edit: bullet_id required for section {!r}", section_id
            )
            continue

        bullets: list[ResumeBullet] = getattr(listing, "bullets", [])
        bullet = next((item for item in bullets if item.id == edit.bullet_id), None)
        if bullet is None:
            logger.warning(
                "Skipping edit: bullet_id={!r} not found in listing {!r}",
                edit.bullet_id,
                edit.listing_id,
            )
            continue

        new_text = edit.new_text.strip()
        if new_text == "":
            # Empty replacement removes the bullet entirely.
            listing.bullets = [item for item in bullets if item.id != edit.bullet_id]
        else:
            bullet.text = new_text
        applied += 1

    return working_copy, applied


def _render_and_compile_variant(
    *,
    resume_content: ResumeContent,
    variant_dir: Path,
    variant_name: str,
) -> tuple[Path, Path, Path, int]:
    """Render a resume variant to TeX, compile to PDF, count pages.

    Purpose:
        Centralize the file-output side-effects so the orchestrator's
        control flow stays readable.
    Args:
        resume_content: Resume model to render.
        variant_dir: Directory that will hold the YAML/TeX/PDF artifacts.
        variant_name: Filename stem (e.g. `tailored_v1`).
    Output:
        Returns `(yaml_path, tex_path, pdf_path, page_count)`.
    """

    variant_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = variant_dir / f"{variant_name}.yaml"
    tex_path = variant_dir / f"{variant_name}.tex"
    pdf_path = variant_dir / f"{variant_name}.pdf"

    save_resume_yaml(path=yaml_path, resume_content=resume_content)
    tex_text = render_resume_tex(resume_content)
    with open(tex_path, "w", encoding="utf-8") as tex_file:
        tex_file.write(tex_text)
    compile_resume_tex(tex_path=tex_path, pdf_output_path=pdf_path)
    log_path = tex_path.with_suffix(".log")
    page_count = get_pdf_page_count(pdf_path=pdf_path, log_path=log_path)
    return yaml_path, tex_path, pdf_path, page_count


def _build_reviewer_message(
    *,
    job_block: str,
    base_resume: ResumeContent,
    tailored_v1: ResumeContent,
    tailored_v2: Optional[ResumeContent],
    feedback_for_retry: Optional[str],
) -> str:
    """Assemble the reviewer prompt body covering 2 or 3 variants.

    Purpose:
        Keep the reviewer agent stateless — the prompt body carries every
        variant and any retry feedback. The verdict semantics differ for
        2-way and 3-way comparisons; the prompt makes the count explicit.
    Args:
        job_block: Pre-formatted `<job_posting>` block.
        base_resume: Base resume content.
        tailored_v1: First tailor attempt content.
        tailored_v2: Optional second tailor attempt content.
        feedback_for_retry: Optional feedback that motivated the retry.
    Output:
        Returns the assembled user-role message text.
    """

    parts: list[str] = [job_block, _format_resume_for_prompt(base_resume, label="base")]
    parts.append(_format_resume_for_prompt(tailored_v1, label="tailored_v1"))
    if tailored_v2 is not None:
        parts.append(_format_resume_for_prompt(tailored_v2, label="tailored_v2"))
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


def _build_tailor_message(
    *,
    job_block: str,
    base_resume: ResumeContent,
    candidate_profile_text: str,
    retry_feedback: Optional[str] = None,
) -> str:
    """Assemble the tailor agent's user-role message.

    Purpose:
        Keep prompt assembly out of `run_tailor_review_pipeline` so the
        orchestrator can stay focused on control flow.
    Args:
        job_block: Pre-formatted `<job_posting>` block.
        base_resume: Base resume content.
        candidate_profile_text: YAML candidate profile snippet.
        retry_feedback: Optional reviewer feedback from a `base_better`
            verdict that drives a re-tailor attempt.
    Output:
        Returns the assembled user-role message text.
    """

    sections = [
        job_block,
        f"<candidate_profile>\n{candidate_profile_text}\n</candidate_profile>",
        _format_resume_for_prompt(base_resume, label="base"),
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
    overflow_resume: ResumeContent,
    measured_page_count: int,
) -> str:
    """Assemble the trim agent's user-role message.

    Purpose:
        Tell the trim agent how far over the page budget the current
        variant is so it does not over-trim.
    Args:
        job_block: Pre-formatted `<job_posting>` block.
        overflow_resume: Tailored variant that exceeded the page limit.
        measured_page_count: Last measured page count.
    Output:
        Returns the assembled user-role message text.
    """

    return "\n\n".join(
        (
            job_block,
            _format_resume_for_prompt(overflow_resume, label="tailored_v1"),
            f"<overflow>\nMeasured page count: {measured_page_count}. "
            f"Trim to {PAGE_LIMIT} page.\n</overflow>",
        )
    )


def _select_final_variant(
    *,
    verdict: ReviewerVerdict,
    base_artifacts: tuple[Path, Path, Path],
    tailored_artifacts: tuple[Path, Path, Path],
) -> tuple[str, tuple[Path, Path, Path]]:
    """Resolve the reviewer verdict into a stored verdict + artifact triple.

    Purpose:
        Keep the verdict-to-artifact mapping centralized so the DB write
        path is straightforward.
    Args:
        verdict: Reviewer's verdict enum.
        base_artifacts: `(yaml, tex, pdf)` paths for the base variant.
        tailored_artifacts: `(yaml, tex, pdf)` paths for the chosen tailored
            variant.
    Output:
        Returns `(db_verdict_string, (yaml, tex, pdf))` for persistence.
    """

    if verdict == ReviewerVerdict.TAILORED_BETTER:
        return VERDICT_TAILORED_DB, tailored_artifacts
    if verdict == ReviewerVerdict.BASE_BETTER:
        return VERDICT_BASE_DB, base_artifacts
    return VERDICT_NO_IMPROVEMENT_DB, base_artifacts


async def _record_cost(
    *,
    db: DatabaseManager,
    stage: str,
    job_hash: str,
    tailor_run_id: int,
    metadata: dict[str, Any],
) -> None:
    """Best-effort wrapper around `record_stage_cost_event`.

    Purpose:
        Cost recording is observational — never let a recording failure
        kill a real pipeline run.
    Args:
        db: Connected database manager.
        stage: Pipeline stage constant (`TAILOR` or `REVIEW`).
        job_hash: Stable job identifier.
        tailor_run_id: Owning tailor run primary key.
        metadata: Model/attempt metadata to attach to the event.
    Output:
        Returns `None`; errors are logged and swallowed.
    """

    try:
        await record_stage_cost_event(
            db=db,
            stage=stage,
            job_hash=job_hash,
            run_id=str(tailor_run_id),
            metadata=metadata,
        )
    except Exception as exc:
        logger.warning("Cost recording failed (stage={}): {}", stage, exc)


async def run_tailor_review_pipeline(
    *,
    db: DatabaseManager,
    tailor_run_id: int,
    job_hash: str,
    base_resume_yaml_path: str | Path,
    candidate_profile_yaml_path: str | Path,
    output_dir: str | Path,
    tailor_agent: Optional[BaseAgent] = None,
    trim_agent: Optional[BaseAgent] = None,
    reviewer_agent: Optional[BaseAgent] = None,
    record_costs: bool = True,
) -> TailorRunResult:
    """Run the full tailor → render → reviewer → pick pipeline.

    Purpose:
        Single entry point used by both the autonomous worker daemon and
        the opt-in API BackgroundTask. The function owns every DB write
        for the run: marking the tailor row RUNNING, writing the artifact
        paths on success, recording the failure on hard errors, and
        inserting the matching review_runs row.
    Args:
        db: Connected database manager (already inside a context manager).
        tailor_run_id: Primary key of the PENDING tailor_runs row.
        job_hash: Stable job identifier.
        base_resume_yaml_path: Path to `config/resume_content.yaml`.
        candidate_profile_yaml_path: Path to `config/candidate_profile.yaml`.
        output_dir: Per-run artifact directory; each variant gets a subdir.
        tailor_agent: Optional injected ADK agent (tests); built when omitted.
        trim_agent: Optional injected trim agent (tests); built when omitted.
        reviewer_agent: Optional injected reviewer agent (tests); built when
            omitted.
        record_costs: When `True`, emit per-stage cost events.
    Output:
        Returns a populated `TailorRunResult`.
    """

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    await db.mark_tailor_running(run_id=tailor_run_id)

    job_row = await db.get_resume_tailor_job_context(job_hash=job_hash)
    if job_row is None:
        error_message = f"job_not_found: {job_hash}"
        await db.record_tailor_failure(
            run_id=tailor_run_id,
            error=error_message,
            next_retry_at=None,
        )
        return TailorRunResult(
            success=False,
            job_hash=job_hash,
            tailor_run_id=tailor_run_id,
            error=error_message,
        )

    try:
        base_resume = load_resume_yaml(base_resume_yaml_path)
    except Exception as exc:
        error_message = f"base_resume_load_failed: {exc}"
        logger.exception("Base resume load failed for job {}", job_hash)
        await db.record_tailor_failure(
            run_id=tailor_run_id, error=error_message, next_retry_at=None
        )
        return TailorRunResult(
            success=False,
            job_hash=job_hash,
            tailor_run_id=tailor_run_id,
            error=error_message,
        )

    candidate_profile_text = _format_candidate_profile_snippet(
        Path(candidate_profile_yaml_path)
    )
    job_block = _format_job_snippet(job_row)

    base_variant_dir = output_dir / BASE_VARIANT_NAME
    base_yaml_path, base_tex_path, base_pdf_path, _ = _render_and_compile_variant(
        resume_content=base_resume,
        variant_dir=base_variant_dir,
        variant_name=BASE_VARIANT_NAME,
    )
    base_artifacts = (base_yaml_path, base_tex_path, base_pdf_path)

    tailor_owned = tailor_agent
    trim_owned = trim_agent
    reviewer_owned = reviewer_agent

    try:
        if tailor_owned is None:
            tailor_owned = build_tailor_agent(mode="tailor")
        tailor_message = _build_tailor_message(
            job_block=job_block,
            base_resume=base_resume,
            candidate_profile_text=candidate_profile_text,
        )
        tailor_response = await run_agent_once(
            agent=tailor_owned, user_message=tailor_message
        )
        if record_costs:
            await _record_cost(
                db=db,
                stage=PIPELINE_STAGE_TAILOR,
                job_hash=job_hash,
                tailor_run_id=tailor_run_id,
                metadata={
                    "provider": TAILOR_PROVIDER,
                    "model": get_tailor_model_name(),
                    "phase": "tailor",
                },
            )
        tailor_output = _parse_tailor_output(tailor_response)

        tailored_v1, applied_v1 = _apply_edits_in_memory(base_resume, tailor_output.edits)

        if applied_v1 == 0:
            review_run_id = await db.insert_pipeline_review_run(
                job_hash=job_hash,
                tailor_run_id=tailor_run_id,
                verdict=VERDICT_NO_IMPROVEMENT_DB,
                selected_yaml_path=str(base_yaml_path),
                selected_tex_path=str(base_tex_path),
                selected_pdf_path=str(base_pdf_path),
                review_report_json=json.dumps(
                    {"reason": "no_edits_applied", "summary": tailor_output.summary}
                ),
                fallback_base_yaml_path=str(base_yaml_path),
                fallback_base_tex_path=str(base_tex_path),
                fallback_base_pdf_path=str(base_pdf_path),
            )
            await db.record_tailor_success(
                run_id=tailor_run_id,
                artifact_yaml_path=str(base_yaml_path),
                artifact_tex_path=str(base_tex_path),
                artifact_pdf_path=str(base_pdf_path),
                page_count=PAGE_LIMIT,
            )
            return TailorRunResult(
                success=True,
                job_hash=job_hash,
                tailor_run_id=tailor_run_id,
                review_run_id=review_run_id,
                verdict=VERDICT_NO_IMPROVEMENT_DB,
                selected_pdf_path=str(base_pdf_path),
                selected_yaml_path=str(base_yaml_path),
                selected_tex_path=str(base_tex_path),
                page_count=PAGE_LIMIT,
            )

        v1_dir = output_dir / TAILORED_V1_VARIANT_NAME
        (
            v1_yaml_path,
            v1_tex_path,
            v1_pdf_path,
            v1_page_count,
        ) = _render_and_compile_variant(
            resume_content=tailored_v1,
            variant_dir=v1_dir,
            variant_name=TAILORED_V1_VARIANT_NAME,
        )

        # Page-fit trim pass — at most one extra LLM call.
        if v1_page_count > PAGE_LIMIT:
            if trim_owned is None:
                trim_owned = build_tailor_agent(mode="trim")
            trim_message = _build_trim_message(
                job_block=job_block,
                overflow_resume=tailored_v1,
                measured_page_count=v1_page_count,
            )
            trim_response = await run_agent_once(
                agent=trim_owned, user_message=trim_message
            )
            if record_costs:
                await _record_cost(
                    db=db,
                    stage=PIPELINE_STAGE_TAILOR,
                    job_hash=job_hash,
                    tailor_run_id=tailor_run_id,
                    metadata={
                        "provider": TAILOR_PROVIDER,
                        "model": get_tailor_model_name(),
                        "phase": "trim",
                    },
                )
            trim_output = _parse_tailor_output(trim_response)
            trimmed_v1, _ = _apply_edits_in_memory(tailored_v1, trim_output.edits)
            (
                v1_yaml_path,
                v1_tex_path,
                v1_pdf_path,
                v1_page_count,
            ) = _render_and_compile_variant(
                resume_content=trimmed_v1,
                variant_dir=v1_dir,
                variant_name=TAILORED_V1_VARIANT_NAME,
            )
            tailored_v1 = trimmed_v1

        if v1_page_count > PAGE_LIMIT:
            review_run_id = await db.insert_pipeline_review_run(
                job_hash=job_hash,
                tailor_run_id=tailor_run_id,
                verdict=VERDICT_PAGE_FIT_FAILED_DB,
                selected_yaml_path=str(base_yaml_path),
                selected_tex_path=str(base_tex_path),
                selected_pdf_path=str(base_pdf_path),
                review_report_json=json.dumps(
                    {"reason": "page_fit_failed", "final_page_count": v1_page_count}
                ),
                fallback_base_yaml_path=str(base_yaml_path),
                fallback_base_tex_path=str(base_tex_path),
                fallback_base_pdf_path=str(base_pdf_path),
            )
            await db.record_tailor_success(
                run_id=tailor_run_id,
                artifact_yaml_path=str(v1_yaml_path),
                artifact_tex_path=str(v1_tex_path),
                artifact_pdf_path=str(v1_pdf_path),
                page_count=v1_page_count,
            )
            return TailorRunResult(
                success=True,
                job_hash=job_hash,
                tailor_run_id=tailor_run_id,
                review_run_id=review_run_id,
                verdict=VERDICT_PAGE_FIT_FAILED_DB,
                selected_pdf_path=str(base_pdf_path),
                selected_yaml_path=str(base_yaml_path),
                selected_tex_path=str(base_tex_path),
                page_count=v1_page_count,
            )

        # Reviewer — 2-way base vs v1.
        if reviewer_owned is None:
            reviewer_owned = build_reviewer_agent()
        reviewer_message = _build_reviewer_message(
            job_block=job_block,
            base_resume=base_resume,
            tailored_v1=tailored_v1,
            tailored_v2=None,
            feedback_for_retry=None,
        )
        reviewer_response = await run_agent_once(
            agent=reviewer_owned, user_message=reviewer_message
        )
        if record_costs:
            await _record_cost(
                db=db,
                stage=PIPELINE_STAGE_REVIEW,
                job_hash=job_hash,
                tailor_run_id=tailor_run_id,
                metadata={
                    "provider": REVIEWER_PROVIDER,
                    "model": get_reviewer_model_name(),
                    "phase": "two_way",
                },
            )
        reviewer_output = _parse_reviewer_output(reviewer_response)

        tailored_v2: Optional[ResumeContent] = None
        v2_artifacts: Optional[tuple[Path, Path, Path]] = None
        v2_page_count: Optional[int] = None

        # Re-tailor at most once when reviewer prefers the base resume.
        if reviewer_output.verdict == ReviewerVerdict.BASE_BETTER:
            feedback = reviewer_output.feedback_for_retry or reviewer_output.rationale
            retry_message = _build_tailor_message(
                job_block=job_block,
                base_resume=base_resume,
                candidate_profile_text=candidate_profile_text,
                retry_feedback=feedback,
            )
            retry_response = await run_agent_once(
                agent=tailor_owned, user_message=retry_message
            )
            if record_costs:
                await _record_cost(
                    db=db,
                    stage=PIPELINE_STAGE_TAILOR,
                    job_hash=job_hash,
                    tailor_run_id=tailor_run_id,
                    metadata={
                        "provider": TAILOR_PROVIDER,
                        "model": get_tailor_model_name(),
                        "phase": "retailor",
                    },
                )
            retry_output = _parse_tailor_output(retry_response)
            candidate_v2, applied_v2 = _apply_edits_in_memory(
                base_resume, retry_output.edits
            )

            if applied_v2 > 0:
                v2_dir = output_dir / TAILORED_V2_VARIANT_NAME
                (
                    v2_yaml,
                    v2_tex,
                    v2_pdf,
                    v2_page_count,
                ) = _render_and_compile_variant(
                    resume_content=candidate_v2,
                    variant_dir=v2_dir,
                    variant_name=TAILORED_V2_VARIANT_NAME,
                )
                if v2_page_count <= PAGE_LIMIT:
                    tailored_v2 = candidate_v2
                    v2_artifacts = (v2_yaml, v2_tex, v2_pdf)

        # If a usable v2 exists, run a 3-way reviewer pass.
        if tailored_v2 is not None and v2_artifacts is not None:
            three_way_message = _build_reviewer_message(
                job_block=job_block,
                base_resume=base_resume,
                tailored_v1=tailored_v1,
                tailored_v2=tailored_v2,
                feedback_for_retry=reviewer_output.feedback_for_retry,
            )
            three_way_response = await run_agent_once(
                agent=reviewer_owned, user_message=three_way_message
            )
            if record_costs:
                await _record_cost(
                    db=db,
                    stage=PIPELINE_STAGE_REVIEW,
                    job_hash=job_hash,
                    tailor_run_id=tailor_run_id,
                    metadata={
                        "provider": REVIEWER_PROVIDER,
                        "model": get_reviewer_model_name(),
                        "phase": "three_way",
                    },
                )
            three_way_output = _parse_reviewer_output(three_way_response)
            final_verdict = three_way_output.verdict
            final_scores_base = three_way_output.scores_base
            final_scores_tailored = three_way_output.scores_tailored
            final_rationale = three_way_output.rationale
            tailored_artifacts = v2_artifacts
            tailored_page_count = v2_page_count or v1_page_count
        else:
            final_verdict = reviewer_output.verdict
            final_scores_base = reviewer_output.scores_base
            final_scores_tailored = reviewer_output.scores_tailored
            final_rationale = reviewer_output.rationale
            tailored_artifacts = (v1_yaml_path, v1_tex_path, v1_pdf_path)
            tailored_page_count = v1_page_count

        db_verdict, selected_artifacts = _select_final_variant(
            verdict=final_verdict,
            base_artifacts=base_artifacts,
            tailored_artifacts=tailored_artifacts,
        )
        selected_yaml, selected_tex, selected_pdf = selected_artifacts

        review_report_payload = {
            "verdict": final_verdict.value,
            "scores_base": final_scores_base.model_dump(),
            "scores_tailored": final_scores_tailored.model_dump(),
            "rationale": final_rationale,
            "had_retry": tailored_v2 is not None,
        }

        review_run_id = await db.insert_pipeline_review_run(
            job_hash=job_hash,
            tailor_run_id=tailor_run_id,
            verdict=db_verdict,
            selected_yaml_path=str(selected_yaml),
            selected_tex_path=str(selected_tex),
            selected_pdf_path=str(selected_pdf),
            review_report_json=json.dumps(review_report_payload),
            fallback_base_yaml_path=str(base_yaml_path),
            fallback_base_tex_path=str(base_tex_path),
            fallback_base_pdf_path=str(base_pdf_path),
        )

        # The artifact paths on tailor_runs always point at the tailored work,
        # not the served PDF — review_runs.selected_pdf_path is authoritative
        # for "what we serve". Page count reflects the tailored variant.
        await db.record_tailor_success(
            run_id=tailor_run_id,
            artifact_yaml_path=str(tailored_artifacts[0]),
            artifact_tex_path=str(tailored_artifacts[1]),
            artifact_pdf_path=str(tailored_artifacts[2]),
            page_count=tailored_page_count,
        )

        return TailorRunResult(
            success=True,
            job_hash=job_hash,
            tailor_run_id=tailor_run_id,
            review_run_id=review_run_id,
            verdict=db_verdict,
            selected_pdf_path=str(selected_pdf),
            selected_yaml_path=str(selected_yaml),
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
