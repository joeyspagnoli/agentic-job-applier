# Greenhouse React combobox interaction pattern

## The current failure

The finisher gives up on Greenhouse because `select(ref, value)` fails on React-Select comboboxes:

1. `select_option(label="United States")` fails — it's not a native `<select>`.
2. Fallback `page.get_by_role("option")` returns 0 matches — Greenhouse's dropdown uses a virtualized list that doesn't render `role=option` elements until the combobox is open, AND the combobox must be open at the moment the snapshot is taken for the refs to be valid.
3. Even if the combobox IS open and refs are captured, any subsequent interaction re-renders the form and stales those refs.

## The agent-browser two-step pattern

For any React-Select / combobox widget on Greenhouse:

```bash
# Step 1: Open the combobox by semantic label (no ref needed, survives re-renders)
agent-browser find role combobox click --name "Country"

# Step 2: Wait briefly for the listbox to render
agent-browser wait --load networkidle   # or: agent-browser wait 300

# Step 3: Click the desired option by text (no ref needed)
agent-browser find text "United States" click --exact
```

## Fields this applies to on Greenhouse

- Country (intl-tel-input country + main country combobox)
- State / Province
- "How did you hear about us?"
- "Are you legally authorized to work in the United States?" (Yes/No)
- "Will you now or in the future require visa sponsorship?" (Yes/No)
- "Are you currently enrolled in school?" (Yes/No)
- Degree pursuing (dropdown)
- Graduation date (month + year dropdowns)
- Phone country code flag selector

## Phone widget specifics

The phone widget (`intl-tel-input`) has two parts:
1. A flag-selector `div` with `class="iti__selected-flag"` — NOT a standard combobox
2. The phone number text input

Interaction sequence:
```bash
# Click the flag (CSS fallback — not a combobox role)
agent-browser click ".iti__selected-flag"

# Type country to filter the dropdown
agent-browser find placeholder "Search" type "United States"
agent-browser find text "United States (+1)" click

# Fill the phone number in the text input
agent-browser find label "Phone" fill "+1 555-123-4567"
```

If the flag selector has a stable accessible name, prefer:
```bash
agent-browser find role button click --name "selected country: United States"
```

## New tool signatures to expose to the agent

```python
async def click(
    ctx: RunContext[FinisherDeps],
    ref: str | None = None,
    label: str | None = None,
) -> str:
    """
    Click an element. Use `ref` (@eN) for buttons and simple inputs.
    Use `label` for comboboxes and dropdowns that re-render after opening
    (country, state, Yes/No questions). When `label` is given, `ref` is ignored
    and a semantic `find role combobox click --name <label>` is used.
    """

async def select_option(
    ctx: RunContext[FinisherDeps],
    label: str,
    value: str,
) -> str:
    """
    Pick a value from an already-open combobox/listbox. Calls
    `agent-browser find text <value> click --exact`. Always call
    `click(label=...)` first to open the dropdown, then this.
    Do NOT use for native <select> — use fill(ref, value) instead
    (agent-browser select works for native selects; React-Select needs this).
    """
```
