"""Tests for the narrow per-step apply-finisher tools.

Locks in the wiring between each helper and the underlying
``invoke_agent_browser_cli`` call so a future refactor can't silently
change the selector / JS literal the model is relying on.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic_ai import ModelRetry

from src.agents.apply_finisher import tools as tools_module
from src.agents.apply_finisher.tools import (
    dispatch_async_typeahead_query,
    fill_combobox,
    pick_option,
    verify_combobox_filled,
)


def _stub_invoke(
    monkeypatch: pytest.MonkeyPatch,
    captured: dict[str, Any],
    *,
    stdout: str = "",
    ok: bool = True,
    stderr: str = "",
    exit_code: int | None = None,
) -> None:
    """Replace ``invoke_agent_browser_cli`` with an argv-capturing stub.

    Args:
        monkeypatch: Pytest fixture.
        captured: Dict that will be populated with the call's argv and
            optional stdin payload.
        stdout: Stdout the stub returns to the caller.
        ok: Whether the stub reports success.
        stderr: Stderr the stub returns.
        exit_code: Override exit code (defaults to 0 when ok else 1).
    """

    async def fake_invoke(
        args: list[str],
        *,
        expect_json: bool = False,
        timeout_seconds: float = 20.0,
        stdin_payload: str | None = None,
    ) -> dict[str, Any]:
        """Record argv (and optional stdin payload) and return a canned payload."""

        _ = (expect_json, timeout_seconds)
        captured["args"] = list(args)
        captured["stdin_payload"] = stdin_payload
        return {
            "ok": ok,
            "command": "agent-browser " + " ".join(args),
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code if exit_code is not None else (0 if ok else 1),
        }

    monkeypatch.setattr(tools_module, "invoke_agent_browser_cli", fake_invoke)


# ---------------------------------------------------------------------------
# pick_option (used only inside the async-typeahead flow)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pick_option_emits_find_role_option_argv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``pick_option`` runs ``find role option click --name <text>``."""

    captured: dict[str, Any] = {}
    _stub_invoke(monkeypatch, captured)

    await pick_option("Bachelor's")

    assert captured["args"] == [
        "find",
        "role",
        "option",
        "click",
        "--name",
        "Bachelor's",
    ]


@pytest.mark.asyncio
async def test_pick_option_appends_exact_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``exact=True`` adds ``--exact`` to disambiguate prefix collisions."""

    captured: dict[str, Any] = {}
    _stub_invoke(monkeypatch, captured)

    await pick_option("Yes", exact=True)

    assert captured["args"][-1] == "--exact"
    assert captured["args"][-3:-1] == ["--name", "Yes"]


# ---------------------------------------------------------------------------
# verify_combobox_filled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_returns_picked_label_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On ok=True the stripped stdout becomes the picked label."""

    captured: dict[str, Any] = {}
    _stub_invoke(monkeypatch, captured, stdout="Bachelor's\n")

    result = await verify_combobox_filled("question_66747923")

    assert result == "Bachelor's"
    # The JS interpolates the validated field id into the selector.
    assert captured["args"][0] == "eval"
    assert "question_66747923" in captured["args"][1]
    assert "single-value" in captured["args"][1]


@pytest.mark.asyncio
async def test_verify_returns_empty_sentinel_when_stdout_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Blank stdout on ok=True is normalized to the EMPTY sentinel."""

    captured: dict[str, Any] = {}
    _stub_invoke(monkeypatch, captured, stdout="   \n")

    result = await verify_combobox_filled("country")
    assert result == "EMPTY"


@pytest.mark.asyncio
async def test_verify_returns_error_prefix_on_cli_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A nonzero exit yields ``ERROR: <first stderr line>``."""

    captured: dict[str, Any] = {}
    _stub_invoke(
        monkeypatch,
        captured,
        ok=False,
        stderr="ReferenceError: el is null\n  at <anonymous>",
    )

    result = await verify_combobox_filled("question_66747918")
    assert result.startswith("ERROR:")
    assert "ReferenceError" in result


# ---------------------------------------------------------------------------
# dispatch_async_typeahead_query
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_dispatch_emits_eval_with_native_setter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The dispatch helper runs the native-setter + input-event eval."""

    captured: dict[str, Any] = {}
    _stub_invoke(monkeypatch, captured, stdout="dispatched")

    await dispatch_async_typeahead_query("candidate-location", "Gainesville")

    assert captured["args"][0] == "eval"
    js = captured["args"][1]
    assert "candidate-location" in js
    assert "Gainesville" in js
    assert "HTMLInputElement.prototype" in js
    assert "dispatchEvent(new Event('input'" in js


@pytest.mark.asyncio
async def test_async_dispatch_rejects_query_with_single_quote() -> None:
    """A single quote in the query would break the JS literal — reject."""

    with pytest.raises(ModelRetry):
        await dispatch_async_typeahead_query("candidate-location", "O'Brien")


@pytest.mark.asyncio
async def test_async_dispatch_rejects_bad_field_id() -> None:
    """Field id outside [A-Za-z0-9_-] is rejected."""

    with pytest.raises(ModelRetry):
        await dispatch_async_typeahead_query("bad id!", "Gainesville")


# ---------------------------------------------------------------------------
# fill_combobox (single-eval React-Select pick + verify)
# ---------------------------------------------------------------------------


def _eval_success_stdout(picked: str) -> str:
    """Return the stdout the eval would produce on a successful pick."""

    return json.dumps({"ok": True, "picked": picked})


@pytest.mark.asyncio
async def test_fill_combobox_runs_one_eval_via_stdin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The helper calls ``eval --stdin`` once with the field-bound JS payload."""

    captured: dict[str, Any] = {}
    _stub_invoke(
        monkeypatch,
        captured,
        stdout=_eval_success_stdout("United States +1"),
    )

    result = await fill_combobox("country", "United States +1", exact=True)

    assert result == "United States +1"
    assert captured["args"] == ["eval", "--stdin"]
    js = captured["stdin_payload"] or ""
    # Field id baked into the JS via the validated string literal.
    assert "const FIELD_ID = 'country';" in js
    # Target is passed via JSON.stringify on the Python side.
    assert '"United States +1"' in js
    # exact=True surfaces in the JS as the literal `true`.
    assert "const EXACT = true;" in js


