"""agent-browser CLI-backed tools for the apply finisher.

Each browser tool shells out to the ``agent-browser`` CLI via
``asyncio.create_subprocess_exec`` (async; matches the async agent loop).
State-only tools (``lookup_cached_answer``, ``defer``, ``flag_for_verify``,
``complete_apply``) are unchanged from the Playwright version.
"""

from __future__ import annotations

import asyncio
import json
import shlex
from typing import Any

from loguru import logger
from pydantic_ai import ModelRetry, RunContext, ToolReturn

from src.agents.apply_finisher.schemas import (
    DeferredQuestion,
    DraftedField,
    FinisherDeps,
)

_MAX_SNAPSHOT_CHARS: int = 24_000
_TRUNCATION_SENTINEL: str = "\n...(snapshot truncated for length)"

_FORBIDDEN_CLICK_NAME_PREFIXES: tuple[str, ...] = (
    "submit",
    "apply",
    "send application",
    "send",
    "continue to submit",
)

# After a combobox is clicked, wait this long for the listbox to render
# before trying to click an option in it.
_COMBOBOX_SETTLE_MS: int = 250


def _normalize_ab_ref(ref: str) -> str:
    """Normalize a ref to the ``@eN`` form agent-browser expects.

    Accepts ``"@e5"``, ``"e5"``, or ``"5"``; the model emits any of these.

    Args:
        ref: Caller-supplied ref string.
    Returns:
        ``"@eN"`` form.
    Raises:
        ModelRetry: When ``ref`` is empty or unparseable.
    """

    candidate = (ref or "").strip()
    if not candidate:
        raise ModelRetry("ref must be non-empty (e.g. '@e5' or 'e5').")
    if candidate.startswith("@e") and candidate[2:].isdigit():
        return candidate
    if candidate.startswith("e") and candidate[1:].isdigit():
        return f"@{candidate}"
    if candidate.isdigit():
        return f"@e{candidate}"
    raise ModelRetry(
        f"ref {ref!r} is not a valid agent-browser ref (expected '@eN', 'eN', or 'N')."
    )


def _is_forbidden_name(accessible_name: str) -> bool:
    cleaned = (accessible_name or "").strip().lower()
    return any(cleaned.startswith(prefix) for prefix in _FORBIDDEN_CLICK_NAME_PREFIXES)


