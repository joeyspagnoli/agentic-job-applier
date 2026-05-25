"""Playwright-shaped doubles for the apply-finisher tool surface.

These helpers replace ``playwright.async_api.Page`` / ``Locator`` for tests
that exercise the BYO tools in :mod:`src.agents.apply_finisher.tools` and the
gate-aware browser flow in :mod:`src.agents.apply_worker.browser`. They cover
only the async API surface the tools and helpers actually use; tests build
deterministic state through the constructor and assert behavior by reading
the recorded log lists after the tool call.

Why these live in a shared helper:
    The orchestrator's smoke fixture in ``test_apply_finisher_smoke.py`` is
    intentionally narrow — one selector returns one locator. The behavior-
    driven test pass needs branchy locator behavior (counts of zero, select
    options, raising click, etc.) so the helper here is the broader
    contract.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable


_REF_RE = re.compile(r"aria-ref=(?P<ref>e?\d+)")


def _ref_from_selector(selector: str) -> str | None:
    """Pull the ``eN`` token out of an ``aria-ref=eN`` selector string.

    Purpose:
        Tools always build locators via ``page.locator(f"aria-ref={normalized}")``.
        Tests can plug into the lookup by indexing on the canonical token.
    Args:
        selector: Selector passed to :meth:`FakeFinisherPage.locator`.
    Returns:
        The ``eN`` ref or ``None`` for non-aria selectors.
    """

    match = _REF_RE.search(selector)
    if match is None:
        return None
    ref = match.group("ref")
    return ref if ref.startswith("e") else f"e{ref}"


@dataclass
class FakeLocatorState:
    """Configurable behavior for one ref or selector.

    Attributes:
        count: Value returned by ``count()``.
        accessible_name: Returned by ``get_attribute('aria-label')``.
        text_content_value: Returned by ``text_content()``.
        click_raises: Exception class to raise on ``click()``; ``None`` to succeed.
        fill_raises: Exception class to raise on ``fill()``; ``None`` to succeed.
        select_option_raises: Exception class to raise on ``select_option``;
            ``None`` to succeed. Tests use this to force the listbox fallback.
        select_value: Value the test expects to see passed to ``select_option``.
        input_value: Value returned by ``input_value()``.
    """

    count: int = 1
    accessible_name: str = ""
    text_content_value: str = ""
    click_raises: type[BaseException] | None = None
    fill_raises: type[BaseException] | None = None
    select_option_raises: type[BaseException] | None = None
    input_value: str = ""


class FakeLocator:
    """Async Playwright-like locator backed by a :class:`FakeLocatorState`.

    Recording: each fake locator captures click/fill/select calls into the
    parent page's logs so tests can assert behavior without inspecting the
    fake's private state.
    """

    def __init__(self, state: FakeLocatorState, page: "FakeFinisherPage", ref: str | None) -> None:
        """Bind one locator to its state and the page that produced it.

        Args:
            state: Configured behavior for this ref.
            page: Owning :class:`FakeFinisherPage` for log capture.
            ref: ``eN`` token this locator resolves, when applicable.
        """

        self._state = state
        self._page = page
        self._ref = ref

    @property
    def first(self) -> "FakeLocator":
        """Return self to match Playwright's locator chaining contract."""

        return self

    async def count(self) -> int:
        """Return the configured count."""

        return self._state.count

    async def get_attribute(self, name: str) -> str | None:
        """Return the configured aria-label when requested.

        Args:
            name: Attribute name. Only ``aria-label`` is recognised; other
                names return ``None`` to mirror Playwright when an attribute
                is missing.
        Returns:
            The configured accessible name or ``None``.
        """

        if name == "aria-label":
            return self._state.accessible_name or None
        return None

    async def text_content(self) -> str | None:
        """Return the configured text content."""

        return self._state.text_content_value or None

    async def click(self) -> None:
        """Record the click; raise when ``click_raises`` is configured."""

        if self._state.click_raises is not None:
            raise self._state.click_raises("forced click failure")
        self._page.click_log.append(self._ref or "")

    async def fill(self, value: str) -> None:
        """Record the fill value; raise when ``fill_raises`` is configured."""

        if self._state.fill_raises is not None:
            raise self._state.fill_raises("forced fill failure")
        self._page.fill_log.append((self._ref or "", value))

    async def select_option(self, *, label: str) -> None:
        """Record the option; raise when ``select_option_raises`` is set."""

        if self._state.select_option_raises is not None:
            raise self._state.select_option_raises("forced select failure")
        self._page.select_log.append((self._ref or "", label))

    async def input_value(self, *, timeout: float = 0) -> str:
        """Return the configured input_value (timeout is accepted, ignored)."""

        _ = timeout
        return self._state.input_value

    async def aria_snapshot(self, *, mode: str = "ai") -> str:
        """Return the page's configured AX-tree snapshot text.

        Args:
            mode: Snapshot mode hint; recorded but ignored.
        Returns:
            The configured snapshot string.
        """

        self._page.snapshot_mode = mode
        return self._page.snapshot_text

    def nth(self, index: int) -> "FakeLocator":
        """Return self for any index — matches Playwright's sync API."""

        _ = index
        return self


