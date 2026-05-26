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

import json
from typing import Any

from pydantic_ai import ModelRetry, RunContext

from src.agents.apply_finisher.browser_cli import invoke_agent_browser_cli
from src.agents.apply_finisher.schemas import (
    DeferredQuestion,
    DraftedField,
    FinisherDeps,
)

# Wall-clock cap for the fill_combobox eval. The eval includes a 500ms
# open-menu settle + 300ms pick-commit settle + DOM walking + scroll, so
# 15s is generous and only trips on a genuinely wedged page.
_FILL_COMBOBOX_TIMEOUT_SECONDS: float = 15.0

# The eval JS that drives a React-Select combobox end-to-end inside one
# agent-browser subprocess. Three pieces of context every reader needs:
#
# 1. React-Select on Cloudflare's Greenhouse build does NOT commit a
#    pick from a plain `click` event. Verified live 2026-05-26: every
#    `find role option click` and every `eval target.click()` left the
#    form blank with no .select__single-value rendered. Only the full
#    sequence PointerEvent(pointerdown) + MouseEvent(mousedown) +
#    PointerEvent(pointerup) + MouseEvent(mouseup) + MouseEvent(click)
#    on the option element causes onChange to fire.
#
# 2. The intl-tel-input country picker pre-renders all 244 country
#    options as hidden `[role="option"]` elements in the DOM, even when
#    no menu is open. A global `find role option` therefore competes
#    with 244 phantoms and either picks the wrong country or returns
#    "no match". Scoping the option query to the field's own
#    `.select-shell .select__menu` sidesteps the collision entirely.
#
# 3. Field id is interpolated as a JS string literal — `_validate_field_id`
#    rejects anything outside `[A-Za-z0-9_-]`, so it cannot escape the
#    literal. `target_option` is passed via JSON.stringify on the
#    Python side (no shell quoting risk).
_FILL_COMBOBOX_JS_TEMPLATE: str = """\
(async () => {{
  const FIELD_ID = '{field_id}';
  const TARGET = {target_json};
  const EXACT = {exact_json};
  const EVT = {{ bubbles: true, cancelable: true, button: 0, pointerType: 'mouse' }};

  const input = document.getElementById(FIELD_ID);
  if (!input) return JSON.stringify({{ ok: false, step: 'lookup', error: 'no element with id ' + FIELD_ID }});

  const control = input.closest('[class*=\"select__control\"]');
  const shell = input.closest('.select-shell') || control?.parentElement;
  if (!control || !shell) return JSON.stringify({{ ok: false, step: 'lookup', error: 'no React-Select control or shell' }});

  try {{ control.scrollIntoView({{ block: 'center', behavior: 'instant' }}); }} catch (e) {{}}

  control.dispatchEvent(new PointerEvent('pointerdown', EVT));
  control.dispatchEvent(new MouseEvent('mousedown', EVT));
  control.dispatchEvent(new PointerEvent('pointerup', EVT));
  control.dispatchEvent(new MouseEvent('mouseup', EVT));

  await new Promise(r => setTimeout(r, 500));

  const menu = shell.querySelector('[class*=\"select__menu\"]');
  if (!menu) return JSON.stringify({{ ok: false, step: 'open_menu', error: 'menu did not mount after click' }});

  const opts = Array.from(menu.querySelectorAll('[role=\"option\"], [class*=\"select__option\"]'));
  if (opts.length === 0) return JSON.stringify({{ ok: false, step: 'open_menu', error: 'menu rendered but contains no options' }});

  const normalize = (s) => (s || '').trim().replace(/[\\u2018\\u2019]/g, \"'\");
  const targetNorm = normalize(TARGET);
  const target = opts.find(o => {{
    const t = normalize(o.textContent);
    return EXACT ? t === targetNorm : t.includes(targetNorm);
  }});
  if (!target) {{
    return JSON.stringify({{
      ok: false,
      step: 'find_option',
      error: 'no option matched target',
      target: TARGET,
      options: opts.map(o => normalize(o.textContent)),
    }});
  }}

  try {{ target.scrollIntoView({{ block: 'center', behavior: 'instant' }}); }} catch (e) {{}}

  target.dispatchEvent(new PointerEvent('pointerdown', EVT));
  target.dispatchEvent(new MouseEvent('mousedown', EVT));
  target.dispatchEvent(new PointerEvent('pointerup', EVT));
  target.dispatchEvent(new MouseEvent('mouseup', EVT));
  target.dispatchEvent(new MouseEvent('click', EVT));

  await new Promise(r => setTimeout(r, 300));

  const sv = shell.querySelector('.select__single-value')?.textContent?.trim() || '';
  if (!sv) {{
    return JSON.stringify({{ ok: false, step: 'verify', error: 'pick fired but .select__single-value is empty' }});
  }}
  return JSON.stringify({{ ok: true, picked: sv }});
}})()
"""

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


