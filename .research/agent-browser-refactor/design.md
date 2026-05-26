# Finisher refactor: agent-browser as the tool surface

## TL;DR

The current finisher fails on Greenhouse's React combobox dropdowns (country, phone code, Yes/No questions) because Playwright's `aria-ref` locators lose track of elements after React re-renders; agent-browser's semantic `find role combobox` locators survive those re-renders. The refactor swaps only the five browser-touching tools (`get_snapshot`, `click`, `fill`, `select`, `wait_for_dom_quiet`) to thin `subprocess.run` wrappers around agent-browser CLI; the three state-only tools (`lookup_cached_answer`, `defer`, `flag_for_verify`) and the output tool (`complete_apply`) are untouched. The worker keeps Playwright for everything it already does reliably (CDP connect, Simplify autofill, resume upload, DOM screenshots); only the finisher agent's tool surface changes.

---

## New tool surface

| Tool | Current impl | New impl | Rationale |
|---|---|---|---|
| `get_snapshot` | `page.locator(selector).aria_snapshot(mode="ai")` with screenshot fallback | `subprocess.run(["agent-browser", "snapshot", "-i", "-c", "-s", FORM_ROOT_CSS])` | agent-browser snapshot produces `@eN` refs natively; `-s` scopes to form root; `-c` keeps output compact |
| `click` | `page.locator(f"aria-ref={ref}").click()` | `subprocess.run(["agent-browser", "click", ref])` for `@eN` refs; `subprocess.run(["agent-browser", "find", "role", "combobox", "click", "--name", label])` for semantic fallback | semantic `find` survives React re-mounts where `@eN` stales |
| `fill` | `page.locator(f"aria-ref={ref}").fill(value)` | `subprocess.run(["agent-browser", "fill", ref, value])` | direct swap; same ref scheme |
| `select` | native `select_option` + listbox fallback via `page.get_by_role("option")` | `subprocess.run(["agent-browser", "select", ref, value])` for `<select>`; `subprocess.run(["agent-browser", "find", "role", "combobox", "click", "--name", label])` + `find text value click` for React-Select | this is the specific failure case — agent-browser's semantic path handles React-Select reliably |
| `wait_for_dom_quiet` | `page.evaluate(MutationObserver JS)` | `subprocess.run(["agent-browser", "wait", "--load", "networkidle"])` or `subprocess.run(["agent-browser", "wait", str(ms)])` | agent-browser wait commands cover both cases without JS injection |
| `lookup_cached_answer` | reads `FinisherDeps.cache` | **unchanged** | no browser interaction |
| `defer` | appends to `FinisherDeps.recorded_deferrals` | **unchanged** | no browser interaction |
| `flag_for_verify` | appends to `FinisherDeps.drafted_fields` | **unchanged** | no browser interaction |
| `complete_apply` | Pydantic AI `ToolOutput` | **unchanged** | output tool, no browser |

**Ref scheme change**: old tools used Playwright's `aria-ref=eN` selector string (e.g. `"e5"`); new tools use agent-browser's `@eN` prefix (e.g. `"@e5"`). The `_normalize_aria_ref` helper in `tools.py` becomes `_normalize_ab_ref` — accepts `"@e5"` or `"e5"` or `"5"`, always emits `"@e5"`.

**`_FORBIDDEN_CLICK_NAME_PREFIXES` guard stays**. Before each `click` call the tool checks the element's accessible name from the snapshot (captured on the previous `get_snapshot` call and stored in `FinisherDeps.last_snapshot_names: dict[str, str]`). If the name starts with submit/apply/send, it raises `ModelRetry` exactly as today.

---

## System prompt rewrite

### Sections to keep verbatim from current `prompts.py`

- **Tier model** (Tier 1 / 2 / 3 classification, EEO-is-not-Tier-3 callout, `apply_prefs` rule) — proven logic, nothing browser-specific in it.
- **DO-NOT-CLICK-SUBMIT rule** — word-for-word. Extend to also say "never call `find role button click --name` with any Submit/Apply/Send label".
- **Untrusted data guard** — prompt-injection defense, keep as-is.
- **Never invent profile data** rule.
- **`complete_apply` terminates the run** note.
- **Workflow step ordering** (snapshot → classify → fill/defer/flag → re-snapshot when state changes → complete).

### Sections to replace / rewrite

