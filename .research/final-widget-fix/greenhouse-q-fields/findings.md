# Greenhouse React-Select Widget: Why Some Fields Failed in Run 24

## Executive Summary

All 6 failing fields share identical React-Select HTML structure with the working fields. The root causes were NOT the widget pattern — they were label-text matching issues and a compound option set bug:

1. **q918**: Label contains U+2019 curly apostrophe in "job's location". Agent used straight apostrophe -> `find label` mismatch -> field skipped.
2. **q923**: Label has trailing newline `\n` before the asterisk span -> label match fails.
3. **q924**: Options are NOT date strings. Expected "December 2027" but actual options are "Immediately after the internship ends" / "Need to return to school and available upon graduation".
4. **q925**: `aria-required="false"` — likely deprioritized by the agent in run 24.
5. **All fields**: Dropdown exposes 245 `[role="option"]` items (240 country phone codes + actual options) due to Greenhouse rendering phone-flag selectors in the same aria scope.

---

## 1. HTML Comparison

### WORKING: hispanic_ethnicity (filled: "No")

```html
<label id="hispanic_ethnicity-label" ...>Are you Hispanic/Latino?</label>
<div class="select-shell remix-css-b62m3t-container">
  <div class="select__value-container select__value-container--has-value">
    <div class="select__single-value">No</div>
    <input class="select__input" style="opacity: 0;"/> <!-- opacity:0 = filled -->
  <!-- aria-describedby="hispanic_ethnicity-error" (NO placeholder ref = filled) -->
```

### WORKING: question_66747919 (filled: "No")

```html
<label id="question_66747919-label" ...>
  Do you now or will you in the future require immigration sponsorship to work at Cloudflare?
  <span aria-hidden="true">*</span>
</label>
<div class="select__single-value">No</div>
<!-- aria-describedby="question_66747919-error" (no placeholder ref = filled) -->
```

No special characters. Plain ASCII label. aria-describedby excludes placeholder ID when filled.

### WORKING: question_66747921 (filled: "Yes" — dropdown OPEN in run 24 DOM)

```html
<label id="question_66747921-label" ...>
  Are you currently enrolled in a university or program and will return to the program upon completion of internship?
</label>
<!-- aria-expanded="true" — dropdown was OPEN when DOM captured -->
<div class="select__single-value">Yes</div>
<div class="select__option--is-focused select__option--is-selected" role="option">Yes</div>
```

DOM captured mid-interaction with dropdown open and "Yes" focused+selected.

### FAILING: question_66747918 (empty — curly apostrophe)

```html
<label id="question_66747918-label" ...>
  Do you currently live or are you willing to relocate to the job&#x2019;s location?
  <!-- U+2019 RIGHT SINGLE QUOTATION MARK in "job's" -->
  <span aria-hidden="true">*</span>
</label>
<div class="select__placeholder">Select...</div>
<!-- NO select__single-value — EMPTY -->
<!-- aria-describedby="react-select-question_66747918-placeholder question_66747918-error"
     ↑ placeholder ID present = EMPTY -->
<input class="select__input" style="opacity: 1;"/> <!-- opacity:1 = empty/focused -->
```

**Root cause: U+2019 curly apostrophe.** `find label "...job's location?"` with straight apostrophe does not match.

### FAILING: question_66747923 (empty — trailing newline in label)

```html
<label id="question_66747923-label" ...>
  If you are enrolled in university, what degree are you currently pursuing?
  <!-- ↑ TRAILING \n before the span (repr: 'ing?\n') -->
  <span aria-hidden="true">*</span>
</label>
<div class="select__placeholder">Select...</div>
```

**Root cause: trailing newline.** Label textContent ends with `\n`. `find label` text matching fails.

### FAILING: question_66747924 (empty — wrong expected option text)

```html
<label id="question_66747924-label" ...>
  A successful internship may lead to consideration for a full-time opportunity.
  If you were to receive a full-time offer, when would you be available to start?
</label>
<div class="select__placeholder">Select...</div>
<!-- Options: "Immediately after the internship ends"
              "Need to return to school and available upon graduation" -->
```

**Root cause: agent expected month/year dates (e.g., "December 2027") but actual options are completion-status phrases.**

---

## 2. Root Cause: Compound Option Set

Every custom question dropdown exposes **245 `[role="option"]` items** when opened — NOT just 2-6 actual answers:

```
[role="option"] "Afghanistan+93"      <- country phone code #1
[role="option"] "Åland Islands+358"   <- country phone code #2
... 240 more countries ...
[role="option"] "Yes"                 <- actual answer (position 242)
[role="option"] "No"                  <- actual answer (position 243)
```

