"""Typed BYO Playwright tools for the apply finisher.

Module-level async functions so the agent can register them via
``Agent(tools=[...])`` and each tool stays independently unit-testable.
Each tool takes ``RunContext[FinisherDeps]`` and resolves Playwright
locators through Playwright 1.59+'s native ``aria-ref=eN`` selector
(no custom RefMap needed).
"""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger
from pydantic_ai import BinaryContent, ModelRetry, RunContext, ToolReturn

from src.agents.apply_finisher.schemas import (
    DeferredQuestion,
    DraftedField,
    FinisherDeps,
)

# Hard cap on serialized snapshot length. Above this we truncate so the
# model's context budget doesn't blow up on multi-page forms.
_MAX_SNAPSHOT_CHARS: int = 24_000
_TRUNCATION_SENTINEL: str = "\n...(snapshot truncated for length)"

# Default DOM-quiet wait window. Empirically sufficient for Ashby's
# React re-mounts (Notion EEO fieldset takes ~250ms).
_DEFAULT_DOM_QUIET_MS: int = 300
_DOM_QUIET_TIMEOUT_MS: int = 5_000

# Submit-button name prefixes the finisher refuses to click. Defense
# in depth alongside the worker's hard ``dry_run`` ceiling.
_FORBIDDEN_CLICK_NAME_PREFIXES: tuple[str, ...] = (
    "submit",
    "apply",
    "send application",
    "send",
)


def _normalize_aria_ref(ref: str) -> str:
    """Normalize an aria ref to the ``eN`` form Playwright expects.

    Accepts both ``"e5"`` and ``"5"``; Pydantic AI tool arguments come
    from the model as strings so we cannot trust the shape.

    Args:
        ref: Caller-supplied ref string.
    Returns:
        ``"eN"`` form suitable for ``page.locator(f"aria-ref={ref}")``.
    Raises:
        ModelRetry: When ``ref`` is empty or unparseable.
    """

    candidate = (ref or "").strip()
    if not candidate:
        raise ModelRetry("ref must be non-empty (e.g. 'e5').")
    if candidate.startswith("e") and candidate[1:].isdigit():
        return candidate
    if candidate.isdigit():
        return f"e{candidate}"
    raise ModelRetry(
        f"ref {ref!r} is not a valid aria-ref (expected 'eN' or 'N')."
    )


def _is_forbidden_name(accessible_name: str) -> bool:
    """Return True when an accessible name should never be clicked.

    Purpose:
        The finisher must never click the submit button. The worker
        owns auto-submit and the gate decides whether to fire.
    Args:
        accessible_name: Visible label / aria-label captured pre-click.
    """

    cleaned = (accessible_name or "").strip().lower()
    return any(cleaned.startswith(prefix) for prefix in _FORBIDDEN_CLICK_NAME_PREFIXES)


async def get_snapshot(ctx: RunContext[FinisherDeps]) -> ToolReturn:
    """Return the accessibility tree for the application form.

    Purpose:
        Single entry point the agent uses to "see" the page. Uses
        Playwright 1.59+'s native ``aria_snapshot(mode="ai")`` which
        emits the ``[ref=eN]`` markers used by every other tool. Falls
        back to a full-page screenshot when the tree is empty so the
        model can still localize fields via vision (sub-agent B
        confirms gpt-5.4-mini accepts ``input_image`` + function tools
        on the same turn).
    Args:
        ctx: Tool run context carrying ``FinisherDeps``.
    Returns:
        ``ToolReturn`` whose ``return_value`` is the truncated AX tree
        text, or a screenshot-fallback message when the tree is empty.
    """

    page = ctx.deps.page
    selector = ctx.deps.form_root_selector

    try:
        snapshot_yaml = await page.locator(selector).aria_snapshot(mode="ai")
    except Exception as exc:
        logger.warning(
            "aria_snapshot failed for selector={!r}: {} — falling back to body",
            selector,
            exc,
        )
        snapshot_yaml = await page.locator("body").aria_snapshot(mode="ai")

    stripped = (snapshot_yaml or "").strip()
    if stripped:
        if len(stripped) > _MAX_SNAPSHOT_CHARS:
            stripped = stripped[:_MAX_SNAPSHOT_CHARS] + _TRUNCATION_SENTINEL
        return ToolReturn(return_value=stripped)

    # AX-tree empty — capture a screenshot and let the model use vision.
    try:
        screenshot_bytes = await page.screenshot(full_page=True)
    except Exception as exc:  # pragma: no cover - exercised in fixture tests
        logger.error("Screenshot fallback failed: {}", exc)
        return ToolReturn(
            return_value=(
                "Accessibility tree was empty and screenshot capture failed. "
                "End the run via complete_apply with outcome AGENT_GAVE_UP."
            ),
        )
    return ToolReturn(
        return_value=(
            "Accessibility tree was empty. Inspect the attached screenshot "
            "to identify fields, then call get_snapshot again after the "
            "next interaction settles."
        ),
        content=[
            "Fallback screenshot of the application form:",
            BinaryContent(data=screenshot_bytes, media_type="image/png"),
        ],
    )