- **Tool inventory** — rewrite to describe the new CLI-backed tools and their arguments. The most important new thing the agent must understand:
  - Refs (`@eN`) are **stale after any page mutation**. Re-call `get_snapshot` before the next ref-based interaction.
  - Use `click(label=...)` (semantic mode) instead of `click(ref=...)` when the element is a combobox that will re-render after opening (country, phone code, Yes/No dropdowns). The `label` argument triggers `agent-browser find role combobox click --name <label>`.
  - After a combobox click, the option list is a new render. Use `select_option(label=..., value=...)` which triggers `agent-browser find text <value> click`.
  - `wait_for_dom_quiet(ms)` now delegates to `agent-browser wait <ms>` or `agent-browser wait --load networkidle` for Ashby EEO fieldset re-mounts.

### New section to add: "How element refs work (read first)"

Inline a short excerpt from the agent-browser core skill:

```
Refs (@e1, @e2, …) are assigned fresh on every snapshot. They become
stale the moment the page changes — after clicks that navigate, form
submits, or dynamic re-renders. Always re-snapshot before your next
ref interaction. When a combobox opens a listbox and re-renders the
form, the old refs for non-combobox fields are also stale.
```

### ATS fragments

Keep the per-ATS fragment structure (`_GREENHOUSE_FRAGMENT`, `_ASHBY_FRAGMENT`). Update the Greenhouse fragment:

- Replace the old `click(ref) to open, then select(ref, value)` pattern with:  
  "For React-Select comboboxes (Country, State, How did you hear), call `click(label='Country')` — this uses a semantic combobox locator that survives React re-renders. Then call `select_option(label='Country', value='United States')` to pick from the opened list."
- Replace the `intl-tel-input` phone widget instructions with the new two-step: `click(label='Phone Number Country Flag')` then `select_option(label='Phone Number Country Flag', value='United States (+1)')` then `fill(ref, phone_number)`.

---

## Runner lifecycle

### What changes in `runner.py`

The signature of `run_finisher` loses the `page: Page` parameter. It gains nothing — agent-browser is a stateful process-level CLI that already holds a Chrome session. The runner only needs to ensure the right URL is open before handing off.

**Step-by-step**:

