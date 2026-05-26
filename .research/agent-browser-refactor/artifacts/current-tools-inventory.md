# Current tools.py inventory (snapshot for comparison)

Source: `src/agents/apply_finisher/tools.py`

## Tools registered in `FINISHER_TOOLS`

| Function | Playwright call(s) | Failure mode on Greenhouse comboboxes |
|---|---|---|
| `get_snapshot` | `page.locator(selector).aria_snapshot(mode="ai")` | Works; returns `[ref=eN]` markers |
| `click(ref)` | `page.locator(f"aria-ref={ref}").click()` | Fails: after combobox opens and React re-renders, old refs go stale |
| `fill(ref, value)` | `page.locator(f"aria-ref={ref}").fill(value)` | Works for text inputs; stale ref after re-renders |
| `select(ref, value)` | `locator.select_option(label=value)` → fallback `page.get_by_role("option")` | Fails: React-Select listbox options are not `<option>` elements; `get_by_role("option")` returns 0 matches in Greenhouse's virtualized dropdown |
| `wait_for_dom_quiet(ms)` | `page.evaluate(MutationObserver JS)` | Works but fragile on pages that block `evaluate` |
| `defer(...)` | no browser call | N/A |
| `lookup_cached_answer(...)` | no browser call | N/A |
| `flag_for_verify(...)` | no browser call | N/A |

## `complete_apply` (output tool in agent.py)

Registered as `ToolOutput(FinisherResult, name="complete_apply")` — no browser interaction.

## Key constants

```python
_MAX_SNAPSHOT_CHARS: int = 24_000
_DEFAULT_DOM_QUIET_MS: int = 300
_DOM_QUIET_TIMEOUT_MS: int = 5_000
_FORBIDDEN_CLICK_NAME_PREFIXES = ("submit", "apply", "send application", "send")
```

## Root selectors per ATS (from runner.py)

```python
_FORM_ROOT_BY_ATS = {
    "greenhouse": "#application-form, #application_form",
    "ashby": "form",
}
```
