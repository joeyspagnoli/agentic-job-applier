# local-gap-audit-001 — field_scanner phantom-input dedup point

**Source:** `src/agents/apply_worker/field_scanner.py` (272 lines, full file read 2026-05-25)
**Trigger:** Locked decision: Phase D adds phantom-input dedup at the scanner; epic Phase D bullet 4. Gap-analysis-greenhouse §J + gap-synthesis §3c describe the bug.

## Current scanner shape

The scanner is a single ~150-line `_FIELD_SCAN_JS` block executed via `page.evaluate(...)` in the main frame + every child frame. Filter logic at lines 139-157:

```js
elements.forEach(el => {
    if (el.type === 'hidden' || el.type === 'submit' ||
        el.type === 'button' || el.type === 'image') {
        return;
    }
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') {
        return;
    }
    const value = el.value || '';
    const isRequired = isFieldRequired(el);
    const validationError = getValidationError(el);
    const isEmpty = value.trim() === '';
    if (!isEmpty && !validationError) return;
    fields.push({ ... });
});
```

`getUniqueSelector(el)` at lines 112-125 falls back to `el.tagName.toLowerCase() + ':nth-child(' + (idx + 1) + ')'` when an element has no `id` and no `name`. **This is exactly the path that produces the phantom `input:nth-child(1)` selector** observed in iter 001 (7 phantoms) and iter 006 (7 phantoms).

`isFieldRequired()` (lines 102-110) reads `el.required` and `el.getAttribute('aria-required')`. **React-Select's hidden text-search input inside a `[role="combobox"]` wrapper inherits `aria-required="true"`** from the parent wrapper, so the scanner classifies it as a required gap.

## Proposed dedup point

Two complementary patches inside `_FIELD_SCAN_JS`:

1. **Skip a phantom inside a React-Select wrapper.** Add a filter just before the `fields.push(...)` call:
   ```js
   // Skip hidden text-search inputs inside React-Select widgets.
   // The visible combobox is captured separately.
   const isPhantomReactSelectInput = (
       el.tagName === 'INPUT' &&
       !el.id &&
       !el.name &&
       !getLabelText(el) &&
       el.closest('[class*="select__"], [class*="Select__"]') &&
       el.closest('[role="combobox"]')
   );
   if (isPhantomReactSelectInput) return;
   ```
   The double `closest()` is intentional: react-select wraps the input in a `__control` div AND the combobox role lives on a sibling element. Both ancestor patterns are present on Cloudflare Greenhouse markup.

2. **De-duplicate by `closest('[role="combobox"]')`** as a fallback: if two captured fields share the same combobox ancestor, keep only the one with a non-null `field_id` or non-null `label`.

The first patch is the cheap fix (matches the iter 001/006 phantom signature exactly). The second is the defensive backstop in case some company uses a non-react-select combobox.

## Test point

Add a fixture HTML file (e.g. `tests/fixtures/greenhouse_cloudflare_intern.html` — the saved iter 001 `dom_post.html` works) and assert `scan_unresolved_fields(page)` returns ~8 fields, not ~17, for the same DOM.

## Unaddressed by the epic

- The epic says "skip orphan `input:nth-child(1)` entries inside React-Select wrappers." That's necessary but **not sufficient** — the field_scanner.py source has no awareness of `role="combobox"` at all today; it only filters on hidden/submit/button/image and visibility. The dedup needs to be implemented inside `_FIELD_SCAN_JS`, not in `_parse_raw_fields()`, because the raw side already lost the parent context by the time Python sees it.
- `getOptions(el)` at lines 79-100 doesn't enumerate React-Select's open listbox options (they live in a separate React portal). The finisher's `select(ref, value)` tool will need to click the combobox → wait for listbox → fuzzy-match → click. This is separate from the dedup but worth noting because the scanner currently reports `options: null` for every React-Select, which the agent's prompt will need to handle.
