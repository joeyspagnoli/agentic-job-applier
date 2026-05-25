"""Pydantic AI tools for the apply-finisher.

The browser surface is a single shell-tool that runs the
``agent-browser`` CLI in the persistent CDP session the worker
attached before invoking the finisher. The four non-browser tools
(``lookup_cached_answer``, ``defer``, ``flag_for_verify``, and the
``complete_apply`` output tool registered in ``agent.py``) touch
``FinisherDeps`` state — answer cache, deferral list, drafted-field
list, termination — and never see the browser.

The browser-touching CLI plumbing lives in
:mod:`src.agents.apply_finisher.browser_cli` so the runner and worker
can call the exact same subprocess wrapper for pre-flight and session
bootstrap, respectively.
"""

from __future__ import annotations

from typing import Any

from pydantic_ai import ModelRetry, RunContext

from src.agents.apply_finisher.browser_cli import invoke_agent_browser_cli
from src.agents.apply_finisher.schemas import (
    DeferredQuestion,
    DraftedField,
    FinisherDeps,
)


def _normalize_ab_ref(ref: str) -> str:
    """Normalize an agent-browser ref to the bare ``eN`` form.

    Purpose:
        Tools that record refs (``defer``, ``flag_for_verify``) accept
        whatever shape the model emits — agent-browser's ``@e5``
        prefix, the bare ``e5`` form, or just the digits — and store
        the canonical ``eN`` so diagnostics stay shape-stable across
        runs and tool surfaces.
    Args:
        ref: Caller-supplied ref string.
    Returns:
        ``"eN"`` form (no ``@`` prefix) suitable for diagnostics.
    Raises:
        ModelRetry: When ``ref`` is empty or unparseable.
    """

    candidate = (ref or "").strip().lstrip("@")
    if not candidate:
        raise ModelRetry("ref must be non-empty (e.g. '@e5' or 'e5').")
    if candidate.startswith("e") and candidate[1:].isdigit():
        return candidate
    if candidate.isdigit():
        return f"e{candidate}"
    raise ModelRetry(
        f"ref {ref!r} is not a valid agent-browser ref (expected '@eN', "
        "'eN', or 'N')."
    )


async def agent_browser(
    args: list[str],
    expect_json: bool = False,
    timeout_seconds: float = 20.0,
) -> dict[str, Any]:
    """Run an ``agent-browser`` CLI command in the persistent CDP session.

    Purpose:
        Single browser surface for the finisher agent. The worker
        runs ``agent-browser connect <CDP_URL>`` once before invoking
        ``run_finisher``; every call from inside the agent loop reuses
        that session. The function shells out to the CLI via the
        shared ``invoke_agent_browser_cli`` helper so timeout / output
        truncation / JSON parsing semantics match the runner pre-flight
        and the worker bootstrap.
    Args:
        args: CLI argv tail, e.g. ``["snapshot", "-i", "-c"]``. The
            ``agent-browser`` executable is prepended automatically —
            never include it in ``args``. Passing a Python list avoids
            any shell-quoting concerns.
        expect_json: When True, append ``--json`` to ``args`` (if not
            already present) and parse stdout as JSON into the ``data``
            field of the return value. On parse failure, ``ok=False``
            and ``error`` describes the failure.
        timeout_seconds: Hard wall-clock cap. Defaults to 20s — enough
            for ``wait --load networkidle`` but short enough to abort
            hangs before the agent's request budget is consumed.
    Returns:
        Dict with keys:
          - ``ok`` (bool): True iff exit_code == 0 and (when applicable)
            JSON parsed successfully.
          - ``command`` (str): The argv that ran, joined for logs.
          - ``stdout`` (str): Captured stdout, truncated.
          - ``stderr`` (str): Captured stderr, truncated.
          - ``exit_code`` (int): Process exit code; ``-1`` on timeout,
            ``-2`` on launch failure.
          - ``data`` (Any, optional): Parsed JSON when ``expect_json``.
          - ``error`` (str, optional): Human-readable failure summary.
    Raises:
        ModelRetry: When the binary is missing from the image so the
            agent surfaces an actionable diagnostic rather than burning
            turns on a broken deploy.
    """

    result = await invoke_agent_browser_cli(
        args,
        expect_json=expect_json,
        timeout_seconds=timeout_seconds,
    )
    if (
        not result["ok"]
        and result.get("exit_code") == -2
        and "not on PATH" in (result.get("error") or "")
    ):
        raise ModelRetry(
            "agent-browser CLI not on PATH inside the container — "
            "the deploy is broken. Cannot proceed."
        )
    return result


