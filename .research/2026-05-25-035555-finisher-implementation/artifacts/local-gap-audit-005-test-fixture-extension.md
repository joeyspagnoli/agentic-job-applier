# local-gap-audit-005 — test fixture extensibility for the finisher

**Source:** `tests/test_apply_worker_and_retry_semantics.py` lines 36-260. FakeBrowserPage, FakeScanFrame, FakeScanPage, FakeUploadLocator, FakeUploadPage classes.
**Trigger:** Phase C acceptance criterion: "6/6 BYO tools have unit tests against a Playwright-fake page."

## What `FakeBrowserPage` (lines 36-135) covers today

| Method | Behavior |
|---|---|
| `goto(url, timeout, wait_until)` | Records URL or raises `RuntimeError("navigation failed")` when `fail_on_goto=True` |
| `wait_for_load_state(state, timeout)` | No-op (returns None) |
| `content()` | Returns `"<html><body><form></form></body></html>"` constant |
| `evaluate(script, arg)` | Branches on `script == browser._JS_DETECT_SIMPLIFY` → returns `simplify_detected` boolean; **raises `RuntimeError("Unexpected evaluate script")` for any other script** |

Notable: `evaluate()` only knows about ONE script (`_JS_DETECT_SIMPLIFY`). It does NOT know about `_JS_CLICK_SIMPLIFY_AUTOFILL` (the actual click) or `_FIELD_SCAN_JS` (the field scanner). The existing flow tests must therefore never reach the click or scan steps.

## What the finisher tests will need

The 8 BYO tools from the epic (`get_snapshot`, `click`, `fill`, `select`, `wait_for_idle`, `goto`, `defer`, `complete_apply`) plus the answer-cache tool (per analysis-015) need their own fake-page surface. Each tool will call `playwright.async_api.Page` methods like:

| Tool | Page method(s) called |
|---|---|
| `get_snapshot` | `page.accessibility.snapshot()` OR `page.evaluate(<custom AX-tree script>)` |
| `click(ref)` | `page.locator(ref).click()` (or `page.evaluate(...)` if refs are JS-handled) |
| `fill(ref, value)` | `page.locator(ref).fill(value)` |
| `select(ref, value)` | `page.locator(ref).select_option(value)` or compound click → fuzzy match |
| `wait_for_idle()` | `page.wait_for_timeout(300)` + custom MutationObserver script (see gap-audit-006) |
| `goto(url)` | `page.goto(url)` |
| `defer` | No browser interaction; pure record |
| `complete_apply` | No browser interaction; pure signal |

`FakeBrowserPage` covers none of `accessibility`, `locator`, or the click/fill methods on locators. **It needs net-new fixture work**, not extension.

## Recommendation: a new `FakeFinisherPage` class

Don't extend `FakeBrowserPage` — it would bloat the existing class and risk breaking the flow tests. Add a new sibling class in a new file (e.g., `tests/fixtures/fake_finisher_page.py`) with:

```python
class FakeFinisherPage:
    """Async Playwright-like page for testing finisher BYO tools."""

    def __init__(self, ax_tree_snapshot: dict, ...):
        self.ax_tree_snapshot = ax_tree_snapshot
        self.click_log: list[str] = []
        self.fill_log: list[tuple[str, str]] = []
        self._locator_factory = ...
        self.accessibility = _FakeAccessibility(ax_tree_snapshot)

    def locator(self, selector: str) -> FakeLocator: ...
```

Wire the ref-resolution (`@eN` → element) through the same fake-locator path. Each tool test gets its own `FakeFinisherPage(ax_tree=<fixture>)` with deterministic state.

## Saved real-world DOM as fixtures

The smoke run produced real DOM HTML files at `.research/simplify-loop/iterations/{NNN}/dom_post.html`. **Suggestion: copy 2-3 of these into `tests/fixtures/` as canonical inputs** for the AX-tree snapshot tool tests. Then the AX-tree tool can be tested end-to-end: real DOM → snapshot → assertions on what `@eN` refs were emitted. This is high-value because the AX-tree transformation is the single most likely source of finisher bugs.

## Gap not in the epic

The epic Phase C acceptance criterion says "6/6 BYO tools have unit tests against a Playwright-fake page" but doesn't address:
- **Integration test for the agent loop itself** — multiple tool calls in sequence, defer policy enforcement, complete_apply exit, max_turns cap.
- **Test for the defer-rules regex matcher** (Phase B acceptance covers this — OK).
- **Test that confirms phantom-input dedup is applied AT the scanner AND the finisher's snapshot tool doesn't undo the dedup.** (Implicit but worth being explicit.)
