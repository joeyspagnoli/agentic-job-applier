# Greenhouse Widget Anatomy — Cloudflare ML Intern Form

Source files: `/tmp/run17-dom.html` (175 863 bytes, captured at submit time, run 17).

---

## 1. Per-Field HTML Anatomy

All seven `question_NNNNN` fields plus `country` and `candidate-location` use the **same** Greenhouse React-Select wrapper. The `phone` field (the number itself) is a plain `<input type="tel">`. The phone country-code picker is a **separate** intl-tel-input widget, not React-Select.

### question_66747918 — "Willing to relocate?"

```html
<div class="field-wrapper">
  <div class="select">
    <div class="select__container select__container--outside-label">
      <label id="question_66747918-label" for="question_66747918"
             class="label select__label select__label--outside-label">
        Do you currently live or are you willing to relocate to the job's location?
        <span aria-hidden="true">*</span>
      </label>
      <div class="select-shell remix-css-b62m3t-container">
        <span id="react-select-question_66747918-live-region" class="remix-css-7pg0cj-a11yText"></span>
        <span aria-live="polite" aria-atomic="false" aria-relevant="additions text"
              role="log" class="remix-css-7pg0cj-a11yText"></span>
        <div>
          <div class="select__control--outside-label select__control remix-css-13cymwt-control">
            <div class="select__value-container remix-css-hlgwow">
              <!-- placeholder shown when empty -->
              <div class="select__placeholder remix-css-1jqq78o-placeholder"
                   id="react-select-question_66747918-placeholder">Select...</div>
              <div class="select__input-container remix-css-19bb58m" data-value="">
                <input class="select__input"
                       style="color: inherit; background: 0px center; opacity: 1; ..."
                       id="question_66747918"
                       type="text"
                       role="combobox"
                       aria-autocomplete="list"
                       aria-expanded="false"
                       aria-haspopup="true"
                       aria-labelledby="question_66747918-label"
                       aria-required="true"
                       aria-errormessage="question_66747918-error"
                       aria-invalid="false"
                       aria-activedescendant=""
                       aria-describedby="react-select-question_66747918-placeholder question_66747918-error"
                       enterkeyhint="done"
                       value="">
              </div>
            </div>
            <div class="select__indicators--outside-label select__indicators remix-css-1wy0on6">
              <button type="button" class="icon-button icon-button--sm"
                      aria-label="Toggle flyout" tabindex="-1">
                <!-- chevron-down SVG -->
              </button>
            </div>
          </div>
        </div>
        <!-- HIDDEN REQUIRED-ENFORCEMENT INPUT -->
        <input required="" tabindex="-1" aria-hidden="true"
               class="remix-css-1a0ro4n-requiredInput" value="" style="">
      </div>
    </div>
  </div>
</div>
```

**Summary:** React-Select Pattern A, empty at capture. `<input type="text" role="combobox" aria-haspopup="true">`. Trigger: `<button aria-label="Toggle flyout">`. Hidden sibling `remix-css-1a0ro4n-requiredInput` with `value=""`.

---

### question_66747919 — "Immigration sponsorship?" (SELECTED — value = "No")

```html
<div class="select__value-container select__value-container--has-value remix-css-hlgwow">
  <!-- rendered selected label -->
  <div class="select__single-value remix-css-1dimb5e-singleValue">No</div>
  <div class="select__input-container remix-css-19bb58m" data-value="">
    <input class="select__input"
           style="... opacity: 0; ..."
           id="question_66747919"
           type="text"
           role="combobox"
           aria-expanded="false"
           aria-haspopup="true"
           aria-labelledby="question_66747919-label"
           aria-required="true"
           value="">
  </div>
</div>
<!-- Clear button — appears INSTEAD of Toggle flyout when value is set -->
<div aria-hidden="false">
  <button type="button" class="icon-button icon-button--sm"
          aria-label="Clear selections" data-testid="clear-selection">
  </button>
</div>
```

**Summary:** React-Select Pattern A, value committed ("No" shown in `.select__single-value`). Input has `opacity: 0`. Toggle flyout replaced by "Clear selections" button. No `remix-css-1a0ro4n-requiredInput` sibling (not required-enforced in same container for this field).

---

### question_66747921 — "Currently enrolled?"

