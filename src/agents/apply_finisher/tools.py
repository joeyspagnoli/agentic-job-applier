"""Pydantic AI tools for the apply-finisher.

The browser surface is split into:

- ``agent_browser(args)`` — the generic escape hatch that runs an
  arbitrary ``agent-browser`` CLI command in the persistent CDP
  session the worker attached.
- A small catalog of **narrow, one-CLI-call** helpers that each wrap
  a specific subprocess invocation the model has historically failed
  to substitute correctly. Each helper takes typed args (no
  placeholders for the model to interpolate) so the agent reasons
  about *what* to do, not *how* to escape JS literals or build the
  exact CSS selector.

The four state tools (``lookup_cached_answer``, ``defer``,
``flag_for_verify`` plus the ``complete_apply`` output tool
registered in ``agent.py``) touch ``FinisherDeps`` state — answer
cache, deferral list, drafted-field list, termination — and never
see the browser.

The browser-touching CLI plumbing lives in
:mod:`src.agents.apply_finisher.browser_cli`.
"""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic_ai import ModelRetry, RunContext

from src.agents.apply_finisher.browser_cli import invoke_agent_browser_cli
from src.agents.apply_finisher.schemas import (
    DeferredQuestion,
    DraftedField,
    FinisherDeps,
)

# Hard cap on react-select option-pick filter strings. 60 chars covers
# every Greenhouse / Ashby answer label we've seen; longer suggests the
# caller is pasting prose by mistake.
_MAX_FILTER_LEN: int = 60

# Listbox-settle delay. The React-Select listbox takes ~250-400ms to
# mount after the trigger click; without it, the next keyboard-insert
# goes into the body instead of the (still-empty) input. Same window
# applies between filter typing and option click for the filtered
# option list to settle.
_REACT_SELECT_SETTLE_SECONDS: float = 0.45

# Verifier eval template. Reads .select__single-value text via DOM
# traversal from the field input id. Returns the picked label or the
# literal string ``EMPTY``. Single-quoted JS so it shells cleanly.
_VERIFY_COMBOBOX_JS_TEMPLATE: str = (
    "var el=document.getElementById('{field_id}');"
    "var s=el&&el.closest('.select-shell');"
    "var sv=s&&s.querySelector('[class*=\"single-value\"]');"
    "sv?sv.textContent:'EMPTY'"
)