async def click(ctx: RunContext[FinisherDeps], ref: str) -> str:
    """Click an interactive element by aria-ref.

    Purpose:
        Used for buttons, expanders, combobox triggers, and the
        country-flag widget. Refuses to click anything whose
        accessible name starts with ``submit``/``apply``/``send``.
    Args:
        ctx: Tool run context.
        ref: aria-ref of the element (``"e5"`` or ``"5"``).
    Returns:
        Confirmation string the model reads next turn.
    Raises:
        ModelRetry: On invalid ref, missing element, or submit attempt.
    """

    normalized = _normalize_aria_ref(ref)
    locator = ctx.deps.page.locator(f"aria-ref={normalized}")

    try:
        count = await locator.count()
    except Exception as exc:
        raise ModelRetry(
            f"Could not resolve ref {ref!r}: {exc}. Call get_snapshot() first."
        ) from exc
    if count == 0:
        raise ModelRetry(
            f"Ref {ref!r} not found in current snapshot. Call get_snapshot() first."
        )

    accessible_name = ""
    try:
        accessible_name = await locator.first.get_attribute("aria-label") or ""
        if not accessible_name:
            accessible_name = (await locator.first.text_content()) or ""
    except Exception:  # pragma: no cover - best-effort name capture
        accessible_name = ""

    if _is_forbidden_name(accessible_name):
        raise ModelRetry(
            f"Refused to click {accessible_name!r} — submit/apply buttons "
            "are reserved for the worker. End the run via complete_apply."
        )

    try:
        await locator.first.click()
    except Exception as exc:
        raise ModelRetry(
            f"Click on ref {ref!r} failed: {exc}. The element may have "
            "re-rendered. Call get_snapshot() and retry."
        ) from exc

    return f"clicked ref {normalized} ({accessible_name!r})"


async def fill(ctx: RunContext[FinisherDeps], ref: str, value: str) -> str:
    """Type ``value`` into a text input or textarea.

    Purpose:
        Tier-1 direct fills and Tier-2 drafted essays both flow through
        this tool. The agent must call ``flag_for_verify`` separately
        for drafts; this tool is a pure write.
    Args:
        ctx: Tool run context.
        ref: aria-ref of the field.
        value: Text to type.
    Returns:
        Confirmation string.
    Raises:
        ModelRetry: On unresolvable ref or fill failure.
    """

    normalized = _normalize_aria_ref(ref)
    locator = ctx.deps.page.locator(f"aria-ref={normalized}")

    if await locator.count() == 0:
        raise ModelRetry(
            f"Ref {ref!r} not found. Call get_snapshot() first."
        )

    try:
        await locator.first.fill(value)
    except Exception as exc:
        raise ModelRetry(
            f"fill on ref {ref!r} failed: {exc}. Element may not be editable."
        ) from exc

    ctx.deps.fields_filled_count += 1
    preview = value if len(value) <= 80 else value[:77] + "..."
    return f"filled ref {normalized} with {preview!r}"