This happens because the Greenhouse form's phone number field (intl-tel-input) renders its country selector using `[role="option"]` in the same accessibility tree scope. The `find text "Yes"` approach either times out scrolling through 245 items, or hits a timing issue. **The fix is to type a filter string before clicking**, which narrows the list to only the matching option.

Fill state is detectable via `aria-describedby`:
- **EMPTY**: includes `react-select-FIELDID-placeholder`
- **FILLED**: only `FIELDID-error`

---

## 3. Verified Live CLI Sequences

All values confirmed live via `.select__single-value` eval using Playwright CDP to Chrome:9222.

### q918 — relocate

```python
combobox = page.locator('[aria-labelledby="question_66747918-label"]')
await combobox.scroll_into_view_if_needed()
await combobox.click()
await combobox.type("I am willing", delay=50)
await page.locator('[role="option"]').filter(has_text="I am willing to relocate").first.click()
# Verified: "I am willing to relocate to this job's location."
```

agent-browser equivalent:
```bash
agent-browser click '[aria-labelledby="question_66747918-label"]'
agent-browser keyboard type "I am willing"
agent-browser find text "I am willing to relocate" click
agent-browser eval "document.querySelector('[aria-labelledby=\"question_66747918-label\"]').closest('.select-shell').querySelector('.select__single-value')?.textContent"
# => "I am willing to relocate to this job's location."
```

### q919 — sponsorship

```bash
agent-browser click '[aria-labelledby="question_66747919-label"]'
agent-browser keyboard type "No"
agent-browser find text "No" click --exact
# Verified: "No"
```

### q921 — enrolled

```bash
agent-browser click '[aria-labelledby="question_66747921-label"]'
agent-browser keyboard type "Yes"
agent-browser find text "Yes" click --exact
# Verified: "Yes"
```

### q923 — degree

```bash
agent-browser click '[aria-labelledby="question_66747923-label"]'
agent-browser keyboard type "Bachelor"
agent-browser find text "Bachelor" click
# Verified: "Bachelor's"
# Note: actual option text is "Bachelor's" with curly apostrophe U+2019
```

### q924 — full-time start

```bash
agent-browser click '[aria-labelledby="question_66747924-label"]'
agent-browser keyboard type "Need to"
agent-browser find text "Need to return" click
# Verified: "Need to return to school and available upon graduation"
# NOTE: options are NOT month/year dates. "December 2027" does NOT exist.
```

### q925 — Python/SQL

```bash
agent-browser click '[aria-labelledby="question_66747925-label"]'
agent-browser keyboard type "Yes"
agent-browser find text "Yes" click --exact
# Verified: "Yes"
```

---

## 4. Prompt-Ready Pattern for All These Fields

```python
async def fill_greenhouse_select(page, field_id: str, target_value: str, type_filter: str = None):
    """
    Fill a Greenhouse React-Select custom question dropdown.
    
    GOTCHAS:
    - Always use aria-labelledby CSS selector, never find-by-label-text (curly quotes, trailing newlines)
    - Always type a filter string first — dropdown shows 245 items (240 country codes + real options)
    - q924 options are NOT dates: "Immediately after..." or "Need to return to school..."
    - q918 option text contains curly apostrophe: "job's location" (U+2019)
    - q923 option text contains curly apostrophe: "Bachelor's" (U+2019)
    """
    combobox = page.locator(f'[aria-labelledby="{field_id}-label"]')
    await combobox.scroll_into_view_if_needed()
    await combobox.click()
    await page.wait_for_timeout(400)
    
    filter_text = type_filter or target_value[:10]
    await combobox.type(filter_text, delay=50)
    await page.wait_for_timeout(400)
    
    option = page.locator('[role="option"]').filter(has_text=target_value)
    await option.first.click()
    await page.wait_for_timeout(300)
    
    sv = await page.evaluate(f"""
        document.querySelector('[aria-labelledby="{field_id}-label"]')
            ?.closest('.select-shell')
            ?.querySelector('.select__single-value')?.textContent
    """)
    assert sv == target_value, f"Expected {target_value!r}, got {sv!r}"
    return sv
```

### Values verified in this session

| field_id | type_filter | target_value |
|---|---|---|
| question_66747918 | `"I am willing"` | `"I am willing to relocate to this job's location."` |
| question_66747919 | `"No"` | `"No"` |
| question_66747921 | `"Yes"` | `"Yes"` |
| question_66747923 | `"Bachelor"` | `"Bachelor's"` |
| question_66747924 | `"Need to"` | `"Need to return to school and available upon graduation"` |
| question_66747925 | `"Yes"` | `"Yes"` |