class FakeOptionLocator:
    """Locator returned by ``page.get_by_role('option')`` for select fallback.

    Attributes:
        options: Visible option labels the agent should see.
    """

    def __init__(self, options: list[str]) -> None:
        """Capture the visible option list.

        Args:
            options: Visible labels in DOM order.
        """

        self._options = options
        self._filter_value: str | None = None

    async def count(self) -> int:
        """Return the option list length."""

        return len(self._options)

    def nth(self, index: int) -> "FakeOptionLocator":
        """Return a per-index locator that exposes its text content."""

        if 0 <= index < len(self._options):
            return FakeOptionLocator([self._options[index]])
        return FakeOptionLocator([])

    async def text_content(self) -> str:
        """Return the only option text when this locator is for one option."""

        if len(self._options) == 1:
            return self._options[0]
        return ""

    def filter(self, *, has_text: str) -> "FakeOptionLocator":
        """Filter to options containing ``has_text``."""

        filtered = [opt for opt in self._options if has_text in opt]
        return FakeOptionLocator(filtered)

    @property
    def first(self) -> "FakeOptionLocator":
        """Return self for chained ``first.click()`` calls."""

        return self

    async def click(self) -> None:
        """Recording is handled at the page level via :meth:`get_by_role`."""

        return None


@dataclass
class FakeFinisherPage:
    """Async page double for the apply-finisher tool surface.

    Tests construct one of these per scenario, then pass it through a
    ``FinisherDeps`` instance into the tool under test.

    Attributes:
        ref_states: Mapping of ``eN`` ref → configured behavior.
        default_state: Locator state for any ref not in ``ref_states``.
        snapshot_text: Body returned by ``locator(...).aria_snapshot()``.
        screenshot_bytes: Body returned by ``page.screenshot()``.
        screenshot_raises: Exception class to raise on screenshot; ``None``
            to succeed.
        listbox_options: Options visible when the agent calls
            ``select`` and the native path raises.
        evaluate_results: Map of script substring → response value used by
            ``page.evaluate(...)``.
        url: Current page URL — tests mutate this to simulate a submit-time
            navigation.
        click_log: ``[ref, ...]`` of every click attempted.
        fill_log: ``[(ref, value), ...]`` of every fill attempted.
        select_log: ``[(ref, value), ...]`` of every select attempted.
        snapshot_mode: Mode argument passed to the last ``aria_snapshot`` call.
    """

    ref_states: dict[str, FakeLocatorState] = field(default_factory=dict)
    default_state: FakeLocatorState = field(default_factory=FakeLocatorState)
    snapshot_text: str = "stub snapshot"
    screenshot_bytes: bytes = b"\x89PNG\r\n\x1a\nfake"
    screenshot_raises: type[BaseException] | None = None
    listbox_options: list[str] = field(default_factory=list)
    evaluate_results: dict[str, object] = field(default_factory=dict)
    url: str = "https://example.com/apply"
    click_log: list[str] = field(default_factory=list)
    fill_log: list[tuple[str, str]] = field(default_factory=list)
    select_log: list[tuple[str, str]] = field(default_factory=list)
    snapshot_mode: str = ""
    wait_for_url_should_raise: bool = False

    def locator(self, selector: str) -> FakeLocator:
        """Return a locator matching ``selector`` or the default state.

        Args:
            selector: CSS / aria-ref / form-root selector.
        Returns:
            A :class:`FakeLocator` whose state is the configured ref or the
            page-wide default.
        """

        ref = _ref_from_selector(selector)
        state = self.ref_states.get(ref or "", self.default_state) if ref else self.default_state
        return FakeLocator(state=state, page=self, ref=ref)

    def get_by_role(self, role: str) -> FakeOptionLocator:
        """Mimic Playwright's role locator for the listbox fallback path."""

        _ = role
        return FakeOptionLocator(list(self.listbox_options))

    async def screenshot(self, *, full_page: bool = False, path: str | None = None) -> bytes:
        """Return the configured screenshot bytes, or raise when configured.

        Args:
            full_page: Accepted for signature parity.
            path: Accepted for signature parity.
        Returns:
            The configured PNG-ish bytes.
        Raises:
            Whatever class is configured in ``screenshot_raises``.
        """

        _ = (full_page, path)
        if self.screenshot_raises is not None:
            raise self.screenshot_raises("forced screenshot failure")
        return self.screenshot_bytes

    async def evaluate(self, script: str, arg: object | None = None) -> object:
        """Match the script substring to a configured response.

        Args:
            script: JavaScript payload passed by the tool.
            arg: Optional argument the tool builds.
        Returns:
            The matched configured value, or ``"quiet"`` for the
            MutationObserver script, or ``None`` otherwise.
        """

        _ = arg
        for needle, value in self.evaluate_results.items():
            if needle in script:
                return value
        if "MutationObserver" in script:
            return "quiet"
        return None

    async def wait_for_url(
        self,
        predicate: Callable[[str], bool] | str,
        *,
        timeout: float = 0,
    ) -> None:
        """Imitate ``page.wait_for_url`` for submit-classification tests.

        Args:
            predicate: Either a callable evaluated against ``self.url`` or a
                string URL to match exactly.
            timeout: Accepted for signature parity.
        Raises:
            TimeoutError: When the predicate is not yet satisfied (or when
                ``wait_for_url_should_raise`` is configured).
        """

        _ = timeout
        if self.wait_for_url_should_raise:
            raise TimeoutError("forced wait_for_url timeout")
        if callable(predicate):
            satisfied = predicate(self.url)
        else:
            satisfied = self.url == predicate
        if not satisfied:
            raise TimeoutError("URL has not changed yet")


__all__ = [
    "FakeFinisherPage",
    "FakeLocator",
    "FakeLocatorState",
    "FakeOptionLocator",
]