1. **Worker calls `run_finisher`** with the same args minus `page`. Instead it passes `apply_url: str` (the normalized URL the worker already navigated to) and the existing `ats`, `target_company`, etc.
2. **Runner pre-flight**: `subprocess.run(["agent-browser", "get", "url"])` → verify the current URL matches `apply_url`. If not (shouldn't happen if worker flow is unchanged), call `subprocess.run(["agent-browser", "open", apply_url])` and wait for load.
3. **Runner builds `FinisherDeps`**: same as today minus the `page` field. `FinisherDeps.page` field is removed; `FinisherDeps` gets no new field — agent-browser session state is process-global.
4. **Agent loop**: unchanged. `agent.iter()` drives the Pydantic AI loop. Each tool call does a blocking `subprocess.run` to the agent-browser CLI (synchronous calls wrapped in `asyncio.get_event_loop().run_in_executor` or just `asyncio.to_thread` to stay on the async event loop).
5. **Cost accumulation and result synthesis**: unchanged.
6. **Cleanup**: nothing — worker manages the Chrome session lifetime.

### Session ownership

- The worker's Playwright `connect_over_cdp` session and agent-browser both talk to the same host Chrome on port 9222.
- They are active at different times: Playwright handles steps 1–7 of `_run_application_flow` (navigation, Simplify, upload, scan, confidence, verify, artifacts), then the finisher runs exclusively via agent-browser for step 8.
- There is no concurrent access conflict as long as the worker awaits `run_finisher` synchronously (which it already does).
- After `run_finisher` returns, the worker uses Playwright again for steps 9–11 (screenshot, DOM save, gate, submit). This is fine — Playwright reconnects to the same page.

### `FinisherDeps` changes

```python
# Remove:
page: "Page"
form_root_selector: str

# Add:
apply_url: str          # for pre-flight URL check
form_root_css: str      # CSS selector to pass as -s to snapshot (same values as before)
last_snapshot_names: dict[str, str]  # @eN -> accessible name, populated by get_snapshot
```

`form_root_css` keeps the same values as the old `form_root_selector`: `"#application-form, #application_form"` for Greenhouse, `"form"` for Ashby. It's passed as `-s <selector>` to `agent-browser snapshot`.

---

## Worker integration (Playwright vs agent-browser split)

**Recommendation: keep Playwright for all worker steps; use agent-browser only inside the finisher.**

Rationale:

1. **Resume upload relies on `page.set_input_files`** (Playwright's file input API). There is no agent-browser equivalent that's as reliable for shadow-root file inputs. This is working — don't touch it.
2. **Simplify autofill uses `page.evaluate` to pierce shadow roots**. The JS injection approach is brittle enough already; switching it to agent-browser's `eval` command adds subprocess overhead and a new failure mode with no benefit.
3. **`connect_over_cdp`** is the worker's established session. Playwright owns the browser context lifetime; agent-browser attaches to the same Chrome. If agent-browser breaks, Playwright can still take artifacts.
4. **Steps 9–11 (screenshot, DOM, gate, submit)** use Playwright locators that are already stable (the submit button locator isn't a React combobox). No reason to switch.
5. **The finisher is the only component that's failing**. The failure is specifically React combobox dropdowns. The split keeps risk contained: only `tools.py` changes; `browser.py` is untouched.

**The split**:
```
Playwright (browser.py):  navigate → Simplify → upload → scan → confidence → verify → artifacts → submit
agent-browser (tools.py): finisher agent loop only (step 8)
```

**One wrinkle**: the worker currently passes `page` directly to `run_finisher`. After the refactor it passes `apply_url` instead. The worker call site in `browser.py` line ~558 changes from:

```python
finisher_result = await run_finisher(
    page=playwright_page,
    ...
)
```

to:

```python
finisher_result = await run_finisher(
    apply_url=playwright_page.url,
    ...
)
```

That's the only change to `browser.py`.

---

## Test seam

### Unit tests for tools

**Current approach**: mock `Page` — e.g. `AsyncMock` for `page.locator().aria_snapshot()`.

**New approach**: mock `subprocess.run`. Each tool becomes:

```python
import subprocess

def _ab(args: list[str]) -> str:
    result = subprocess.run(["agent-browser"] + args, capture_output=True, text=True, check=True)
    return result.stdout
```

In tests, monkeypatch `subprocess.run` (or the thin `_ab` wrapper):

```python
def fake_ab(args, **kwargs):
    if args[1] == "snapshot":
        return FakeResult(stdout=FIXTURE_SNAPSHOT_YAML, returncode=0)
    if args[1] == "fill":
        return FakeResult(stdout=f"filled {args[2]} with {args[3]}", returncode=0)
    ...

monkeypatch.setattr("src.agents.apply_finisher.tools.subprocess.run", fake_ab)
```

Fixture snapshot YAML files live in `tests/fixtures/snapshots/` (one per ATS, one for the Greenhouse combobox-open state). These replace the current `AsyncMock(return_value=FIXTURE_SNAPSHOT_YAML)` pattern.

### What to fixture-test specifically

1. `get_snapshot` — returns parsed snapshot text; truncates at `_MAX_SNAPSHOT_CHARS`.
2. `click` in ref mode — calls `agent-browser click @e5`; blocks submit refs.
3. `click` in semantic mode (`label=...`) — calls `agent-browser find role combobox click --name "Country"`.
4. `select_option` — calls `agent-browser find text "United States" click` after the combobox is open.
5. `fill` — increments `fields_filled_count`, calls `agent-browser fill @e3 "value"`.
6. `wait_for_dom_quiet` — calls `agent-browser wait <ms>`.
7. `defer`, `flag_for_verify`, `lookup_cached_answer` — these don't touch subprocess; existing tests port unchanged.

### End-to-end smoke test

The existing `tests/test_apply_loop_safe_mode.py` and `tests/test_user_triggered_apply.py` (currently untracked) will need their Playwright `Page` mocks removed and replaced with agent-browser subprocess mocks at the `tools._ab` level. The `run_finisher` call site no longer needs `page=AsyncMock()` — pass `apply_url="https://job-boards.greenhouse.io/..."` instead.

A new `tests/smoke/test_finisher_greenhouse.py` should run against a recorded fixture:

```bash
# Record once against a real Greenhouse form (in safe_mode):
agent-browser snapshot -i -c -s "#application-form" > tests/fixtures/snapshots/greenhouse_form.txt
```

Then the smoke test uses `monkeypatch.setattr("subprocess.run", fixture_dispatcher)` to replay the recorded snapshot and verify the agent fills the expected fields without deferring everything.

---

## Risks

- **subprocess latency adds up.** Each agent-browser CLI call spawns a subprocess and communicates over a Unix socket/HTTP to the running browser daemon. Empirically 50–150ms per call. A 15-field form with 30 tool calls adds ~3–5 seconds. Acceptable, but monitor.

- **agent-browser session may not be open when the finisher runs.** If the parallel sub-agent's container install doesn't have agent-browser connected to host Chrome before `run_finisher` is called, every subprocess call will fail with a "no session" error. The pre-flight URL check in the runner will catch this early and return `RUNTIME_ERROR` rather than silently filling nothing. Mitigation: add an explicit health-check in the runner before the agent loop.

- **`@eN` refs stale on the first re-render after any fill.** The current Playwright implementation had the same problem (it was masking it by re-snapshotting often). The new prompt's "re-snapshot after any page mutation" instruction is critical. If the model doesn't follow it, it will send stale refs and get `Error: ref @e5 not found`. agent-browser returns a non-zero exit code on bad refs; the tool raises `ModelRetry`. This is recoverable but wastes turns.

- **`-s` CSS selector for form root may not scope correctly.** agent-browser's `-s` flag uses `document.querySelector` semantics. The Greenhouse comma-joined selector `"#application-form, #application_form"` may not be supported — `querySelector` accepts comma selectors but they match the first found, which is correct behavior. Verify this during initial smoke testing.

- **Greenhouse phone `intl-tel-input` widget.** The current code already flags this as complex. agent-browser's `find role combobox click --name "Phone Number"` may not find the flag selector widget because it uses a custom `<div>` with `role=combobox` that doesn't surface a consistent `aria-label`. May need a CSS fallback: `agent-browser click ".iti__selected-flag"`. Plan B: classify phone country code as Tier 1 with a hardcoded `find text "United States" click` after opening.

- **`asyncio.to_thread` overhead for sync subprocess calls.** The Pydantic AI tool runner is async; `subprocess.run` is blocking. Wrapping in `asyncio.to_thread` is correct but adds thread pool overhead on high-concurrency deployments. For the current single-apply-at-a-time architecture this is fine; revisit if concurrency increases.

- **`FinisherDeps.page` removal breaks any test that imports `FinisherDeps` and passes a `Page`.** The test suite change is mechanical but needs to happen atomically with the `schemas.py` change to avoid a broken intermediate state.

---

## Implementation order

### Commit 1: Update `FinisherDeps` and `runner.py` signatures (no behavior change yet)

- Add `apply_url: str` and `form_root_css: str` to `FinisherDeps`; make `page` optional with `page: Optional["Page"] = None` (keeps old tests passing during transition).
- Change `run_finisher` to accept `apply_url: str` in addition to (not replacing) `page`.
- Update `browser.py` call site to pass `apply_url=playwright_page.url`.
- All existing tests still pass.

### Commit 2: Rewrite `tools.py` — browser tools become CLI wrappers

- Add `_ab(args: list[str]) -> str` helper that calls `subprocess.run(["agent-browser"] + args, ...)` inside `asyncio.to_thread`.
- Replace `get_snapshot`, `click`, `fill`, `select`, `wait_for_dom_quiet` with CLI wrappers.
- Add `click(label: str | None = None, ref: str | None = None)` overload — semantic mode when `label` is given.
- Add `select_option(label: str, value: str)` as a new tool (two-step: open combobox by label, then click the value text).
- Rename `_normalize_aria_ref` to `_normalize_ab_ref`, update prefix to `@`.
- Move forbidden-name check to read from `FinisherDeps.last_snapshot_names` dict.
- Remove `wait_for_dom_quiet`'s MutationObserver JS; delegate to `agent-browser wait`.
- Keep `FINISHER_TOOLS` tuple updated.

### Commit 3: Rewrite `prompts.py` — update tool inventory and ref staleness section

- Add "How element refs work (read first)" section with staleness warning.
- Rewrite tool inventory to match new tool names/signatures.
- Keep tier model, DO-NOT-SUBMIT rule, untrusted data guard verbatim.
- Update ATS fragments with new combobox patterns.

### Commit 4: Remove `page` from `FinisherDeps` and `runner.py`

- Drop optional `page` field now that tools.py no longer uses it.
- Drop `form_root_selector` (replaced by `form_root_css`).
- Update `schemas.py` `TYPE_CHECKING` block to remove Playwright import.
- Confirm `runner.py` pre-flight URL check works.

### Commit 5: Update tests

- Replace `AsyncMock(Page)` fixtures with `monkeypatch.setattr` on `subprocess.run` / `tools._ab`.
- Add snapshot fixture files under `tests/fixtures/snapshots/`.
- Add a Greenhouse combobox-specific test case that verifies `select_option` takes the two-step semantic path.
- Port existing `test_apply_loop_safe_mode.py` and `test_user_triggered_apply.py` to new test seam.