async def select(ctx: RunContext[FinisherDeps], ref: str, value: str) -> str:
    """Pick ``value`` from a ``<select>`` or React-Select combobox.

    Purpose:
        Tier-1 dropdown fills (country, state, "how did you hear",
        pronouns). For React-Select widgets the agent typically calls
        ``click(combobox)`` first to open the listbox, then ``select``
        with the option text.
    Args:
        ctx: Tool run context.
        ref: aria-ref of the select / combobox.
        value: Option label to choose.
    Returns:
        Confirmation string.
    Raises:
        ModelRetry: When ``value`` is not in the option list. The
            error message enumerates valid options so the model can
            retry without re-snapshotting.
    """

    normalized = _normalize_aria_ref(ref)
    locator = ctx.deps.page.locator(f"aria-ref={normalized}")

    if await locator.count() == 0:
        raise ModelRetry(
            f"Ref {ref!r} not found. Call get_snapshot() first."
        )

    # Try native <select> path first; fall through to listbox option click.
    try:
        await locator.first.select_option(label=value)
        ctx.deps.fields_filled_count += 1
        return f"selected {value!r} on ref {normalized}"
    except Exception as native_exc:
        # React-Select / listbox path: enumerate visible options, click match.
        try:
            options_locator = ctx.deps.page.get_by_role("option")
            option_count = await options_locator.count()
            visible_options: list[str] = []
            for index in range(option_count):
                option_text = await options_locator.nth(index).text_content()
                if option_text is not None:
                    visible_options.append(option_text.strip())

            if value not in visible_options:
                raise ModelRetry(
                    f"{value!r} is not a valid option for ref {ref!r}. "
                    f"Valid options: {visible_options or '(none visible — click the combobox first)'}"
                )

            await options_locator.filter(has_text=value).first.click()
            ctx.deps.fields_filled_count += 1
            return f"selected {value!r} on ref {normalized} via listbox option"
        except ModelRetry:
            raise
        except Exception as exc:
            raise ModelRetry(
                f"select on ref {ref!r} failed: native error {native_exc}; "
                f"listbox fallback error {exc}. Call get_snapshot() and retry."
            ) from exc


async def wait_for_dom_quiet(
    ctx: RunContext[FinisherDeps],
    ms: int = _DEFAULT_DOM_QUIET_MS,
) -> str:
    """Block until no DOM mutations have occurred for ``ms`` milliseconds.

    Purpose:
        Playwright's built-in stability is bounding-box only (~33ms);
        insufficient for Ashby's React re-mounts. MutationObserver-based
        quiescence catches the case where the form rebuilds itself.
    Args:
        ctx: Tool run context.
        ms: Required quiet window in milliseconds (default 300).
    Returns:
        Confirmation string.
    """

    quiet_ms = max(int(ms), 50)
    timeout_ms = _DOM_QUIET_TIMEOUT_MS

    script = """
    async ({ quietMs, timeoutMs }) => {
        return await new Promise((resolve) => {
            const deadline = setTimeout(() => {
                obs.disconnect();
                resolve('timeout');
            }, timeoutMs);
            let timer = setTimeout(() => {
                obs.disconnect();
                clearTimeout(deadline);
                resolve('quiet');
            }, quietMs);
            const obs = new MutationObserver(() => {
                clearTimeout(timer);
                timer = setTimeout(() => {
                    obs.disconnect();
                    clearTimeout(deadline);
                    resolve('quiet');
                }, quietMs);
            });
            obs.observe(document.body, {
                childList: true,
                subtree: true,
                attributes: true,
            });
        });
    }
    """

    try:
        outcome = await ctx.deps.page.evaluate(
            script, {"quietMs": quiet_ms, "timeoutMs": timeout_ms}
        )
    except Exception as exc:
        # Falling back to a flat sleep keeps the loop moving on browsers
        # that disallow evaluate (rare; defensive only).
        logger.debug("wait_for_dom_quiet evaluate failed ({}); using sleep", exc)
        await asyncio.sleep(quiet_ms / 1000.0)
        outcome = "sleep_fallback"

    return f"dom_quiet={outcome} after {quiet_ms}ms quiet window"


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
        ref: aria-ref of the deferred field.
        label: Visible label captured from the snapshot.
        field_type: One of ``select``/``textarea``/``checkbox``/...
        category: ``sponsorship``/``eeo``/``salary``/``start_date``/``other``.
        reason: Short justification (one sentence).
    Returns:
        Confirmation string.
    """

    normalized = _normalize_aria_ref(ref)
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
        The agent ALSO calls ``fill`` separately so the value appears
        in the form. This tool only registers that the value must be
        approved by the human before the gate may auto-submit.
    Args:
        ctx: Tool run context.
        ref: aria-ref of the drafted field.
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

    normalized = _normalize_aria_ref(ref)
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


# Tools registered on the agent. complete_apply is wired separately as
# the output tool (see agent.py).
FINISHER_TOOLS: tuple[Any, ...] = (
    get_snapshot,
    click,
    fill,
    select,
    wait_for_dom_quiet,
    defer,
    lookup_cached_answer,
    flag_for_verify,
)


__all__ = [
    "FINISHER_TOOLS",
    "click",
    "defer",
    "fill",
    "flag_for_verify",
    "get_snapshot",
    "lookup_cached_answer",
    "select",
    "wait_for_dom_quiet",
]
