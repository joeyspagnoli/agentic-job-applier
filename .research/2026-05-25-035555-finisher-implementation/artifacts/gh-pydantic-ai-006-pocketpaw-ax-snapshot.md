# Reference: `pocketpaw/pocketpaw` — AX-tree snapshot with stable refs

**Repo:** https://github.com/pocketpaw/pocketpaw
**Files:** `src/pocketpaw/browser/snapshot.py`, `src/pocketpaw/browser/driver.py`
**Fetched:** 2026-05-25

**This is the closest existing pattern to what we want.** It converts Playwright's accessibility
tree into a numbered text snapshot with stable refs the model can use to address elements.

## RefMap — the stable-ref mechanism

```python
@dataclass
class RefMap:
    refs: dict[int, str] = field(default_factory=dict)
    next_ref: int = 1

    def add(self, selector: str) -> int:
        """Add a selector and return its reference number."""
        ref = self.next_ref
        self.refs[ref] = selector
        self.next_ref += 1
        return ref

    def get_selector(self, ref: int) -> str | None:
        return self.refs.get(ref)
```

The map is built each time a snapshot is taken. Refs are integers 1..N within a single snapshot;
each new snapshot resets and rebuilds. The selector is an **ARIA-role-based Playwright locator**
(see below).

## Snapshot text format (verbatim example output)

```
Page: Apply for Software Engineer
URL: https://boards.greenhouse.io/example/jobs/12345

- heading "Apply for Software Engineer" [level=1]
- textbox "First name" [ref=1] [required]
- textbox "Last name" [ref=2] [required]
- textbox "Email" [ref=3] [type=email] [required]
- textbox "Phone" [ref=4]
- button "Attach resume" [ref=5]
- combobox "How did you hear about us?" [ref=6]
- textbox "Why do you want to work here?" [ref=7] [required]
- button "Submit application" [ref=8]
```

The model reads this text. To click "First name" it emits `fill(ref=1, value="Jane")`.

**Roles that get refs (interactive):**
- `button`, `link`, `textbox`, `checkbox`, `radio`, `combobox`, `listbox`, `option`,
  `menuitem`, `menuitemcheckbox`, `menuitemradio`, `switch`, `slider`, `spinbutton`,
  `searchbox`, `tab`, `treeitem`

**Roles skipped entirely:**
- `none`, `presentation`, `generic`

## Selector generation — `role=...[name=...]`

```python
def _generate_selector(self, node: AccessibilityNode) -> str:
    """Format: role=<role>[name="<name>"]"""
    selector_parts = [f"role={node.role}"]
    if node.name:
        escaped_name = node.name.replace('"', '\\"')
        selector_parts.append(f'[name="{escaped_name}"]')
    return "".join(selector_parts)
```

This produces a **Playwright accessibility locator** (e.g., `role=textbox[name="Email"]`).
When the model says `click(ref=3)`, we look up `refs[3]` → `role=textbox[name="Email"]` and call
`page.locator(...)`. This is more stable than CSS selectors because the underlying DOM can
re-render but the ARIA role/name typically stays the same.

## Click / fill implementations

```python
async def click(self, ref: int) -> NavigationResult:
    selector = self._refmap.get_selector(ref)
    if selector is None:
        raise ValueError(f"Invalid ref: {ref}. Element not found in current snapshot.")
    locator = self._page.locator(selector)
    await locator.click()
    return await self._take_snapshot()   # snapshot AFTER click

async def type_text(self, ref: int, text: str) -> str:
    selector = self._refmap.get_selector(ref)
    if selector is None:
        raise ValueError(f"Invalid ref: {ref}. Element not found in current snapshot.")
    locator = self._page.locator(selector)
    await locator.fill(text)
    return f"Typed text into element [ref={ref}]"
```

Two key takeaways:

1. **`click` re-snapshots automatically**, `type_text` does NOT. Reason: after clicking, the page
   often navigates / re-renders, so the prior refmap is stale anyway. After typing, the page
   typically stays put.
2. **Invalid ref → `ValueError`.** This is the spot to convert to `ModelRetry` for the
   Pydantic AI integration:
   ```python
   if selector is None:
       raise ModelRetry(
           f"Ref {ref} not found in current snapshot. Call get_snapshot() first."
       )
   ```

## Snapshot generation — the algorithm

The `SnapshotGenerator._process_node` recursively walks the Playwright AX dict, emitting one
indented line per interesting node. Properties surfaced as `[level=]`, `[focused]`, `[disabled]`,
`[checked]`, `[expanded=]`, `[selected]`, `[pressed]`, `[required]`, `[readonly]`, `[type=...]`.

This format is human-readable AND machine-friendly — names are quoted so role-name pairs are
unambiguous.

## Adaptation for finisher

| Pocketpaw choice | Our choice for finisher |
|---|---|
| `ref=1` style (integer) | `@e1` style (per user request; the leading `@` is unambiguous in JSON) |
| Snapshot after every action | Same — `click` / `fill` return updated snapshot text |
| `role=textbox[name="..."]` selectors | Same — Playwright accessibility locators |
| Raise `ValueError` on stale ref | Raise `ModelRetry` on stale ref |
| Hardcoded interactive role list | Same — port `INTERACTIVE_ROLES` set verbatim |
| Truncate names to 100 chars | Same |

## Token economics

A typical Greenhouse "Apply" form (~10 fields) produces a snapshot of:
- 10 textbox lines × ~50 chars = 500 chars
- 1 file-upload button = 40 chars
- 1 dropdown = 60 chars
- 1 submit button = 40 chars
- Page header = 100 chars

Total ≈ 750 chars ≈ 200 tokens. A screenshot at 1280x720 at "high detail" on GPT-4-class models
costs ~2000-3000 image tokens. **AX-tree is ~10x cheaper**, matching the user's prior assertion.
