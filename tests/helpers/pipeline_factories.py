"""Builders for bullet manifests + reviewer payloads used by pipeline tests.

Purpose:
    Concentrate fixture construction so each test reads as a sequence
    of behaviors rather than a wall of nested dicts. Every factory
    returns a fully validated Pydantic model so tests fail fast on
    schema drift.

Factories produce bullet manifests and patch-proposal payloads — the
pipeline no longer consumes the legacy `ResumeContent` shape.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from src.agents.resume_tailor.llm import LlmCallResult
from src.agents.resume_tailor.locator import build_bullet_manifest
from src.agents.resume_tailor.manifest import BulletManifest
from src.providers.types import CostBreakdown, TokenUsage
from src.agents.resume_tailor.pipeline_schemas import (
    BulletPatchProposal,
    ReviewerOutput,
    ReviewerScores,
    ReviewerVerdict,
    SkippedBulletNote,
    TailorOutput,
)


def row_int(row: dict[str, object] | None, key: str) -> int:
    """Extract one int field from a `dict[str, object]` row safely.

    Purpose:
        Avoid scattering `int(cast(int, row["id"]))` across every test.
        Asserts the row is not `None` and the field is integral.
    Args:
        row: Database row mapping returned by `DatabaseManager` methods.
        key: Field name to extract.
    Output:
        Integer value at `key`.
    """

    assert row is not None, "expected a row, got None"
    return int(cast(int, row[key]))


def row_str(row: dict[str, object] | None, key: str) -> str:
    """Extract one string field from a `dict[str, object]` row safely.

    Purpose:
        Same role as `row_int` — keep DB-row reads readable without
        per-call `cast` noise.
    Args:
        row: Database row mapping.
        key: Field name to extract.
    Output:
        String value at `key`.
    """

    assert row is not None, "expected a row, got None"
    return str(cast(str, row[key]))


def resume_tex_fixture_path() -> Path:
    """Return the absolute path to the synthetic-minimal `.tex` fixture.

    Purpose:
        Phase-2 tests need a contract-conforming `.tex` source. The
        synthetic minimal fixture is the smallest such file in the
        repo.
    Output:
        Absolute `Path` to `tests/fixtures/resumes/synthetic_minimal.tex`.
    """

    return (
        Path(__file__).resolve().parent.parent
        / "fixtures"
        / "resumes"
        / "synthetic_minimal.tex"
    )


def build_minimal_bullet_manifest() -> BulletManifest:
    """Build a deterministic manifest from the synthetic-minimal fixture.

    Purpose:
        Phase-2 unit tests use this as the canonical "small known
        manifest" so per-test branches can exercise the patcher and
        proposal-resolution code without writing fixtures by hand.
    Output:
        Manifest with the synthetic-minimal fixture's sections,
        entries, and bullets.
    """

    tex_text = resume_tex_fixture_path().read_text(encoding="utf-8")
    return build_bullet_manifest(tex_text)


def make_tailor_result(
    *,
    bullets: list[BulletPatchProposal] | None = None,
    skipped_bullets: list[SkippedBulletNote] | None = None,
    rewrite_plan: str = "Test rewrite plan.",
) -> LlmCallResult[TailorOutput]:
    """Build an `LlmCallResult[TailorOutput]` stub for monkeypatching.

    Purpose:
        Keep test assertions focused on pipeline branches; the LLM
        call result shape stays consistent across every scenario.
    Args:
        bullets: Per-bullet proposals the fake tailor emits.
        skipped_bullets: Optional skipped-bullet notes.
        rewrite_plan: Rationale-first plan text. Field-1 by schema.
    Output:
        Populated `LlmCallResult` carrying a fake `TailorOutput`.
    """

    output = TailorOutput(
        rewrite_plan=rewrite_plan,
        bullets=list(bullets or []),
        skipped_bullets=list(skipped_bullets or []),
    )
    stub_usage = TokenUsage(prompt_tokens=10, completion_tokens=5)
    stub_cost = CostBreakdown()
    return LlmCallResult(
        parsed=output,
        model="openai/test-model",
        usage=stub_usage,
        cost=stub_cost,
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
    )


def make_reviewer_result(
    *,
    verdict: ReviewerVerdict,
    feedback_for_retry: str | None = None,
    rationale: str = "Test rationale.",
    factuality_base: int = 5,
    factuality_tailored: int = 5,
) -> LlmCallResult[ReviewerOutput]:
    """Build an `LlmCallResult[ReviewerOutput]` stub for monkeypatching.

    Purpose:
        Cover the factuality-veto branch (set `factuality_tailored=0`
        with `verdict=BASE_BETTER`) alongside the standard
        better/worse/no-improvement verdicts.
    Args:
        verdict: Reviewer verdict to return.
        feedback_for_retry: Critique to attach when verdict is
            `base_better`.
        rationale: Field-1 rationale text.
        factuality_base: Factuality score on the base variant (0-5).
        factuality_tailored: Factuality score on the tailored variant
            (0-5). Set to 0 to simulate the factuality veto.
    Output:
        Populated `LlmCallResult` carrying a fake `ReviewerOutput`.
    """

    output = ReviewerOutput(
        rationale=rationale,
        scores_base=ReviewerScores(
            keyword_fit=3, specificity=3, factuality=factuality_base
        ),
        scores_tailored=ReviewerScores(
            keyword_fit=4, specificity=4, factuality=factuality_tailored
        ),
        verdict=verdict,
        feedback_for_retry=feedback_for_retry,
    )
    stub_usage = TokenUsage(prompt_tokens=20, completion_tokens=8)
    stub_cost = CostBreakdown()
    return LlmCallResult(
        parsed=output,
        model="openai/test-model",
        usage=stub_usage,
        cost=stub_cost,
        prompt_tokens=20,
        completion_tokens=8,
        total_tokens=28,
    )


def single_valid_patch_proposal() -> BulletPatchProposal:
    """Return one rewrite proposal that targets the synthetic fixture.

    Purpose:
        Match an actual bullet ID from `synthetic_minimal.tex` so the
        pipeline counts the proposal as applicable.
    Output:
        Populated `BulletPatchProposal` with `action="rewrite"`.
    """

    manifest = build_minimal_bullet_manifest()
    # Pull the first bullet of the first entry of the first section.
    first_section = manifest.sections[0]
    first_entry = first_section.entries[0]
    first_bullet = first_entry.bullets[0]
    return BulletPatchProposal(
        id=first_bullet.id,
        rationale="Test rationale.",
        action="rewrite",
        new_text="Rewrote the first bullet.",
    )
