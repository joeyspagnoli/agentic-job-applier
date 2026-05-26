# agent-browser core skill — key excerpts for this refactor

Source: `agent-browser skills get core --full`

## Ref staleness rule (critical)

> Refs (`@e1`, `@e2`, ...) are assigned fresh on every snapshot. They become
> **stale the moment the page changes** — after clicks that navigate, form
> submits, dynamic re-renders, dialog opens. Always re-snapshot before your
> next ref interaction.

## Snapshot command reference

```bash
agent-browser snapshot -i -c           # interactive elements, compact (preferred for agent use)
agent-browser snapshot -i -c -s "#id"  # scoped to CSS selector
```

Output format:
```
Page: Title
URL: https://...

@e1 [heading] "..."
@e2 [form]
  @e3 [input type="text"] placeholder="First Name"
  @e4 [combobox] "Country"
  @e5 [button type="submit"] "Submit Application"
```

## Semantic locator commands (for comboboxes)

```bash
agent-browser find role combobox click --name "Country"
agent-browser find text "United States" click
agent-browser find text "United States" click --exact
agent-browser find label "Email" fill "user@test.com"
```

Rule: snapshot + `@eN` refs for most interactions. `find role/text/label` when refs are unstable (comboboxes, dynamic lists).

## Wait commands

```bash
agent-browser wait <ms>                    # dumb wait (avoid except debugging)
agent-browser wait --load networkidle      # until network idle (good after combobox interaction)
agent-browser wait --text "..."            # until text appears
agent-browser wait @e1                     # until element appears
```

## Click / fill / select

```bash
agent-browser click @e3
agent-browser fill @e3 "value"
agent-browser select @e4 "option-value"    # native <select> only
```

For React-Select / combobox dropdowns, `select` does NOT work — must use:
```bash
agent-browser find role combobox click --name "Country"   # open the dropdown
agent-browser find text "United States" click             # pick the option
```

## Screenshot (for fallback when snapshot is empty)

```bash
agent-browser screenshot /tmp/fallback.png
agent-browser screenshot --full /tmp/full.png
```

## What subprocess.run returns

- `stdout`: the text output (snapshot YAML, confirmation strings, etc.)
- `returncode`: 0 on success, non-zero on error (stale ref, element not found, etc.)
- Non-zero returncode with stderr describing the error → raise `ModelRetry` in the tool wrapper

## Connecting to existing Chrome

agent-browser uses CDP by default. If the host Chrome is already running on port 9222:
```bash
AGENT_BROWSER_CDP_URL=http://localhost:9222 agent-browser snapshot -i
```
Or configure once; the CLI reads the env var on every invocation.