Same structure as 66747918 (empty). Input `opacity: 1`, placeholder "Select...", Toggle flyout button present.

**Summary:** React-Select Pattern A, empty at capture. Input id `question_66747921`, role=`combobox`, aria-haspopup=`true`.

---

### question_66747922 — "Expected graduation date?"

Same structure as 66747918 (empty). Placeholder "Select...", Toggle flyout button present.

**Summary:** React-Select Pattern A, empty at capture. Input id `question_66747922`.

---

### question_66747923 — "Degree pursuing?"

Same structure as 66747918 (empty). Placeholder "Select...", Toggle flyout button present.

**Summary:** React-Select Pattern A, empty at capture. Input id `question_66747923`.

---

### question_66747924 — "Full-time start date?"

Same structure as 66747918 (empty). Placeholder "Select...", Toggle flyout button present.

**Summary:** React-Select Pattern A, empty at capture. Input id `question_66747924`.

---

### question_66747925 — "Python/SQL proficiency?"

Same structure but `aria-required="false"` (the only non-required react-select on the form). Placeholder "Select...", Toggle flyout button present.

**Summary:** React-Select Pattern A, empty, NOT required. Input id `question_66747925`.

---

### `country` — Phone country code (React-Select, pre-selected US +1)

```html
<fieldset class="phone-input">
  <legend class="visually-hidden">Phone</legend>
  <div class="phone-input__country">
    <div class="select">
      <div class="select__container select__container--outside-label">
        <label id="country-label" for="country">Country<span aria-hidden="true">*</span></label>
        <div class="select-shell remix-css-b62m3t-container">
          <div class="select__value-container select__value-container--has-value remix-css-hlgwow">
            <div class="select__single-value remix-css-1dimb5e-singleValue">
              <div class="iti__flag iti__us"></div><span>+1</span>
            </div>
            <input id="country" type="text" role="combobox"
                   aria-haspopup="true" aria-labelledby="country-label"
                   aria-required="true" value=""
                   style="opacity: 1">
          </div>
          <!-- Toggle flyout button IS present even though --has-value -->
          <button type="button" aria-label="Toggle flyout" tabindex="-1">...</button>
        </div>
      </div>
    </div>
  </div>
```

**Summary:** React-Select Pattern A, already shows US +1 flag (has `--has-value` + `select__single-value`). Unusual: input stays `opacity: 1` and Toggle flyout button is NOT replaced by Clear — Greenhouse keeps the flyout always-visible for this field so users can change country. Accessible name: `"Country"` from label `country-label`.

---

### `phone` — Phone number text field (plain input)

```html
<div class="iti iti--allow-dropdown iti--show-flags iti--inline-dropdown">
  <div class="iti__country-container" style="left: 0px;">
    <!-- intl-tel-input decorative button — PRE-SET to US, NOT a Greenhouse form field -->
    <button type="button" class="iti__selected-country"
            aria-expanded="false"
            aria-label="Change country, selected United States (+1)"
            aria-haspopup="dialog"
            aria-controls="iti-0__dropdown-content"
            title="United States">
      <div class="iti__selected-country-primary">
        <div class="iti__flag iti__us"></div>
        <div class="iti__arrow" aria-hidden="true"></div>
      </div>
    </button>
    <!-- dialog listbox for intl-tel-input, hidden by default -->
    <div id="iti-0__dropdown-content" class="iti__dropdown-content iti__hide" role="dialog" aria-modal="true">
      <input id="iti-0__search-input" type="search" role="combobox"
             aria-controls="iti-0__country-listbox" aria-label="Search">
      <ul id="iti-0__country-listbox" role="listbox" aria-label="List of countries">
        <li role="option" data-dial-code="93" data-country-code="af">Afghanistan +93</li>
        <!-- 244 countries total -->
      </ul>
    </div>
  </div>
  <!-- THE ACTUAL PHONE NUMBER INPUT -->
  <input id="phone" type="tel" class="input iti__tel-input"
         aria-label="Phone" aria-required="true"
         value="" data-intl-tel-input-id="0">
</div>
```

**Summary:** Two sub-components. (1) `<button class="iti__selected-country">` — intl-tel-input flag button, pre-set to US, opens a `role="dialog"` country listbox. The finisher does NOT need to interact with this. (2) `<input id="phone" type="tel" aria-label="Phone">` — plain text field, just type the number.