async def defer(
    ctx: RunContext[FinisherDeps],
    ref: str,
    label: str,
    field_type: str,
    category: str,
    reason: str,
) -> str:
    """Record a Tier-3 field the human must answer.

    Purpose:
        Append to ``ctx.deps.recorded_deferrals`` without touching the
        page. The agent must NOT also fill the field. The runner reads
        this list when synthesizing the final ``FinisherResult``.
    Args:
        ctx: Tool run context.
        ref: agent-browser ref of the deferred field (``"@e5"`` or
            ``"e5"`` or ``"5"``).
        label: Visible label captured from the snapshot.
        field_type: One of ``select`` / ``textarea`` / ``checkbox`` / ...
        category: ``sponsorship`` / ``eeo`` / ``salary`` / ``start_date``
            / ``other``.
        reason: Short justification (one sentence).
    Returns:
        Confirmation string.
    """

    normalized = _normalize_ab_ref(ref)
    ctx.deps.recorded_deferrals.append(
        DeferredQuestion(
            field_id=normalized,
            label=label,
            field_type=field_type,
            category=category,
            reason=reason,
        )
    )
    return f"deferred ref {normalized} (category={category})"


async def lookup_cached_answer(
    ctx: RunContext[FinisherDeps],
    question_text: str,
) -> str:
    """Look up a previously-cached answer by fuzzy match.

    Purpose:
        Tier-2 essays the user already approved in a past run become
        Tier 1 for this run. Per-company entries win over anonymized
        entries; the cache substitutes ``$COMPANY`` automatically.
    Args:
        ctx: Tool run context.
        question_text: The question label as it appears on the form.
    Returns:
        The cached answer string when found, or a sentinel
        ``"<no cache hit>"`` when no entry meets the fuzzy threshold.
    """

    hit = ctx.deps.cache.lookup(question_text, company=ctx.deps.target_company)
    if hit is None:
        return "<no cache hit>"
    return (
        f"<cache_hit score={hit.score:.0f} "
        f"anonymized={hit.was_anonymized}>\n{hit.entry.answer}"
    )


async def flag_for_verify(
    ctx: RunContext[FinisherDeps],
    ref: str,
    label: str,
    drafted_value: str,
    confidence: float,
    reasoning: str,
) -> str:
    """Record a Tier-2 draft for human review.

    Purpose:
        The agent ALSO fills the value into the form (via
        ``agent_browser(["fill", ...])``); this tool only registers
        that the value must be approved by the human before the gate
        may auto-submit.
    Args:
        ctx: Tool run context.
        ref: agent-browser ref of the drafted field.
        label: Visible label captured pre-fill.
        drafted_value: The text the agent wrote.
        confidence: Self-reported confidence in [0.0, 1.0]. Be honest;
            high confidence only when sourced directly from the
            candidate profile.
        reasoning: One-sentence justification of the value.
    Returns:
        Confirmation string.
    Raises:
        ModelRetry: When ``confidence`` is outside [0.0, 1.0].
    """

    normalized = _normalize_ab_ref(ref)
    if not 0.0 <= confidence <= 1.0:
        raise ModelRetry(
            f"confidence={confidence} is outside [0.0, 1.0]. Re-emit with "
            "a value in that range."
        )

    ctx.deps.drafted_fields.append(
        DraftedField(
            field_id=normalized,
            label=label,
            drafted_value=drafted_value,
            confidence=confidence,
            reasoning=reasoning,
        )
    )
    return f"flagged ref {normalized} for verify (confidence={confidence:.2f})"


# Tools registered on the agent. ``complete_apply`` is wired separately
# as the output tool (see ``agent.py``).
FINISHER_TOOLS: tuple[Any, ...] = (
    agent_browser,
    lookup_cached_answer,
    defer,
    flag_for_verify,
)


__all__ = [
    "FINISHER_TOOLS",
    "agent_browser",
    "defer",
    "flag_for_verify",
    "lookup_cached_answer",
]