async def _ab(args: list[str]) -> tuple[int, str, str]:
    """Run ``agent-browser <args>`` and return (returncode, stdout, stderr).

    Wraps async subprocess so tool functions stay non-blocking.
    """

    cmd = ["agent-browser"] + args
    logger.debug("ab> {}", shlex.join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await proc.communicate()
    stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
    stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
    rc = proc.returncode if proc.returncode is not None else -1
    if stderr:
        logger.debug("ab stderr: {}", stderr)
    logger.debug("ab< rc={} stdout={!r}", rc, stdout[:200])
    return rc, stdout, stderr


async def _ab_json(args: list[str]) -> tuple[int, Any, str]:
    """Run ``agent-browser <args> --json`` and parse the JSON output.

    Returns:
        (returncode, parsed_object_or_None, stderr)
    """

    rc, stdout, stderr = await _ab(args + ["--json"])
    parsed: Any = None
    if stdout:
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError:
            logger.warning("ab: JSON parse failed for stdout={!r}", stdout[:200])
    return rc, parsed, stderr


# ---------------------------------------------------------------------------
# Browser tools
# ---------------------------------------------------------------------------


async def get_snapshot(ctx: RunContext[FinisherDeps]) -> str:
    """Return the accessibility tree for the application form.

    Uses ``agent-browser snapshot -i -c`` scoped to the form root CSS
    selector. Interactive-only (``-i``) and compact (``-c``) by default
    to keep token cost down. Refs in the output are ``@eN``; they become
    stale after any page mutation — re-call before the next ref interaction.

    Args:
        ctx: Tool run context carrying ``FinisherDeps``.
    Returns:
        Snapshot YAML text (truncated at 24k chars if needed).
    Raises:
        ModelRetry: When agent-browser returns a non-zero exit code.
    """

    selector = ctx.deps.form_root_css
    args = ["snapshot", "-i", "-c"]
    if selector:
        args += ["-s", selector]

    rc, stdout, stderr = await _ab(args)
    if rc != 0:
        raise ModelRetry(
            f"get_snapshot failed (rc={rc}): {stderr or stdout or 'no output'}. "
            "Verify agent-browser is connected to the browser session."
        )

    stripped = (stdout or "").strip()
    if not stripped:
        raise ModelRetry(
            "Snapshot returned empty output. The form may not be loaded yet — "
            "wait 500ms and retry."
        )

    # Update last_snapshot_names from the snapshot text for forbidden-click guard.
    # Simple parse: lines like "@e5 [button] "Submit""
    names: dict[str, str] = {}
    for line in stripped.splitlines():
        line = line.strip()
        if not line.startswith("@e"):
            continue
        parts = line.split(None, 2)
        if len(parts) >= 3:
            ref_token = parts[0]
            # parts[2] may be '"Label"' — strip quotes
            name = parts[2].strip().strip('"')
            names[ref_token] = name
    ctx.deps.last_snapshot_names = names

    if len(stripped) > _MAX_SNAPSHOT_CHARS:
        stripped = stripped[:_MAX_SNAPSHOT_CHARS] + _TRUNCATION_SENTINEL
    return stripped


async def fill(ctx: RunContext[FinisherDeps], ref: str, value: str) -> str:
    """Clear and type ``value`` into a plain text input or textarea.

    Do NOT use for comboboxes / React-Select / typeahead widgets — those
    require ``select_option``.

    Args:
        ctx: Tool run context.
        ref: ``@eN`` ref of the field (also accepts ``eN`` or ``N``).
        value: Text to type.
    Returns:
        Confirmation string.
    Raises:
        ModelRetry: On ref validation failure or CLI error.
    """

    normalized = _normalize_ab_ref(ref)
    rc, stdout, stderr = await _ab(["fill", normalized, value])
    if rc != 0:
        raise ModelRetry(
            f"fill on {normalized!r} failed (rc={rc}): "
            f"{stderr or stdout or 'unknown error'}. "
            "Ref may be stale — call get_snapshot() and retry."
        )

    ctx.deps.fields_filled_count += 1
    preview = value if len(value) <= 80 else value[:77] + "..."
    return f"filled {normalized} with {preview!r}"


async def select_option(
    ctx: RunContext[FinisherDeps],
    combobox_label: str,
    option_value: str,
) -> str:
    """Pick an option from a React-Select / typeahead combobox.

    Two-step mandatory pattern:
    1. ``agent-browser find role combobox click --name <combobox_label>``
       — opens the dropdown.
    2. Wait 250ms for the listbox to render.
    3. ``agent-browser find text <option_value> click --exact``
       — clicks the option.

    Never use ``fill`` for comboboxes — React-Select ignores programmatic
    input. This tool handles country, phone country code, location,
    Yes/No listboxes, and all Greenhouse React-Select widgets.

    Args:
        ctx: Tool run context.
        combobox_label: Accessible name of the combobox (e.g. ``"Country"``).
        option_value: Exact text of the option to click (e.g. ``"United States"``).
    Returns:
        Confirmation string.
    Raises:
        ModelRetry: When either step fails.
    """

    # Step 1: open the combobox
    rc, stdout, stderr = await _ab(
        ["find", "role", "combobox", "click", "--name", combobox_label]
    )
    if rc != 0:
        raise ModelRetry(
            f"select_option: could not open combobox {combobox_label!r} "
            f"(rc={rc}): {stderr or stdout or 'unknown error'}. "
            "Check the label matches the combobox's accessible name in the snapshot."
        )

    # Step 2: wait for listbox to render
    await asyncio.sleep(_COMBOBOX_SETTLE_MS / 1000.0)

    # Step 3: click the option by exact text
    rc2, stdout2, stderr2 = await _ab(
        ["find", "text", option_value, "click", "--exact"]
    )
    if rc2 != 0:
        raise ModelRetry(
            f"select_option: option {option_value!r} not found in {combobox_label!r} "
            f"listbox (rc={rc2}): {stderr2 or stdout2 or 'no output'}. "
            "Call get_snapshot() to see what options are visible, then retry with the "
            "exact option text."
        )

    ctx.deps.fields_filled_count += 1
    return f"selected {option_value!r} in combobox {combobox_label!r}"


async def select_radio(
    ctx: RunContext[FinisherDeps],
    group_label: str,
    option_value: str,
) -> str:
    """Click a radio button by its option label within a named radio group.

    Tries ``agent-browser find role radio click --name <option_value>`` first
    (works when the radio has a direct accessible name). Falls back to clicking
    the group heading via ``find role group click --name <group_label>``, then
    clicking the option text with ``find text <option_value> click --exact``.

    Args:
        ctx: Tool run context.
        group_label: Accessible name of the radio group (e.g. ``"Gender"``).
        option_value: Label of the radio option to select (e.g. ``"Male"``).
    Returns:
        Confirmation string.
    Raises:
        ModelRetry: When the option cannot be found via either strategy.
    """

    # Primary: direct radio by accessible name (works on most ATS)
    rc, stdout, stderr = await _ab(
        ["find", "role", "radio", "click", "--name", option_value]
    )
    if rc == 0:
        ctx.deps.fields_filled_count += 1
        return f"selected radio {option_value!r} in group {group_label!r}"

    logger.debug(
        "select_radio primary path failed (rc={}); trying group fallback", rc
    )

    # Fallback: focus the group, then click the option text
    rc2, stdout2, stderr2 = await _ab(
        ["find", "role", "group", "click", "--name", group_label]
    )
    if rc2 != 0:
        # Group click may not be supported — go straight to text search
        logger.debug("select_radio: group focus failed (rc={}), trying text click", rc2)

    rc3, stdout3, stderr3 = await _ab(
        ["find", "text", option_value, "click", "--exact"]
    )
    if rc3 != 0:
        raise ModelRetry(
            f"select_radio: could not find option {option_value!r} in group "
            f"{group_label!r}. Primary error: {stderr or stdout}. "
            f"Fallback error: {stderr3 or stdout3}. "
            "Call get_snapshot() to verify the option text exactly."
        )

    ctx.deps.fields_filled_count += 1
    return f"selected radio {option_value!r} in group {group_label!r} (text fallback)"


async def click(ctx: RunContext[FinisherDeps], ref_or_locator: str) -> str:
    """Click an element by ``@eN`` ref or CSS selector.

    Refuses to click any element whose accessible name (captured from the
    last snapshot) starts with a submit-family prefix. Use ``select_option``
    instead of click for combobox triggers — ``click`` is for buttons,
    expanders, checkboxes, and non-combobox interactive elements.

    Args:
        ctx: Tool run context.
        ref_or_locator: ``@eN`` ref (preferred) or CSS selector.
    Returns:
        Confirmation string.
    Raises:
        ModelRetry: On forbidden-click guard or CLI error.
    """

    target = (ref_or_locator or "").strip()
    if not target:
        raise ModelRetry("ref_or_locator must be non-empty.")

    # Normalize @eN refs; pass CSS selectors through unchanged.
    normalized = target
    if target.startswith("@e") or target.startswith("e") and target[1:].isdigit() or target.isdigit():
        try:
            normalized = _normalize_ab_ref(target)
        except ModelRetry:
            pass  # not a ref, treat as CSS selector

    # Forbidden-click guard using the last snapshot's name map.
    name_map = getattr(ctx.deps, "last_snapshot_names", {})
    accessible_name = name_map.get(normalized, "")
    if _is_forbidden_name(accessible_name):
        raise ModelRetry(
            f"Refused to click {accessible_name!r} — submit/apply buttons are "
            "reserved for the worker. Call complete_apply() to end your run."
        )

    rc, stdout, stderr = await _ab(["click", normalized])
    if rc != 0:
        raise ModelRetry(
            f"click on {normalized!r} failed (rc={rc}): "
            f"{stderr or stdout or 'unknown error'}. "
            "Ref may be stale — call get_snapshot() and retry."
        )

    return f"clicked {normalized!r}" + (f" ({accessible_name!r})" if accessible_name else "")


async def press(ctx: RunContext[FinisherDeps], key: str) -> str:
    """Press a key or key combination.

    Useful for Tab between fields, Enter to confirm a typeahead selection,
    or Escape to close an accidental modal.

    Args:
        ctx: Tool run context.
        key: Key name or chord (e.g. ``"Tab"``, ``"Enter"``, ``"Control+a"``).
    Returns:
        Confirmation string.
    Raises:
        ModelRetry: On CLI error.
    """

    if not (key or "").strip():
        raise ModelRetry("key must be non-empty (e.g. 'Tab', 'Enter').")

    rc, stdout, stderr = await _ab(["press", key])
    if rc != 0:
        raise ModelRetry(
            f"press {key!r} failed (rc={rc}): {stderr or stdout or 'unknown error'}."
        )

    return f"pressed {key!r}"


async def upload(ctx: RunContext[FinisherDeps], ref: str, file_path: str) -> str:
    """Upload a file to a file-input element.

    Resume upload is handled by the worker before the finisher runs.
    This tool covers cover-letter uploads and any other file inputs the
    finisher encounters.

    Args:
        ctx: Tool run context.
        ref: ``@eN`` ref of the file input.
        file_path: Absolute path to the file on disk.
    Returns:
        Confirmation string.
    Raises:
        ModelRetry: On ref validation failure or CLI error.
    """

    normalized = _normalize_ab_ref(ref)
    rc, stdout, stderr = await _ab(["upload", normalized, file_path])
    if rc != 0:
        raise ModelRetry(
            f"upload to {normalized!r} failed (rc={rc}): "
            f"{stderr or stdout or 'unknown error'}."
        )

    return f"uploaded {file_path!r} to {normalized}"


async def scroll_into_view(ctx: RunContext[FinisherDeps], ref: str) -> str:
    """Scroll an element into the viewport before clicking it.

    Call this before ``click`` on any element that may be below the fold
    (EEO fieldsets, cover-letter upload, submit area).

    Args:
        ctx: Tool run context.
        ref: ``@eN`` ref of the element.
    Returns:
        Confirmation string.
    Raises:
        ModelRetry: On ref validation failure or CLI error.
    """

    normalized = _normalize_ab_ref(ref)
    rc, stdout, stderr = await _ab(["scrollintoview", normalized])
    if rc != 0:
        raise ModelRetry(
            f"scroll_into_view on {normalized!r} failed (rc={rc}): "
            f"{stderr or stdout or 'unknown error'}."
        )

    return f"scrolled {normalized} into view"


async def wait_for(
    ctx: RunContext[FinisherDeps],
    text: str | None = None,
    url_pattern: str | None = None,
    load_state: str | None = None,
    ms: int | None = None,
) -> str:
    """Wait for a page condition before continuing.

    Pass exactly one of the keyword args:
    - ``text``: wait until that substring appears on the page.
    - ``url_pattern``: wait until the current URL matches the glob pattern.
    - ``load_state``: ``"load"`` / ``"domcontentloaded"`` / ``"networkidle"``.
    - ``ms``: plain millisecond sleep (last resort; prefer the above).

    Args:
        ctx: Tool run context.
        text: Substring to wait for on the page.
        url_pattern: URL glob pattern (e.g. ``"**/dashboard"``).
        load_state: Playwright load-state token.
        ms: Milliseconds to wait unconditionally.
    Returns:
        Confirmation string.
    Raises:
        ModelRetry: When no condition is supplied or the wait times out.
    """

    if text is not None:
        args = ["wait", "--text", text]
        desc = f"text={text!r}"
    elif url_pattern is not None:
        args = ["wait", "--url", url_pattern]
        desc = f"url={url_pattern!r}"
    elif load_state is not None:
        valid_states = {"load", "domcontentloaded", "networkidle"}
        if load_state not in valid_states:
            raise ModelRetry(
                f"load_state {load_state!r} is not valid. "
                f"Choose from: {sorted(valid_states)}."
            )
        args = ["wait", "--load", load_state]
        desc = f"load_state={load_state!r}"
    elif ms is not None:
        wait_ms = max(int(ms), 50)
        args = ["wait", str(wait_ms)]
        desc = f"ms={wait_ms}"
    else:
        raise ModelRetry(
            "wait_for requires at least one argument: text, url_pattern, "
            "load_state, or ms."
        )

    rc, stdout, stderr = await _ab(args)
    if rc != 0:
        raise ModelRetry(
            f"wait_for({desc}) timed out or failed (rc={rc}): "
            f"{stderr or stdout or 'unknown error'}."
        )

    return f"waited for {desc}"


async def screenshot(ctx: RunContext[FinisherDeps], path: str) -> str:
    """Save a screenshot to ``path`` for debugging.

    Call when confused about form state; cheap operation. The screenshot
    is saved on disk — the path is returned so logs are traceable.

    Args:
        ctx: Tool run context.
        path: Destination file path (e.g. ``"/tmp/finisher_debug.png"``).
    Returns:
        Confirmation string with saved path.
    Raises:
        ModelRetry: On CLI error.
    """

    if not (path or "").strip():
        raise ModelRetry("path must be non-empty.")

    rc, stdout, stderr = await _ab(["screenshot", path])
    if rc != 0:
        raise ModelRetry(
            f"screenshot failed (rc={rc}): {stderr or stdout or 'unknown error'}."
        )

    return f"screenshot saved to {path!r}"


# ---------------------------------------------------------------------------
# State-only tools (no browser interaction — unchanged from Playwright version)
# ---------------------------------------------------------------------------


async def lookup_cached_answer(
    ctx: RunContext[FinisherDeps],
    question_text: str,
) -> str:
    """Look up a previously-cached answer by fuzzy match.

    Args:
        ctx: Tool run context.
        question_text: The question label as it appears on the form.
    Returns:
        The cached answer string, or ``"<no cache hit>"`` when nothing matches.
    """

    hit = ctx.deps.cache.lookup(question_text, company=ctx.deps.target_company)
    if hit is None:
        return "<no cache hit>"
    return (
        f"<cache_hit score={hit.score:.0f} "
        f"anonymized={hit.was_anonymized}>\n{hit.entry.answer}"
    )


async def defer(
    ctx: RunContext[FinisherDeps],
    ref: str,
    label: str,
    field_type: str,
    category: str,
    reason: str,
) -> str:
    """Record a Tier-3 field the human must answer.

    Do NOT fill the field before calling this. The runner reads
    ``recorded_deferrals`` when synthesizing the final ``FinisherResult``.

    Args:
        ctx: Tool run context.
        ref: ``@eN`` ref of the deferred field.
        label: Visible label captured from the snapshot.
        field_type: One of ``select``/``textarea``/``checkbox``/etc.
        category: ``sponsorship`` / ``salary`` / ``other``.
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
    return f"deferred {normalized} (category={category})"


async def flag_for_verify(
    ctx: RunContext[FinisherDeps],
    ref: str,
    label: str,
    drafted_value: str,
    confidence: float,
    reasoning: str,
) -> str:
    """Record a Tier-2 draft for human review.

    The agent ALSO calls ``fill`` separately so the value appears in the form.
    This tool only registers that the value must be approved before auto-submit.

    Args:
        ctx: Tool run context.
        ref: ``@eN`` ref of the drafted field.
        label: Visible label captured pre-fill.
        drafted_value: The text the agent wrote.
        confidence: Self-reported confidence in [0.0, 1.0].
        reasoning: One-sentence justification.
    Returns:
        Confirmation string.
    Raises:
        ModelRetry: When ``confidence`` is outside [0.0, 1.0].
    """

    normalized = _normalize_ab_ref(ref)
    if not 0.0 <= confidence <= 1.0:
        raise ModelRetry(
            f"confidence={confidence} is outside [0.0, 1.0]. Re-emit with a value in that range."
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
    return f"flagged {normalized} for verify (confidence={confidence:.2f})"


# Tools registered on the agent. complete_apply is wired separately as
# the output tool (see agent.py).
FINISHER_TOOLS: tuple[Any, ...] = (
    get_snapshot,
    fill,
    select_option,
    select_radio,
    click,
    press,
    upload,
    scroll_into_view,
    wait_for,
    screenshot,
    lookup_cached_answer,
    defer,
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
    "press",
    "screenshot",
    "scroll_into_view",
    "select_option",
    "select_radio",
    "upload",
    "wait_for",
]
