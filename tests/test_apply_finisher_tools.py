"""Behavioral tests for the BYO Playwright tools in ``apply_finisher.tools``.

Complements the existing ``test_apply_finisher_smoke.py`` by covering the
ModelRetry branches, the screenshot fallback path on an empty AX tree, the
React-Select listbox fallback in ``select``, and the MutationObserver wait
helper.

Tests build a :class:`tests.helpers.fake_finisher_page.FakeFinisherPage`
configured for the scenario, wrap it in a ``FinisherDeps``, and drive the
tool directly. No live Playwright runtime is required.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Coroutine

import pytest
from pydantic_ai import BinaryContent, ModelRetry, ToolReturn

from src.agents.apply_finisher.answer_cache import AnswerCache
from src.agents.apply_finisher.defer_rules import DeferRules
from src.agents.apply_finisher.schemas import FinisherDeps
from src.agents.apply_finisher.tools import (
    click,
    defer,
    fill,
    flag_for_verify,
    get_snapshot,
    lookup_cached_answer,
    select,
    wait_for_dom_quiet,
)
from tests.helpers.fake_finisher_page import (
    FakeFinisherPage,
    FakeLocatorState,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _Ctx:
    """RunContext stub that carries ``FinisherDeps`` for the tools."""

    def __init__(self, deps: FinisherDeps) -> None:
        """Bind the deps object the tools will read."""

        self.deps = deps


def _build_deps(
    page: FakeFinisherPage,
    *,
    cache_path: Path | None = None,
    form_root: str = "#application_form",
) -> FinisherDeps:
    """Build a FinisherDeps wired to the supplied fake page.

    Args:
        page: The fake page the tools will drive.
        cache_path: Optional path for the (unused) answer cache backing file.
        form_root: Selector returned for ``form_root_selector``.
    Returns:
        Configured :class:`FinisherDeps`.
    """

    cache = AnswerCache(_path=cache_path or Path("/tmp/_test_cache.yaml"))
    rules = DeferRules(
        _always_defer_patterns=(),
        _draft_and_flag_patterns=(),
        bypass_field_types=frozenset(),
        never_defer_overrides=(),
    )
    return FinisherDeps(
        page=page,  # type: ignore[arg-type]
        ats="greenhouse",
        target_company="Stripe",
        defer_rules=rules,
        cache=cache,
        profile_yaml="profile: {}\n",
        form_root_selector=form_root,
    )


def _run(coro: Coroutine[Any, Any, Any]) -> Any:
    """Execute ``coro`` on a fresh event loop and return its result."""

    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# get_snapshot
# ---------------------------------------------------------------------------


def test_get_snapshot_returns_text_when_tree_non_empty() -> None:
    """A non-empty aria_snapshot lands on the ``return_value`` path."""

    page = FakeFinisherPage(snapshot_text="- combobox 'Country' [ref=e3]")
    deps = _build_deps(page)

    result = _run(get_snapshot(_Ctx(deps)))  # type: ignore[arg-type]

    assert isinstance(result, ToolReturn)
    assert "Country" in str(result.return_value)
    assert result.content is None or result.content == []


def test_get_snapshot_falls_back_to_screenshot_with_binary_content() -> None:
    """Empty AX tree triggers a screenshot returned as BinaryContent."""

    page = FakeFinisherPage(snapshot_text="", screenshot_bytes=b"\x89PNGmock")
    deps = _build_deps(page)

    result = _run(get_snapshot(_Ctx(deps)))  # type: ignore[arg-type]

    assert isinstance(result, ToolReturn)
    assert "screenshot" in str(result.return_value).lower()
    assert result.content is not None
    binary_payloads = [c for c in result.content if isinstance(c, BinaryContent)]
    assert len(binary_payloads) == 1
    assert binary_payloads[0].media_type == "image/png"
    assert binary_payloads[0].data == b"\x89PNGmock"


def test_get_snapshot_screenshot_failure_returns_textual_advice() -> None:
    """When screenshot raises after empty tree, the tool returns advice text."""

    page = FakeFinisherPage(snapshot_text="", screenshot_raises=RuntimeError)
    deps = _build_deps(page)

    result = _run(get_snapshot(_Ctx(deps)))  # type: ignore[arg-type]

    assert isinstance(result, ToolReturn)
    assert "AGENT_GAVE_UP" in str(result.return_value)


def test_get_snapshot_falls_back_to_body_when_form_root_raises() -> None:
    """A ``aria_snapshot`` exception falls through to the ``body`` selector."""

    call_counter = {"n": 0}

    class _RaisingFirstAxLocator:
        """Locator that raises the first time and returns snapshot the second."""

        async def aria_snapshot(self, *, mode: str = "ai") -> str:
            call_counter["n"] += 1
            if call_counter["n"] == 1:
                raise RuntimeError("form root not yet mounted")
            _ = mode
            return "- form 'body fallback' [ref=e1]"

    page = FakeFinisherPage(snapshot_text="ignored")

    def _custom_locator(selector: str) -> _RaisingFirstAxLocator:
        _ = selector
        return _RaisingFirstAxLocator()

    page.locator = _custom_locator  # type: ignore[assignment]
    deps = _build_deps(page)

    result = _run(get_snapshot(_Ctx(deps)))  # type: ignore[arg-type]

    assert isinstance(result, ToolReturn)
    assert "body fallback" in str(result.return_value)


# ---------------------------------------------------------------------------
# click — unresolvable + forbidden + locator error paths
# ---------------------------------------------------------------------------


def test_click_raises_model_retry_when_ref_not_found() -> None:
    """``click`` raises ModelRetry when the ref resolves to zero elements."""

    page = FakeFinisherPage(default_state=FakeLocatorState(count=0))
    deps = _build_deps(page)

    with pytest.raises(ModelRetry, match="not found"):
        _run(click(_Ctx(deps), ref="e9"))  # type: ignore[arg-type]


def test_click_raises_model_retry_on_invalid_ref_format() -> None:
    """``click`` raises ModelRetry when ref is neither ``eN`` nor digits."""

    page = FakeFinisherPage()
    deps = _build_deps(page)

    with pytest.raises(ModelRetry, match="not a valid aria-ref"):
        _run(click(_Ctx(deps), ref="abc"))  # type: ignore[arg-type]


def test_click_propagates_locator_failure_as_model_retry() -> None:
    """A click that raises bubbles up as ModelRetry with a helpful message."""

    state = FakeLocatorState(count=1, click_raises=RuntimeError)
    page = FakeFinisherPage(ref_states={"e5": state})
    deps = _build_deps(page)

    with pytest.raises(ModelRetry, match="Click on ref"):
        _run(click(_Ctx(deps), ref="e5"))  # type: ignore[arg-type]


def test_click_refuses_submit_with_apply_prefix() -> None:
    """An accessible name starting with ``apply`` is refused like submit."""

    state = FakeLocatorState(count=1, accessible_name="Apply now")
    page = FakeFinisherPage(ref_states={"e2": state})
    deps = _build_deps(page)

    with pytest.raises(ModelRetry, match="reserved for the worker"):
        _run(click(_Ctx(deps), ref="e2"))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# fill
# ---------------------------------------------------------------------------


def test_fill_raises_model_retry_when_ref_missing() -> None:
    """``fill`` reuses the same not-found message as click."""

    page = FakeFinisherPage(default_state=FakeLocatorState(count=0))
    deps = _build_deps(page)

    with pytest.raises(ModelRetry, match="not found"):
        _run(fill(_Ctx(deps), ref="e3", value="x"))  # type: ignore[arg-type]


def test_fill_propagates_underlying_fill_failure() -> None:
    """A fill that raises bubbles up as ModelRetry."""

    state = FakeLocatorState(count=1, fill_raises=RuntimeError)
    page = FakeFinisherPage(ref_states={"e7": state})
    deps = _build_deps(page)

    with pytest.raises(ModelRetry, match="not be editable"):
        _run(fill(_Ctx(deps), ref="e7", value="y"))  # type: ignore[arg-type]


def test_fill_long_value_is_truncated_in_confirmation_message() -> None:
    """The success confirmation truncates long values to keep logs readable."""

    state = FakeLocatorState(count=1)
    page = FakeFinisherPage(ref_states={"e4": state})
    deps = _build_deps(page)

    value = "z" * 200
    result = _run(fill(_Ctx(deps), ref="e4", value=value))  # type: ignore[arg-type]

    assert isinstance(result, str)
    assert "..." in result
    assert len(result) < 200


# ---------------------------------------------------------------------------
# select — listbox fallback path
# ---------------------------------------------------------------------------


def test_select_native_path_records_label() -> None:
    """The native ``select_option`` path lands a select_log entry."""

    state = FakeLocatorState(count=1)
    page = FakeFinisherPage(ref_states={"e8": state})
    deps = _build_deps(page)

    result = _run(select(_Ctx(deps), ref="e8", value="United States"))  # type: ignore[arg-type]

    assert "selected 'United States'" in str(result)
    assert page.select_log == [("e8", "United States")]
    assert deps.fields_filled_count == 1


def test_select_listbox_fallback_enumerates_options_on_invalid_choice() -> None:
    """When native fails and the value is not in the listbox, ModelRetry lists options."""

    state = FakeLocatorState(count=1, select_option_raises=RuntimeError)
    page = FakeFinisherPage(
        ref_states={"e10": state},
        listbox_options=["Yes", "No", "Prefer not to say"],
    )
    deps = _build_deps(page)

    with pytest.raises(ModelRetry, match="Valid options"):
        _run(select(_Ctx(deps), ref="e10", value="Maybe"))  # type: ignore[arg-type]


def test_select_listbox_fallback_clicks_matching_option() -> None:
    """When native fails but the listbox has the value, the click succeeds."""

    state = FakeLocatorState(count=1, select_option_raises=RuntimeError)
    page = FakeFinisherPage(
        ref_states={"e11": state},
        listbox_options=["Yes", "No"],
    )
    deps = _build_deps(page)

    result = _run(select(_Ctx(deps), ref="e11", value="Yes"))  # type: ignore[arg-type]

    assert "via listbox option" in str(result)
    assert deps.fields_filled_count == 1


# ---------------------------------------------------------------------------
# wait_for_dom_quiet
# ---------------------------------------------------------------------------


def test_wait_for_dom_quiet_uses_evaluate_result() -> None:
    """The tool reports the evaluate-script outcome verbatim."""

    page = FakeFinisherPage(evaluate_results={"MutationObserver": "quiet"})
    deps = _build_deps(page)

    result = _run(wait_for_dom_quiet(_Ctx(deps), ms=120))  # type: ignore[arg-type]

    assert "dom_quiet=quiet" in str(result)
    assert "120ms" in str(result)


def test_wait_for_dom_quiet_clamps_minimum_window() -> None:
    """A sub-50ms request is clamped up to 50ms."""

    page = FakeFinisherPage(evaluate_results={"MutationObserver": "quiet"})
    deps = _build_deps(page)

    result = _run(wait_for_dom_quiet(_Ctx(deps), ms=10))  # type: ignore[arg-type]

    assert "50ms" in str(result)


def test_wait_for_dom_quiet_falls_back_to_sleep_when_evaluate_raises() -> None:
    """If ``evaluate`` raises the tool drops back to ``asyncio.sleep``."""

    class _RaisingPage(FakeFinisherPage):
        async def evaluate(self, script: str, arg: object | None = None) -> object:
            _ = (script, arg)
            raise RuntimeError("evaluate disabled in this fixture")

    page = _RaisingPage()
    deps = _build_deps(page)

    result = _run(wait_for_dom_quiet(_Ctx(deps), ms=60))  # type: ignore[arg-type]

    assert "sleep_fallback" in str(result)


# ---------------------------------------------------------------------------
# defer & flag_for_verify
# ---------------------------------------------------------------------------


def test_defer_does_not_touch_page() -> None:
    """``defer`` is a pure record — no click / fill should land."""

    page = FakeFinisherPage()
    deps = _build_deps(page)

    _run(
        defer(
            _Ctx(deps),  # type: ignore[arg-type]
            ref="e6",
            label="Will you require sponsorship?",
            field_type="select",
            category="sponsorship",
            reason="Tier-3 by policy.",
        )
    )

    assert page.click_log == []
    assert page.fill_log == []
    assert deps.recorded_deferrals[0].field_id == "e6"
    assert deps.recorded_deferrals[0].category == "sponsorship"


def test_flag_for_verify_records_with_confidence() -> None:
    """A valid confidence draft lands in the deps list."""

    page = FakeFinisherPage()
    deps = _build_deps(page)

    _run(
        flag_for_verify(
            _Ctx(deps),  # type: ignore[arg-type]
            ref="e12",
            label="Why this role?",
            drafted_value="Because mission.",
            confidence=0.42,
            reasoning="Drafted from JD.",
        )
    )

    assert deps.drafted_fields[0].confidence == pytest.approx(0.42)
    assert deps.drafted_fields[0].field_id == "e12"


@pytest.mark.parametrize("bad_confidence", [-0.1, 1.1, 2.0])
def test_flag_for_verify_rejects_out_of_range_confidence(bad_confidence: float) -> None:
    """Confidence values outside [0.0, 1.0] raise ModelRetry."""

    page = FakeFinisherPage()
    deps = _build_deps(page)

    with pytest.raises(ModelRetry, match=r"\[0.0, 1.0\]"):
        _run(
            flag_for_verify(
                _Ctx(deps),  # type: ignore[arg-type]
                ref="e1",
                label="Why?",
                drafted_value="...",
                confidence=bad_confidence,
                reasoning="bad",
            )
        )


# ---------------------------------------------------------------------------
# lookup_cached_answer (uses real AnswerCache backed by a tmp YAML)
# ---------------------------------------------------------------------------


def test_lookup_cached_answer_returns_hit_when_normalized_match(tmp_path: Path) -> None:
    """An exact normalized match returns the cached answer."""

    import yaml

    cache_file = tmp_path / "answer_cache.yaml"
    cache_file.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "entries": [
                    {
                        "question_text": "why do you want to work here",
                        "question_normalized": "why do you want to work here",
                        "answer": "I love $COMPANY.",
                        "category": "motivation",
                        "company_specific": False,
                        "company": None,
                    }
                ],
            },
        ),
        encoding="utf-8",
    )
    from src.agents.apply_finisher.answer_cache import load_answer_cache

    cache = load_answer_cache(cache_file)
    rules = DeferRules(
        _always_defer_patterns=(),
        _draft_and_flag_patterns=(),
        bypass_field_types=frozenset(),
        never_defer_overrides=(),
    )
    deps = FinisherDeps(
        page=FakeFinisherPage(),  # type: ignore[arg-type]
        ats="greenhouse",
        target_company="Stripe",
        defer_rules=rules,
        cache=cache,
        profile_yaml="profile: {}\n",
        form_root_selector="#application_form",
    )

    result = _run(
        lookup_cached_answer(_Ctx(deps), question_text="Why do you want to work here?")  # type: ignore[arg-type]
    )

    assert "cache_hit" in str(result)
    assert "I love Stripe." in str(result)