@pytest.mark.asyncio
async def test_fill_combobox_passes_exact_false_when_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``exact=False`` (default) flows through to the JS as ``false``."""

    captured: dict[str, Any] = {}
    _stub_invoke(monkeypatch, captured, stdout=_eval_success_stdout("Bachelor's"))

    await fill_combobox("question_66747923", "Bachelor's")

    js = captured["stdin_payload"] or ""
    assert "const EXACT = false;" in js


@pytest.mark.asyncio
async def test_fill_combobox_emits_pointer_and_mouse_event_sequence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The eval JS dispatches the full event chain React-Select listens for.

    Locks in the load-bearing PointerEvent + MouseEvent sequence — a
    bare ``click`` event does NOT commit React-Select v4 picks. This
    test catches any refactor that quietly drops a member of the chain.
    """

    captured: dict[str, Any] = {}
    _stub_invoke(monkeypatch, captured, stdout=_eval_success_stdout("Yes"))

    await fill_combobox("question_66747925", "Yes", exact=True)

    js = captured["stdin_payload"] or ""
    for event_ctor in (
        "new PointerEvent('pointerdown'",
        "new MouseEvent('mousedown'",
        "new PointerEvent('pointerup'",
        "new MouseEvent('mouseup'",
        "new MouseEvent('click'",
    ):
        assert event_ctor in js, f"missing event constructor {event_ctor!r}"


@pytest.mark.asyncio
async def test_fill_combobox_scopes_option_lookup_to_field_shell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Option search must scope to the field's own ``.select-shell`` menu.

    Sidesteps the intl-tel-input 244-country phantom collision; if a
    refactor reverts to ``document.querySelectorAll('[role=option]')``
    the agent will silently pick wrong countries instead of the
    intended option.
    """

    captured: dict[str, Any] = {}
    _stub_invoke(monkeypatch, captured, stdout=_eval_success_stdout("Yes"))

    await fill_combobox("question_66747921", "Yes")

    js = captured["stdin_payload"] or ""
    assert "input.closest('.select-shell')" in js
    assert 'shell.querySelector(\'[class*="select__menu"]\')' in js
    assert "menu.querySelectorAll(" in js


@pytest.mark.asyncio
async def test_fill_combobox_returns_empty_when_verify_value_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An ok-but-blank picked value surfaces as the literal ``EMPTY``."""

    captured: dict[str, Any] = {}
    _stub_invoke(
        monkeypatch,
        captured,
        stdout=json.dumps({"ok": True, "picked": "   "}),
    )

    result = await fill_combobox("country", "United States +1")
    assert result == "EMPTY"


@pytest.mark.asyncio
async def test_fill_combobox_surfaces_named_step_on_find_option_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A find_option failure includes the menu's actual options for retry."""

    captured: dict[str, Any] = {}
    _stub_invoke(
        monkeypatch,
        captured,
        stdout=json.dumps(
            {
                "ok": False,
                "step": "find_option",
                "error": "no option matched target",
                "options": ["Yes", "No"],
            }
        ),
    )

    result = await fill_combobox("question_66747918", "Yes please")

    assert result.startswith("ERROR: find_option: ")
    assert "no option matched target" in result
    assert "'Yes'" in result
    assert "'No'" in result


@pytest.mark.asyncio
async def test_fill_combobox_surfaces_open_menu_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An open_menu failure passes through as ``ERROR: open_menu: <msg>``."""

    captured: dict[str, Any] = {}
    _stub_invoke(
        monkeypatch,
        captured,
        stdout=json.dumps(
            {
                "ok": False,
                "step": "open_menu",
                "error": "menu did not mount after click",
            }
        ),
    )

    result = await fill_combobox("question_66747918", "Yes")
    assert result == "ERROR: open_menu: menu did not mount after click"


@pytest.mark.asyncio
async def test_fill_combobox_rejects_empty_target() -> None:
    """Without a target option label the helper has nothing to click."""

    with pytest.raises(ModelRetry):
        await fill_combobox("country", "")


@pytest.mark.asyncio
async def test_fill_combobox_rejects_snapshot_ref_field_id() -> None:
    """``@eN`` / ``eN`` refs aren't DOM ids — reject like the other helpers."""

    with pytest.raises(ModelRetry):
        await fill_combobox("e42", "United States +1")


@pytest.mark.asyncio
async def test_fill_combobox_rejects_invalid_field_id() -> None:
    """A field_id with illegal chars fails closed via ModelRetry."""

    with pytest.raises(ModelRetry):
        await fill_combobox("bad id!", "United States +1")
