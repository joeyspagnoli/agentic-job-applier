# intl-tel-input + Country Combobox: Live Findings

**Date:** 2026-05-25  
**Page:** https://job-boards.greenhouse.io/cloudflare/jobs/7914628?gh_jid=7914628  
**Result:** Country set to "United States", phone set to "(561) 329-2705" — VERIFIED LIVE

---

## 1. Widget Anatomy

### Full container structure

Both widgets live inside a single `<fieldset class="phone-input">` with two div children:

```
<fieldset class="phone-input">
  ├── <div class="phone-input__country">          ← React-Select country picker
  │     └── <label id="country-label">Country</label>
  │         <div class="select-shell remix-css-b62m3t-container">
  │           └── <div class="select__control ...">   ← clickable trigger area
  │                 └── <div class="select__input-container">
  │                       └── <input id="country" role="combobox"
  │                               aria-expanded="false" aria-haspopup="true"
  │                               type="text" value="" ...>
  │
  └── <div class="phone-input__phone">            ← intl-tel-input phone widget
        └── <label id="phone-label">Phone</label>
            <div class="iti iti--allow-dropdown iti--show-flags iti--inline-dropdown">
              ├── <div class="iti__country-container">
              │     └── <button class="iti__selected-country"
              │             aria-label="Change country, selected United States (+1)"
              │             aria-haspopup="dialog"
              │             aria-controls="iti-0__dropdown-content">
              │           └── <div class="iti__selected-country-primary">
              │                 ├── <div class="iti__flag iti__us">   ← flag chip
              │                 └── <div class="iti__arrow">
              └── <input id="phone" type="tel"
                      class="input iti__tel-input"
                      data-intl-tel-input-id="0"
                      value="(561) 329-2705" ...>
```

### Key insight: TWO separate widgets, ONE shared React state

- **`id="country"` (React-Select combobox)** is NOT a native `<select>` and NOT intl-tel-input. It is a Greenhouse custom React-Select that renders `[FlagDiv] +dialCode` as its selected value display. Its dropdown lists countries as `"United States +1"`, `"Afghanistan +93"`, etc.
- **`id="phone"` (intl-tel-input `<input>`)** is the actual telephone input. The `iti__selected-country` button's flag/label is updated automatically when the React-Select above changes, via shared React component state.

### Where does the chosen country code actually live after selection?

- **NOT** in `input#country.value` — that stays `""` after selection (React-Select stores it internally)
- **NOT** in a hidden `<input>` — no hidden input present
- **NOT** via `window.intlTelInputGlobals` — that global does not exist on this page
- **YES** in the `iti__flag` div's CSS class: after selecting US → class becomes `"iti__flag iti__us"`
- **YES** readable via the button's `aria-label`: `"Change country, selected United States (+1)"`

---

## 2. Working CLI Sequence: Set Country to "United States"

**Winning approach: click the React-Select combobox ref → dropdown opens → click the "United States +1" option ref.**

```bash
# Step 1: Snapshot to get the Country combobox ref
agent-browser snapshot -i
# Find: combobox "Country" [expanded=false, required, ref=eXX]

# Step 2: Click to open the dropdown  
agent-browser click @eXX
# The listbox appears immediately — no wait needed

# Step 3: Re-snapshot to see options
agent-browser snapshot -i
# Find: option "United States +1" [ref=eZZ]
# NOTE: "United States +1" is always the FIRST option in the listbox

# Step 4: Click the option
agent-browser click @eZZ
```

**What does NOT work:**
- `agent-browser fill @eXX "United States"` — sets DOM .value but React ignores it; no dropdown, no state update
- `agent-browser type @eXX "United States"` — same; dropdown does not appear
- `agent-browser find role combobox click --name "Country"` — returns "element not found" on this layout
- `window.intlTelInputGlobals.getInstance(el).setCountry('us')` — `intlTelInputGlobals` is undefined on this page
- `eval` dispatching raw mousedown/click events — caused agent-browser daemon lockup (exit 143)

**Verification after selection:**
```bash
agent-browser eval "JSON.stringify({flagClass: document.querySelector('.iti__flag').className, btnLabel: document.querySelector('.iti__selected-country').getAttribute('aria-label')})"
# Expected: {"flagClass":"iti__flag iti__us","btnLabel":"Change country, selected United States (+1)"}
```