---

### `candidate-location` — Location (City) async typeahead

```html
<div class="select__container select__container--outside-label">
  <label id="candidate-location-label" for="candidate-location">
    Location (City)<span aria-hidden="true">*</span>
  </label>
  <div class="select-shell remix-css-b62m3t-container">
    <div class="select__control--outside-label select__control remix-css-13cymwt-control">
      <div class="select__value-container remix-css-hlgwow">
        <!-- empty placeholder, no text -->
        <div class="select__placeholder remix-css-1jqq78o-placeholder"
             id="react-select-candidate-location-placeholder"></div>
        <input id="candidate-location" type="text" role="combobox"
               aria-haspopup="true" aria-labelledby="candidate-location-label"
               aria-required="true" value=""
               style="opacity: 1"
               data-dashlane-classification="address,city">
      </div>
      <!-- indicators div is EMPTY — no Toggle flyout, no Clear button -->
      <div class="select__indicators--outside-label select__indicators remix-css-1wy0on6"></div>
    </div>
    <input required="" tabindex="-1" aria-hidden="true"
           class="remix-css-1a0ro4n-requiredInput" value="">
  </div>
</div>
<button type="button" class="btn--tertiary">Locate me</button>
```

**Summary:** React-Select async typeahead. No Toggle flyout button, no Clear button, no static options. The finisher MUST type city text to trigger async option fetch, then pick from the portaled list. Accessible name: `"Location (City)"`.

---

## 2. Pattern Grouping

### Pattern A — Greenhouse React-Select Searchable Combobox (static options)

**Fields:** `question_66747918`, `question_66747919`, `question_66747921`, `question_66747922`, `question_66747923`, `question_66747924`, `question_66747925`, `country`

Built on react-select (Greenhouse "remix" variant). Fixed option list that is **not rendered in the DOM when closed** — options appear in a portaled `<div>` appended to `<body>` only when the dropdown is open.

Key signals:
- `<input type="text" role="combobox" aria-haspopup="true" aria-autocomplete="list">`
- Open trigger: `<button aria-label="Toggle flyout" tabindex="-1">` (chevron-down SVG)
- When value set: `.select__value-container--has-value` class + `.select__single-value` div + input `opacity: 0`
- After value set: trigger swaps to `<button aria-label="Clear selections" data-testid="clear-selection">`
- Required enforcement: sibling `<input class="remix-css-1a0ro4n-requiredInput" aria-hidden="true">` — value managed by React state, not settable directly
- Accessible name: via `aria-labelledby` → `<label id="{field-id}-label">` (NOT via `aria-label` on the input)

### Pattern B — React-Select Async Typeahead (no static options)

**Field:** `candidate-location`

Same React-Select shell but indicators div is empty (no flyout button, no clear button). Options fetched async as the user types (Google Places-style). The finisher must type text and then pick from the dynamically appearing portaled list.

### Pattern C — intl-tel-input Phone Country Button (pre-set, skip)

**Field:** `phone` section — `<button class="iti__selected-country">`

Non-React-Select widget, pre-set to United States. Opens a `role="dialog"` with `role="listbox"`. The finisher does NOT need to touch this. The Greenhouse-controlled country code selector is the React-Select `id="country"` widget. The phone number itself is `<input id="phone" type="tel">`.

---

## 3. Click Target Identification

### Pattern A — React-Select

| Step | DOM element | Role / attribute | Notes |
|------|-------------|------------------|-------|
| **Open dropdown** | `<input id="question_NNNNN">` | `role="combobox"` | Click or focus to open |
| **OR open via button** | `<button aria-label="Toggle flyout">` | `button` | tabindex=-1 so Tab won't reach it; click directly |
| **Pick option** | `<div role="option">` in portaled menu | `option` | Portal is a `<div>` appended to `<body>` NOT inside the form |
| **Verify selection** | `.select__single-value` inside the field's `.select-shell` | — | Text content equals the selected label |
| **Clear / change** | `<button aria-label="Clear selections" data-testid="clear-selection">` | `button` | Only present after value committed |

