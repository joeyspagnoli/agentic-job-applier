# Reference: `dotel/applyjobs` — open-source job-application form-filler

**File:** `src/agent/form_filler.py`
**Repo:** https://github.com/dotel/applyjobs
**Fetched:** 2026-05-25

**This repo is a direct functional analogue of our finisher.** It's an LLM-driven agentic
form-filler for Greenhouse/Workday job applications. It does NOT use Pydantic AI — uses its
own minimal `AgentLoop` / `ToolDef` — but the **Playwright integration patterns are exactly
what we want**.

## Headline pattern: native `aria-ref=` Playwright locators

Playwright 1.59+ supports `aria-ref=eN` as a first-class locator engine. **NO custom RefMap
needed**. The `mode="ai"` parameter on `aria_snapshot()` produces YAML with `[ref=eN]`
markers, and `page.locator("aria-ref=eN")` resolves them.

```python
# Take a snapshot WITH refs:
yaml = root.aria_snapshot(mode="ai")
# yaml contains lines like:
#   - textbox "First name" [ref=e5] [required]
#   - button "Submit application" [ref=e22]

# Round-trip back to a locator — Playwright does it for you:
loc = tab.locator(f"aria-ref={ref}")   # ref = "e5"
loc.first.click()
loc.first.fill("Jane")
```

**This eliminates the entire pocketpaw `RefMap` / `SnapshotGenerator` / selector-rebuild layer.**
Our finisher gets dramatically simpler than I previously estimated.

## Backward-compat note from the source

```python
try:
    yaml = root.aria_snapshot(mode="ai")
except TypeError:
    # Playwright < 1.59: no `mode` kwarg — default snapshot (no [ref=eN]).
    yaml = root.aria_snapshot()
```

So if we pin Playwright `>=1.59` (which we already would for modern features), we always get
refs. We can drop the fallback.

## Tool surface (compare to our planned set)

`dotel/applyjobs` tools:

1. `read_form_state()` → returns `{"aria_snapshot": yaml, "ref_markers": int, "hint": "..."}`
2. `fill_field(label, value, ref="")` → fills text/textarea/number/email
3. `select_option(label, option, ref="")` → handles native `<select>` AND custom listbox dropdowns
4. `check_option(label, value, ref="")` → checkbox/radio
5. `flag_unknown(label, reason)` → marks fields the model can't answer (= our `defer`)

Compare to our planned finisher tools:

| Our tool | Their equivalent | Notes |
|---|---|---|
| `get_snapshot()` | `read_form_state()` | Identical |
| `click(ref)` | (subsumed into `select_option` for custom dropdowns) | We may want both |
| `fill(ref, value)` | `fill_field(label, value, ref)` | They include `label` as fallback if ref stale |
| `select(ref, value)` | `select_option(label, option, ref)` | Same |
| `defer(field_id, reason, q)` | `flag_unknown(label, reason)` | Same |
| `lookup_cached_answer(q)` | (not present) | Our addition |
| `complete_apply()` | (implicit — returns list of unknowns) | We make it an explicit tool |
| `flag_for_verify(ref, confidence)` | (not present) | Our addition for Tier 2 |

## Three patterns to copy verbatim

### 1. Snapshot-then-truncate with a char budget

```python
_MAX_ARIA_SNAPSHOT_CHARS = 24_000
if len(yaml) > _MAX_ARIA_SNAPSHOT_CHARS:
    yaml = yaml[:_MAX_ARIA_SNAPSHOT_CHARS] + "\n...(truncated)"
```

24K chars ≈ 6K tokens. Reasonable cap for a form page. If exceeded, the model gets a clear
signal that truncation happened.

### 2. Ref normalization (accept `e5` OR `5`)

```python
def _normalize_aria_ref(ref: str) -> str:
    ref = (ref or "").strip()
    if not ref:
        return ""
    if ref.startswith("e") and ref[1:].isdigit():
        return ref
    if ref.isdigit():
        return f"e{ref}"
    return ref
```

LLMs sometimes drop the `e` prefix. Always normalize.

### 3. Multi-strategy locator fallback

If the `aria-ref=` lookup fails (rare but happens after re-render), they fall through to
`get_by_label` → `get_by_role` → `get_by_placeholder`:

```python
for strategy in (
    lambda: page.get_by_label(label_short, exact=False),
    lambda: page.get_by_label(label, exact=False),
    lambda: page.get_by_role("textbox", name=label_short, exact=False),
    lambda: page.get_by_role("textbox", name=label, exact=False),
    lambda: page.get_by_role("spinbutton", name=label_short, exact=False),
    lambda: page.get_by_placeholder(label_short, exact=False),
):
    try:
        loc = strategy()
        if loc.count() > 0 and loc.first.is_visible(timeout=1_000):
            _fill_via_playwright_locator(loc.first)
            return {"ok": True, ...}
    except Exception:
        continue
return {"ok": False, ..., "error": "Field not found — pass ref from read_form_state ..."}
```

**Recommendation for finisher:** the model emits BOTH `ref` AND `label` in its tool call;
we try `aria-ref={ref}` first, then fall back to label-based locators. This makes the model
robust to mid-turn re-renders.

## How they handle the form root (iframe-aware)

```python
def _form_root_locator(root: PlaywrightFormRoot):
    """Prefer `#application_form`, then a likely application `form`, else `body`."""
    for sel in ("#application_form", "form[action*='application']"):
        loc = root.locator(sel).first
        try:
            if loc.count() > 0:
                loc.wait_for(state="attached", timeout=3_000)
                return loc
        except Exception:
            continue
    return root.locator("body").first
```

Greenhouse uses `#application_form`. Workday uses `form[action*='application']`. The snapshot
is scoped to this subtree, NOT the whole page — which is huge for token economics. The model
sees just the form, not the chrome / nav / footer.

**Finisher should do the same** — scope to `#application_form` on Greenhouse and the
Ashby-equivalent form root selector.

## How they handle iframe / frame roots

```python
def _owner_page(root: PlaywrightFormRoot) -> Page:
    """Tab `Page` that owns `root`. `aria-ref=…` from iframe snapshots resolves here, not on `Frame`."""
    if isinstance(root, Page):
        return root
    return root.page
```

**Important:** `aria-ref` resolution happens on the owning `Page`, not on the `Frame` you took
the snapshot from. Pass the Frame to `aria_snapshot()` but the Page to `locator("aria-ref=...")`.

## Anti-pattern they admit to

```python
# Playwright < 1.59: no `mode` kwarg — default snapshot (no [ref=eN]).
```

Old Playwright pinning would break this. We pin `playwright>=1.59`.

Looking at PyPI: latest Playwright Python is 1.59.x as of late 2025. By 2026-05-25, we should
pin `playwright==1.62.0` or newer.
