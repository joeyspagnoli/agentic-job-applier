"""Tests for the narrow per-step apply-finisher tools.

Locks in the wiring between each helper and the underlying
``invoke_agent_browser_cli`` call so a future refactor can't silently
change the selector / JS literal the model is relying on.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai import ModelRetry

from src.agents.apply_finisher import tools as tools_module
from src.agents.apply_finisher.tools import (
    dispatch_async_typeahead_query,
    open_combobox,
    pick_option,
    type_combobox_filter,
    verify_combobox_filled,
)


def _stub_invoke(
    monkeypatch: pytest.MonkeyPatch,
    captured: dict[str, Any],
    *,
    stdout: str = "",
    ok: bool = True,
    stderr: str = "",
) -> None:
    """Replace ``invoke_agent_browser_cli`` with an argv-capturing stub.

    Args:
        monkeypatch: Pytest fixture.
        captured: Dict that will be populated with the call's argv.
        stdout: Stdout the stub returns to the caller.
        ok: Whether the stub reports success.
        stderr: Stderr the stub returns.
    """

    async def fake_invoke(
        args: list[str],
        *,
        expect_json: bool = False,
        timeout_seconds: float = 20.0,
    ) -> dict[str, Any]:
        """Record argv and return a canned payload."""

        _ = (expect_json, timeout_seconds)
        captured["args"] = list(args)
        return {
            "ok": ok,
            "command": "agent-browser " + " ".join(args),
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": 0 if ok else 1,
        }

    monkeypatch.setattr(tools_module, "invoke_agent_browser_cli", fake_invoke)


# ---------------------------------------------------------------------------
# open_combobox
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_open_combobox_uses_aria_labelledby_css_selector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``open_combobox`` runs ``click '[aria-labelledby="<id>-label"]'``."""

    captured: dict[str, Any] = {}
    _stub_invoke(monkeypatch, captured)

    result = await open_combobox("question_66747918")

    assert result["ok"] is True
    assert captured["args"] == [
        "click",
        "[aria-labelledby=\"question_66747918-label\"]",
    ]


@pytest.mark.asyncio
async def test_open_combobox_rejects_id_with_illegal_chars() -> None:
    """A field_id containing quotes / brackets fails closed via ModelRetry."""

    with pytest.raises(ModelRetry):
        await open_combobox("question'66747918")


@pytest.mark.asyncio
async def test_open_combobox_rejects_empty_id() -> None:
    """An empty field_id fails closed via ModelRetry."""

    with pytest.raises(ModelRetry):
        await open_combobox("")


# ---------------------------------------------------------------------------
# type_combobox_filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_type_combobox_filter_uses_keyboard_inserttext(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The filter helper runs ``keyboard inserttext <text>``."""

    captured: dict[str, Any] = {}
    _stub_invoke(monkeypatch, captured)

    await type_combobox_filter("I am willing")

    assert captured["args"] == ["keyboard", "inserttext", "I am willing"]


@pytest.mark.asyncio
async def test_type_combobox_filter_rejects_empty_text() -> None:
    """Empty filter text fails closed."""

    with pytest.raises(ModelRetry):
        await type_combobox_filter("   ")


@pytest.mark.asyncio
async def test_type_combobox_filter_rejects_overlong_text() -> None:
    """Filter text above the 60-char cap is rejected to catch prose mistakes."""

    with pytest.raises(ModelRetry):
        await type_combobox_filter("x" * 200)


# ---------------------------------------------------------------------------
# pick_option
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