Option list structure when open (portaled to `<body>`):
```html
<div class="select__menu remix-css-...">
  <div class="select__menu-list">
    <div class="select__option" role="option"
         id="react-select-question_66747918-option-0">Yes</div>
    <div class="select__option" role="option"
         id="react-select-question_66747918-option-1">No</div>
  </div>
</div>
```
Option element IDs follow `react-select-{field-id}-option-{index}`. `aria-activedescendant` on the combobox input updates as you arrow through the list.

### Pattern B — Async Typeahead (candidate-location)

| Step | DOM element | Role | Notes |
|------|-------------|------|-------|
| **Open / populate** | `<input id="candidate-location" role="combobox">` | `combobox` | No flyout button; must type to trigger options |
| **Pick option** | `<div role="option">` in portal | `option` | Appears after async debounce (~300ms) |

### Pattern C — intl-tel-input (no action needed)

Pre-selected to United States. Skip.

---

## 4. Hidden-Value Mechanism

**React-Select (Patterns A and B):**

The chosen value is stored **purely in React component state**. There is no hidden input reliably settable or readable via DOM:

- The `<input type="text" role="combobox">` always has `value=""` (React-Select types into it during search, then clears on selection).
- The `<input class="remix-css-1a0ro4n-requiredInput" aria-hidden="true">` has `value=""` in the DOM snapshot even for the field where "No" IS selected (question_66747919). Its value is synchronized by React at form-submit time — reading it mid-session gives false negatives.
- The **only reliable DOM indicator** of a committed value is: `.select__value-container--has-value` class present AND `.select__single-value` div containing the expected text.

**Verification:** after clicking an option, assert that the `.select__single-value` element exists inside the field's `.select-shell` and its text matches the intended answer. Do NOT rely on `input.value` or `.remix-css-1a0ro4n-requiredInput.value`.

**Phone field:** plain DOM input. Value is in `input.value`. Verify directly.

---

## 5. Recommendation for the Finisher Prompt

### Why current attempts fail

`find role combobox click --name "Do you currently..."` fails for several compounding reasons:

1. **Accessible name mismatch**: The combobox's accessible name is computed from `aria-labelledby` pointing to a label whose text includes `<span aria-hidden="true">*</span>`. Depending on how the agent-browser resolves aria-hidden content, the computed name is either `"Do you currently live or are you willing to relocate to the job's location?"` (without asterisk) or with it. Either way, searching by partial name on a page with 13+ comboboxes is fragile.

2. **Dropdown portal not in DOM at search time**: The agent-browser cannot `find role option name="Yes"` until after the dropdown has been opened and the portal mounted into `<body>`. The click on the combobox must precede the option search.

3. **Value verification against wrong attribute**: The input's `value` attribute is always `""`. Checking it after clicking an option returns empty regardless of success.

### Correct interaction sequence — Pattern A fields

```
# Step 1: click the combobox input by CSS id (most reliable)
click css=#question_66747918

# Step 2: wait for portal to mount — poll for any role=option to appear
wait for role=option

# Step 3: click the option by visible text
click role=option name="Yes"

# Step 4: verify selection committed
assert text in css=.select__single-value == "Yes"
```

Alternative for step 1: click the Toggle flyout button scoped to the field container:
```
click css=#react-select-question_66747918-live-region ~ div .icon-button[aria-label="Toggle flyout"]
```

### Correct interaction sequence — `candidate-location` (Pattern B)

```
click css=#candidate-location
type "San Francisco"
wait for role=option
click role=option name="San Francisco, CA, USA"
assert text in css=.select__single-value contains "San Francisco"
```

### Correct interaction — `phone` (Pattern C — plain input)

```
fill css=#phone value="4155551234"
# or:
click css=#phone
type "4155551234"
```

Do NOT click `button.iti__selected-country` — it is decorative and pre-set to US.

### `country` field note

The `country` React-Select (phone country code) shows US +1 already selected (`select__value-container--has-value` is set). If US is the target, skip this field. If a different country is needed, click the Toggle flyout (it remains present for this field even when has-value), wait for options, and click the desired country by option text. Accessible name is `"Country"`.

---

*Captured from `/tmp/run17-dom.html`, form action `/cloudflare/jobs/7914628?gh_jid=7914628&utm_source=Simplify`.*