---

## 3. Working CLI Sequence: Fill Phone to "5613292705"

After country is set, the phone field is a plain `type="tel"` input. Standard `fill` works. intl-tel-input auto-formats the input on blur.

```bash
# Snapshot to get the Phone textbox ref (may be same snapshot as above)
agent-browser snapshot -i
# Find: textbox "Phone" [required, ref=eAA]

# Fill the phone digits
agent-browser fill @eAA "5613292705"
# intl-tel-input formats this to "(561) 329-2705" in the DOM
```

**Verification:**
```bash
agent-browser eval "document.getElementById('phone').value"
# Returns: "(561) 329-2705"
```

---

## 4. Verifier JS One-Liners

**Country code (returns 2-letter ISO, uppercased):**
```javascript
document.querySelector('.iti__flag').className.split(' ').find(c => c.startsWith('iti__') && c !== 'iti__flag').replace('iti__', '').toUpperCase()
// Returns: "US"
```

**Phone value:**
```javascript
document.getElementById('phone').value
// Returns: "(561) 329-2705"
```

**Combined verifier (one eval call):**
```javascript
JSON.stringify({
  countryCode: document.querySelector('.iti__flag').className.split(' ').find(c => c.startsWith('iti__') && c !== 'iti__flag').replace('iti__', '').toUpperCase(),
  phoneValue: document.getElementById('phone').value
})
// Returns: {"countryCode":"US","phoneValue":"(561) 329-2705"}
```

---

## 5. Prompt-Ready Code Block

Substitute `<COUNTRY_REF>`, `<OPTION_REF>`, `<PHONE_REF>` with snapshot refs. Replace `<COUNTRY_OPTION_TEXT>` and `<PHONE_DIGITS>` as noted.

```bash
# ── COUNTRY + PHONE fill sequence ──────────────────────────────────────────

# 1. Snapshot — identify Country combobox ref
agent-browser snapshot -i
# → combobox "Country" [expanded=false, required, ref=<COUNTRY_REF>]

# 2. Open the Country dropdown
agent-browser click @<COUNTRY_REF>

# 3. Re-snapshot — identify the target option ref
agent-browser snapshot -i
# → option "<COUNTRY_OPTION_TEXT>" [ref=<OPTION_REF>]
# For United States: option "United States +1" [ref=<OPTION_REF>]

# 4. Select the country
agent-browser click @<OPTION_REF>

# 5. Verify country set correctly
agent-browser eval "JSON.stringify({countryCode: document.querySelector('.iti__flag').className.split(' ').find(c=>c.startsWith('iti__')&&c!=='iti__flag').replace('iti__','').toUpperCase(), btnLabel: document.querySelector('.iti__selected-country').getAttribute('aria-label')})"
# Expected: {"countryCode":"US","btnLabel":"Change country, selected United States (+1)"}

# 6. Snapshot — identify Phone textbox ref
agent-browser snapshot -i
# → textbox "Phone" [required, ref=<PHONE_REF>]

# 7. Fill phone digits
agent-browser fill @<PHONE_REF> "<PHONE_DIGITS>"
# Example: agent-browser fill @<PHONE_REF> "5613292705"

# 8. Verify phone value
agent-browser eval "document.getElementById('phone').value"
# Expected: "(561) 329-2705" (intl-tel-input formats the raw digits)
```

---

## Session Notes

- **intl-tel-input version:** v22.x (identified by `iti__country-container`, `iti__selected-country`, `iti--inline-dropdown` class names)
- **React-Select controls iti:** The app wires React-Select's `onChange` callback to update the intl-tel-input country. They share React state — you only need to drive the React-Select; the iti widget follows.
- **Refs are ephemeral:** `@eXX` refs change on every snapshot. Always re-snapshot after a click that changes the DOM.
- **"United States +1" is the first option:** The dropdown pre-sorts it first (confirmed live on this job board).
- **Phone auto-formats:** intl-tel-input turns `5613292705` → `(561) 329-2705`. The form submission sends the formatted string.
- **DO NOT use `fill` to set the country combobox.** It looks like it works (snapshot shows the value) but React state is not updated and the iti widget stays on the globe icon with no country.