async def fill_combobox(
    field_id: str,
    target_option: str,
    exact: bool = False,
) -> str:
    """Open a React-Select combobox, pick an option, and verify the commit.

    Purpose:
        One agent-browser ``eval`` invocation that drives the React-Select
        widget end-to-end using real ``PointerEvent`` + ``MouseEvent``
        sequences. Replaces the prior approach (open via CLI ``click`` →
        ``find role option click``) which failed silently on Cloudflare's
        Greenhouse build because React-Select v4 does not commit a pick
        from a bare ``click`` event — verified live 2026-05-26 across
        every combobox on the form.

        Why eval and not the CLI's verbs:

        - React-Select listens for ``mousedown`` (not ``click``) on the
          option to commit the pick. The CLI's ``click`` and ``find role
          option click`` only emit the ``click`` event, so picks never
          land.
        - The page renders ~244 hidden ``[role="option"]`` elements from
          intl-tel-input's country picker AT ALL TIMES. A global
          ``find role option`` competes with those phantoms and either
          returns no match or clicks the wrong country. The eval scopes
          option lookup to the field's own ``.select-shell .select__menu``
          subtree, which has zero overlap with the phantom set.

        The JS template is :data:`_FILL_COMBOBOX_JS_TEMPLATE`; see its
        block comment for the full event-sequence rationale.
    Args:
        field_id: DOM id of the React-Select input element (e.g.
            ``"question_66747918"``, ``"gender"``). Must NOT be an
            agent-browser snapshot ref.
        target_option: Visible label of the option to pick. Curly
            U+2018 / U+2019 apostrophes are normalized to ASCII on
            both sides of the comparison, so either spelling works.
        exact: When True, the matched option's text must equal
            ``target_option`` exactly after normalization. Use when one
            option is a prefix of another (``"Yes"`` vs ``"Yes, …"``).
    Returns:
        The verified ``.select__single-value`` label on success, the
        literal ``"EMPTY"`` when the verify step found no committed
        value, or ``"ERROR: <step>: <message>"`` when a sub-step
        failed (``<step>`` ∈ ``lookup, open_menu, find_option, verify,
        launch, parse, eval``).

        When ``<step>`` is ``find_option``, the error message includes
        the list of options the menu actually showed so the model can
        retry with a correct target label.
    Raises:
        ModelRetry: When ``field_id`` is invalid or ``target_option``
            is empty.
    """

    validated_id = _validate_field_id(field_id)
    cleaned_target = (target_option or "").strip()
    if not cleaned_target:
        raise ModelRetry("target_option must be non-empty.")

    js = _FILL_COMBOBOX_JS_TEMPLATE.format(
        field_id=validated_id,
        target_json=json.dumps(cleaned_target),
        exact_json="true" if exact else "false",
    )
    result = await invoke_agent_browser_cli(
        ["eval", "--stdin"],
        stdin_payload=js,
        timeout_seconds=_FILL_COMBOBOX_TIMEOUT_SECONDS,
    )
    return _summarize_fill_combobox_result(result)


def _summarize_fill_combobox_result(result: dict[str, Any]) -> str:
    """Reduce a ``fill_combobox`` eval result to the model-facing string.

    Purpose:
        ``fill_combobox`` returns one string so the model's next-turn
        input stays small and the contract matches
        ``verify_combobox_filled``. This helper does the reduction
        from the eval's JSON envelope.
    Args:
        result: Output of :func:`invoke_agent_browser_cli` for the
            ``eval --stdin`` invocation. ``stdout`` is the JSON the JS
            ``return JSON.stringify({...})`` produced.
    Returns:
        Verified label, ``"EMPTY"``, or ``"ERROR: <step>: <msg>"``.
    """

    if not result.get("ok") and result.get("exit_code") == -2:
        return "ERROR: launch: agent-browser binary missing"

    raw_stdout = (result.get("stdout") or "").strip()
    if not raw_stdout:
        stderr_line = (result.get("stderr") or "").strip().splitlines()[:1]
        msg = stderr_line[0] if stderr_line else "no output from eval"
        return f"ERROR: eval: {msg}"

    # agent-browser's `eval` wraps the JS return value as a JSON string.
    # Our JS returns JSON.stringify({...}), so stdout is double-encoded.
    # First decode unwraps the outer envelope (string or object), then
    # the second decode parses the inner JSON payload.
    payload = raw_stdout
    try:
        first = json.loads(raw_stdout)
        if isinstance(first, str):
            payload = first
        elif isinstance(first, dict):
            inner = first.get("value")
            if isinstance(inner, str):
                payload = inner
            else:
                # Already-parsed dict — use it directly without the
                # second decode below.
                return _interpret_pick_result(first)
    except json.JSONDecodeError:
        pass  # Fall through; second decode will surface the error.

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        return f"ERROR: parse: eval JSON unparseable ({exc})"
    if not isinstance(parsed, dict):
        return "ERROR: parse: eval payload was not an object"
    return _interpret_pick_result(parsed)


def _interpret_pick_result(parsed: dict[str, Any]) -> str:
    """Convert the JS-side ``{ok, step, error?, picked?, options?}`` dict.

    Returned shapes from :data:`_FILL_COMBOBOX_JS_TEMPLATE`:

    - ``{"ok": true, "picked": "<label>"}`` → return ``"<label>"``.
    - ``{"ok": false, "step": "find_option", "error": "...", "options": [...]}``
      → return ``"ERROR: find_option: <error>; menu showed: [...]"`` so the
      model can read the actual labels and retry.
    - ``{"ok": false, "step": "<step>", "error": "..."}`` → return
      ``"ERROR: <step>: <error>"``.
    """

    if parsed.get("ok") is True:
        picked = parsed.get("picked")
        if isinstance(picked, str) and picked.strip():
            return picked.strip()
        return "EMPTY"
    step = parsed.get("step") or "unknown"
    err = parsed.get("error") or "unknown error"
    if step == "find_option" and isinstance(parsed.get("options"), list):
        opts = parsed["options"][:12]
        opts_str = ", ".join(repr(o) for o in opts)
        return f"ERROR: find_option: {err}; menu showed: [{opts_str}]"
    return f"ERROR: {step}: {err}"


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
    fill_combobox,
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
    "fill_combobox",
    "flag_for_verify",
    "lookup_cached_answer",
    "pick_option",
    "verify_combobox_filled",
]