# Native HTMLInputElement-value setter + dispatched input event. This
# is the only way React-Select Async picks up programmatic input — the
# CLI's ``fill`` / ``type`` / ``keyboard`` paths bypass React's
# synthetic-event guard and the dropdown never opens.
_DISPATCH_ASYNC_QUERY_JS_TEMPLATE: str = (
    "var i=document.getElementById('{field_id}');"
    "i.focus();"
    "var s=Object.getOwnPropertyDescriptor("
    "window.HTMLInputElement.prototype,'value').set;"
    "s.call(i,'{query}');"
    "i.dispatchEvent(new Event('focus',{{bubbles:true}}));"
    "i.dispatchEvent(new Event('input',{{bubbles:true}}));"
    "'dispatched'"
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


def _validate_field_id(field_id: str) -> str:
    """Reject field ids that would break JS evaluation downstream.

    The narrow combobox helpers interpolate ``field_id`` into a JS
    string. Single quotes / angle brackets would either escape the
    literal or trip the prompt-injection guard. Greenhouse / Ashby
    field ids match ``[A-Za-z0-9_\\-]+`` in practice.

    Also rejects snapshot-ref shape (``eN`` where ``N`` is purely
    digits) — those are agent-browser refs, not DOM ids, and the
    model has been mistakenly passing them. A DOM id looks like
    ``question_66747918`` / ``country`` / ``candidate-location``;
    never bare ``e3`` / ``e42``.

    Args:
        field_id: DOM id of the React-Select input element.
    Returns:
        The validated field id unchanged.
    Raises:
        ModelRetry: When ``field_id`` is empty, contains characters
            outside the allowed set, or matches the agent-browser
            snapshot-ref shape ``eN``.
    """

    stripped = (field_id or "").strip().lstrip("@")
    if not stripped:
        raise ModelRetry("field_id must be non-empty.")
    allowed = set(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    )
    if not set(stripped).issubset(allowed):
        raise ModelRetry(
            f"field_id {field_id!r} contains characters outside "
            "[A-Za-z0-9_-]. Use the bare DOM id from the snapshot."
        )
    if (
        len(stripped) >= 2
        and stripped[0] == "e"
        and stripped[1:].isdigit()
    ):
        raise ModelRetry(
            f"field_id {field_id!r} looks like an agent-browser snapshot "
            "ref (`eN`), not a DOM id. Pass the bare DOM id (e.g. "
            "'question_66747918', 'country', 'candidate-location') — "
            "you can read it from the snapshot's combobox row."
        )
    return stripped


async def agent_browser(
    args: list[str],
    expect_json: bool = False,
    timeout_seconds: float = 20.0,
) -> dict[str, Any]:
    """Run an arbitrary ``agent-browser`` CLI command in the CDP session.

    Purpose:
        Generic escape hatch for cases the narrow helpers don't cover
        (snapshots, plain-input fills, native-select picks, scroll,
        screenshot). Prefer a narrow helper when one exists — the
        helpers eliminate JS-substitution mistakes the model has made
        repeatedly.
    Args:
        args: CLI argv tail, e.g. ``["snapshot", "-i", "-c"]``. The
            ``agent-browser`` executable is prepended automatically.
        expect_json: Append ``--json`` (if absent) and parse stdout
            as JSON into ``data``.
        timeout_seconds: Wall-clock cap. Default 20s.
    Returns:
        ``{ok, command, stdout, stderr, exit_code, data?, error?}``.
    Raises:
        ModelRetry: When the binary is missing from the image.
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


async def open_combobox(field_id: str) -> dict[str, Any]:
    """Open a Greenhouse / Ashby React-Select combobox by field id.

    Purpose:
        Wraps the verified pattern
        ``click '[aria-labelledby="<field_id>-label"]'`` AND blocks
        for the React-Select listbox to mount before returning. The
        settle delay is mandatory: without it the next tool call
        lands on the body before the listbox finishes mounting, the
        filter goes nowhere, and the agent burns turns retrying.
    Args:
        field_id: DOM id of the React-Select input (e.g.
            ``"question_66747918"``, ``"country"``). Read from the
            snapshot's combobox row — NOT a ``@eN`` ref.
    Returns:
        The full ``invoke_agent_browser_cli`` result dict.
    Raises:
        ModelRetry: When ``field_id`` is empty or has illegal chars.
    """

    validated = _validate_field_id(field_id)
    selector = f"[aria-labelledby=\"{validated}-label\"]"
    # Scroll into view first — off-screen comboboxes may swallow the
    # click event silently in agent-browser's CDP implementation.
    # Best-effort; ignore failures (will hard-fail at click instead).
    await invoke_agent_browser_cli(["scrollintoview", selector])
    result = await invoke_agent_browser_cli(["click", selector])
    if result["ok"]:
        await asyncio.sleep(_REACT_SELECT_SETTLE_SECONDS)
    return result


async def type_combobox_filter(field_id: str, text: str) -> dict[str, Any]:
    """Type a filter string into a specific React-Select combobox input.

    Purpose:
        Greenhouse Q comboboxes expose ~245 options (240 country
        phone codes + the real 2-6 answers). Typing 3-6 characters
        narrows the visible list so the subsequent ``pick_option``
        click resolves uniquely.

        Targets the combobox input via its
        ``[aria-labelledby="<field_id>-label"]`` selector and uses
        the CLI's ``type`` action (which scopes events to the
        selector). Previous iterations used ``keyboard inserttext``
        which goes to the focused element — fragile because React-
        Select's listbox mount briefly takes focus away.
    Args:
        field_id: DOM id of the combobox input. Must match the field
            that was opened in the immediately-preceding
            ``open_combobox`` call.
        text: Filter substring. Keep short (≤60 chars enforced).
    Returns:
        Full CLI result dict.
    Raises:
        ModelRetry: When ``field_id`` is invalid, ``text`` is empty,
            or ``text`` exceeds ``_MAX_FILTER_LEN``.
    """

    validated = _validate_field_id(field_id)
    cleaned = (text or "").strip()
    if not cleaned:
        raise ModelRetry("text must be non-empty.")
    if len(cleaned) > _MAX_FILTER_LEN:
        raise ModelRetry(
            f"text is {len(cleaned)} chars (max {_MAX_FILTER_LEN}); "
            "pass a short unique prefix, not the full option label."
        )
    selector = f"[aria-labelledby=\"{validated}-label\"]"
    result = await invoke_agent_browser_cli(["type", selector, cleaned])
    if result["ok"]:
        await asyncio.sleep(_REACT_SELECT_SETTLE_SECONDS)
    return result


async def pick_option(
    option_text: str, exact: bool = False
) -> dict[str, Any]:
    """Click a listbox option by its visible text.

    Purpose:
        Wraps ``find role option click --name "<text>"`` (with
        optional ``--exact``). Scoping to ``role=option`` (rather
        than ``find text``) prevents the model from matching the
        same string in the input's preview or in unrelated page
        chrome.
    Args:
        option_text: The full visible label of the target option.
        exact: When True, append ``--exact`` so the match must equal
            the whole option text (use when one option is a prefix
            of another, e.g. ``"Yes"`` vs ``"Yes, …"``).
    Returns:
        Full CLI result dict.
    Raises:
        ModelRetry: When ``option_text`` is empty.
    """

    cleaned = (option_text or "").strip()
    if not cleaned:
        raise ModelRetry("option_text must be non-empty.")
    argv: list[str] = [
        "find", "role", "option", "click", "--name", cleaned,
    ]
    if exact:
        argv.append("--exact")
    return await invoke_agent_browser_cli(argv)


async def verify_combobox_filled(field_id: str) -> str:
    """Return the picked label of a React-Select combobox, or ``"EMPTY"``.

    Purpose:
        The snapshot lies for React-Select — a successfully-picked
        combobox still appears ``[expanded=false]`` with no value.
        The only source of truth is the ``.select__single-value``
        text inside the field's ``.select-shell``. This helper runs
        the verified eval against the supplied ``field_id`` — the
        model had been copying the placeholder ``<FIELD_ID>`` into
        the JS verbatim and querying the wrong node.
    Args:
        field_id: DOM id of the React-Select input (e.g.
            ``"question_66747918"``).
    Returns:
        The picked option text, or the literal string ``"EMPTY"``
        when no value is set, or ``"ERROR: <stderr>"`` when the CLI
        call itself failed.
    Raises:
        ModelRetry: When ``field_id`` is empty or has illegal chars.
    """

    validated = _validate_field_id(field_id)
    js = _VERIFY_COMBOBOX_JS_TEMPLATE.format(field_id=validated)
    result = await invoke_agent_browser_cli(["eval", js])
    if not result["ok"]:
        stderr = (result.get("stderr") or "").strip().splitlines()[:1]
        return f"ERROR: {stderr[0] if stderr else 'eval failed'}"
    return (result.get("stdout") or "").strip() or "EMPTY"


async def dispatch_async_typeahead_query(
    field_id: str, query: str
) -> dict[str, Any]:
    """Trigger a React-Select Async typeahead's network fetch.

    Purpose:
        The ``candidate-location`` field (and other React-Select
        Async widgets) ignore ``fill`` / ``type`` / ``keyboard``
        because they bypass React's synthetic-event guard. The only
        reliable path is the native HTMLInputElement value setter
        plus a dispatched ``input`` event. This helper runs that
        exact eval so the model never has to compose it.

        Caller must wait ~2 seconds after this returns for the
        network fetch to populate the listbox, then click an option.
    Args:
        field_id: DOM id of the typeahead input (e.g.
            ``"candidate-location"``).
        query: The text to inject (e.g. ``"Gainesville"``). Single
            quotes are rejected to avoid breaking the JS literal.
    Returns:
        Full CLI result dict. ``stdout`` is the literal
        ``"dispatched"`` on success.
    Raises:
        ModelRetry: When ``field_id`` or ``query`` is empty, when
            ``field_id`` has illegal chars, or when ``query``
            contains a single quote.
    """

    validated_id = _validate_field_id(field_id)
    cleaned = (query or "").strip()
    if not cleaned:
        raise ModelRetry("query must be non-empty.")
    if "'" in cleaned:
        raise ModelRetry(
            "query may not contain a single quote — the JS literal "
            "would break. Use a different filter or strip the quote."
        )
    js = _DISPATCH_ASYNC_QUERY_JS_TEMPLATE.format(
        field_id=validated_id, query=cleaned
    )
    return await invoke_agent_browser_cli(["eval", js])


async def defer(
    ctx: RunContext[FinisherDeps],
    ref: str,
    label: str,
    field_type: str,
    category: str,
    reason: str,
) -> str:
    """Record a Tier-3 field the human must answer.

    Args:
        ctx: Tool run context.
        ref: agent-browser ref (``"@e5"`` or ``"e5"`` or ``"5"``).
        label: Visible label captured from the snapshot.
        field_type: ``select`` / ``textarea`` / ``checkbox`` / ...
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
    return f"deferred ref {normalized} (category={category})"


async def lookup_cached_answer(
    ctx: RunContext[FinisherDeps],
    question_text: str,
) -> str:
    """Look up a previously-cached answer by fuzzy match.

    Args:
        ctx: Tool run context.
        question_text: The question label as it appears on the form.
    Returns:
        The cached answer string when found, or ``"<no cache hit>"``.
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
    """Record a Tier-2 draft for human review (you must ALSO fill it).

    Args:
        ctx: Tool run context.
        ref: agent-browser ref of the drafted field.
        label: Visible label captured pre-fill.
        drafted_value: The text you wrote.
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
    open_combobox,
    type_combobox_filter,
    pick_option,
    verify_combobox_filled,
    dispatch_async_typeahead_query,
    lookup_cached_answer,
    defer,
    flag_for_verify,
)


__all__ = [
    "FINISHER_TOOLS",
    "agent_browser",
    "defer",
    "dispatch_async_typeahead_query",
    "flag_for_verify",
    "lookup_cached_answer",
    "open_combobox",
    "pick_option",
    "type_combobox_filter",
    "verify_combobox_filled",
]
