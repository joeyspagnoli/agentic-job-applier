# CLI Audit: agent-browser vs apply-finisher prompt gaps

**Date:** 2026-05-25  
**Scope:** Read-only audit. Sources: `agent-browser --help`, per-subcommand `--help`, `skills get core`, `skills get core --full`.

---

## 1. Complete subcommand inventory

### Core interaction
| Command | Summary |
|---|---|
| `open <url>` | Navigate to URL (aliases: goto, navigate) |
| `click <sel>` | Click element by ref or CSS selector |
| `dblclick <sel>` | Double-click element |
| `type <sel> <text>` | Type WITHOUT clearing first (appends) |
| `fill <sel> <text>` | Clear then type into element |
| `press <key>` | Press key at current focus (Enter, Tab, Control+a, ArrowDown, etc.) |
| `keyboard type <text>` | Type char-by-char with real key events, NO selector |
| `keyboard inserttext <text>` | Insert text WITHOUT firing key events (like paste), NO selector |
| `hover <sel>` | Hover element |
| `focus <sel>` | Focus element |
| `check <sel>` | Check checkbox |
| `uncheck <sel>` | Uncheck checkbox |
| `select <sel> <val...>` | Select native `<select>` option(s) |
| `drag <src> <dst>` | Drag and drop |
| `upload <sel> <files...>` | Upload files |
| `download <sel> <path>` | Download file by clicking |
| `scroll <dir> [px]` | Scroll page (up/down/left/right) |
| `scrollintoview <sel>` | Scroll element into view |
| `keydown <key>` | Hold key down — only in `references/commands.md` (--full), NOT in --help |
| `keyup <key>` | Release held key — only in `references/commands.md` (--full), NOT in --help |

### Reading / introspection
| Command | Summary |
|---|---|
| `snapshot [-i] [-c] [-d N] [-s sel]` | Accessibility tree with @refs |
| `get text <sel>` | Get visible text of element |
| `get html <sel>` | Get innerHTML |
| `get value <sel>` | Get input element's current value |
| `get attr <sel> <name>` | Get arbitrary attribute |
| `get title` | Get page title |
| `get url` | Get current URL |
| `get count <sel>` | Count matching elements |
| `get box <sel>` | Bounding box (x, y, width, height) |
| `get styles <sel>` | Computed CSS styles |
| `get cdp-url` | Chrome DevTools Protocol WebSocket URL |
| `is visible <sel>` | Returns true/false |
| `is enabled <sel>` | Returns true/false |
| `is checked <sel>` | Returns true/false |

### Semantic locators (find)
| Command | Summary |
|---|---|
| `find role <role> <action> [--name N] [--exact]` | Find by ARIA role |
| `find text <text> <action> [--exact]` | Find by text content |
| `find label <label> <action> [--exact]` | Find by associated label |
| `find placeholder <text> <action>` | Find by placeholder |
| `find alt <text> <action>` | Find by alt text |
| `find title <text> <action>` | Find by title attribute |
| `find testid <id> <action>` | Find by data-testid |
| `find first <sel> <action>` | First matching CSS selector |
| `find last <sel> <action>` | Last matching CSS selector |
| `find nth <n> <sel> <action>` | Nth matching CSS selector (0-based) |

### Waiting
| Command | Summary |
|---|---|
| `wait <sel>` | Wait for element to appear |
| `wait <ms>` | Dumb wait in milliseconds |
| `wait --text <text>` | Wait for text to appear on page |
| `wait --url <pattern>` | Wait for URL to match glob |
| `wait --load networkidle|domcontentloaded|load` | Wait for load state |
| `wait --fn <expr>` | Wait for JS expression to be truthy |
| `wait --download [path]` | Wait for a download to complete |
| `wait <sel> --state hidden` | Wait for element to become hidden |
| `wait <sel> --state detached` | Wait for element to be removed from DOM |

### JavaScript execution
| Command | Summary |
|---|---|
| `eval <js>` | Run JS, return result (inline quotes break easily) |
| `eval -b <base64>` | Run base64-encoded JS (avoids shell escaping entirely) |
| `eval --stdin` | Read JS script from stdin (heredoc-safe for multiline/complex) |

### Mouse (low-level, no selector)
| Command | Summary |
|---|---|
| `mouse move <x> <y>` | Move mouse to coordinates |
| `mouse down [left|right|middle]` | Press mouse button |
| `mouse up [left|right|middle]` | Release mouse button |
| `mouse wheel <dy> [dx]` | Scroll mouse wheel |

### React (requires `open --enable react-devtools` at launch)
| Command | Summary |
|---|---|
| `react tree` | Full React component tree with depth/id/parent/name |
| `react inspect <fiberId>` | Inspect one fiber: props, hooks, state, source location |
| `react renders start` | Record re-renders via onCommitFiberRoot |
| `react renders stop [--json]` | Stop and print render profile |
| `react suspense [--only-dynamic] [--json]` | Walk Suspense boundaries |

### Diff
| Command | Summary |
|---|---|
| `diff snapshot [--baseline <f>]` | Compare current snapshot to last (or saved) snapshot |
| `diff screenshot --baseline <f>` | Pixel diff against baseline image |
| `diff url <u1> <u2>` | Compare two pages by snapshot (optionally screenshot) |

### Network
| Command | Summary |
|---|---|
| `network route <url> [--abort|--body JSON] [--resource-type csv]` | Intercept/mock/block requests |
| `network unroute [url]` | Remove route interceptions |
| `network requests [--clear] [--filter pattern]` | Inspect captured requests |
| `network har start|stop [path]` | Record/stop HAR traffic capture |

### Frames
| Command | Summary |
|---|---|
| `frame <sel|@ref>` | Switch context into an iframe |
| `frame main` | Return to main frame |

### Tabs / windows
| Command | Summary |
|---|---|
| `tab [new|list|close|<id>|<label>]` | Manage tabs with stable IDs (t1, t2) or labels |
| `tab new --label <name> [url]` | Open tab with a memorable label |
| `window new` | Open a new window |

### Dialogs
| Command | Summary |
|---|---|
| `dialog accept [text]` | Accept dialog |
| `dialog dismiss` | Dismiss/cancel dialog |
| `dialog status` | Check if a dialog is currently open |

### Debug
| Command | Summary |
|---|---|
| `console [--clear]` | View/clear browser console logs |
| `errors [--clear]` | View/clear page JS errors |
| `highlight <sel>` | Highlight element visually |
| `inspect` | Open Chrome DevTools for active page |
| `screenshot [--annotate]` | Screenshot; `--annotate` adds [N] labels matching @eN refs |
| `trace start|stop [path]` | Record Chrome DevTools trace |
| `profiler start|stop [path]` | Record Chrome DevTools profile |
| `record start|stop <path>` | WebM video recording |
| `clipboard read|write|copy|paste` | Read/write system clipboard |

### Batch
| Command | Summary |
|---|---|
| `batch [--bail] ["cmd" ...]` | Execute multiple commands from args or stdin |

### Misc not applicable to form-filling
`open` (navigation — forbidden for finisher), `back`, `forward`, `reload`, `pushstate`, `auth`, `state`, `cookies`, `storage`, `stream`, `chat`, `vitals`, `set device`, `set geo`, `set offline`, `profiles`, `doctor`.

---

## 2. Commands NOT currently in the finisher prompt

The finisher's cheat sheet explicitly teaches: `snapshot`, `fill`, `click`, `find label`, `find text`, `find role`, `eval` (inline), `press`, `focus`, `select`, `check`/`uncheck`, `wait` (limited patterns), `scrollintoview`, `upload`, `screenshot`.

### HIGH relevance — directly helps the failing widget types

| Command | In prompt? | Impact |
|---|---|---|
| `keyboard inserttext <text>` | **NO** | Inserts text without key events (paste path). Critical for intl-tel-input phone digit input whose per-keystroke formatter strips characters on rapid programmatic input. |
| `wait --fn "<js expr>"` | **NO** | JS-condition gate. The correct primitive for async typeaheads: exits as soon as `ul[role=listbox]` has children, rather than guessing a fixed timeout. |
| `wait <sel> --state hidden` / `--state detached` | **NO** | Waits for a loading spinner to disappear before clicking listbox options — prevents clicking on a covered/stale portal. |
| `find role option click --name "<text>"` | **NO** | Targets only `role=option` nodes (always in the listbox portal), not the input preview. Prevents the "click the input instead of the option" race condition when option text appears in multiple DOM locations. |
| `type <sel> <text>` (no-clear) | **NO** | Appends to an existing value without clearing. For async typeaheads where clearing triggers a reset handler that clears the listbox before results return. |
| `eval -b <base64>` / `eval --stdin` | **NO** | Correct approach for multiline JS or JS with nested quotes. The prompt only teaches inline `eval "..."` which breaks when React-Select traversal code contains single quotes, backticks, or `\"` sequences. |
| `get value <sel>` | **NO** | Simpler alternative to `eval "document.querySelector('#x').value"` for verifying `<input type="tel">` after filling. No shell escaping needed. |
| `is visible <sel>` | **NO** | Guards portaled-dropdown option clicks: confirm the listbox `div` is actually visible before `find text`. |
| `mouse move <x> <y>` + `mouse down` + `mouse up` | **NO** | Escape hatch for intl-tel-input's flag/country button when `click` doesn't open it (touch-action CSS override). Low-level mouse events penetrate this. |
| `keydown <key>` / `keyup <key>` | **NO** | Only documented in `references/commands.md` (--full), not in `--help` at all. Needed for modifier-key combos in date-pickers (hold Shift while clicking a calendar cell for range selection). |
| `dblclick <sel>` | **NO** | Some calendar-cell date-pickers require double-click to commit a date selection. |
| `is checked <sel>` | **NO** | Programmatic radio/checkbox verification without relying on snapshot's `[checked]` attribute representation. |

### MEDIUM relevance — debugging and robustness

| Command | In prompt? | Impact |
|---|---|---|
| `console [--clear]` | **NO** | React-Select and intl-tel-input emit JS warnings when programmatic actions fail. Cheap signal for why a pick silently failed. |
| `errors [--clear]` | **NO** | Catches JS exceptions thrown by widget validation code. |
| `get html <sel>` | **NO** | Read portaled `ul[role=listbox]` innerHTML to see all available options when `find text` fails to match. |
| `get count <sel>` | **NO** | Confirm `ul[role=listbox] li[role=option]` has at least 1 item before clicking, avoiding stale-listbox bug. |
| `get box <sel>` | **NO** | Get pixel coordinates for `mouse move` fallback. |
| `screenshot --annotate` | **NO** | Labeled screenshot maps [N] to @eN — useful for debugging confusing snapshots. |
| `network requests [--filter pattern]` | **NO** | Confirm async typeahead API request fired and response returned before attempting option click. |
| `diff snapshot` | **NO** | After a combobox pick, shows exactly which nodes changed without re-reading the full tree. |
| `react tree` + `react inspect <id>` | **NO** | Read React-Select or intl-tel-input fiber state/props directly. Requires `--enable react-devtools` at launch (not currently set). |

---

## 3. Specialized commands for the four problem widget patterns

### intl-tel-input (country flag + phone digits)

The country flag dropdown IS a React-Select combobox and Pattern A/B applies. The issue is the PHONE DIGIT `<input type="tel">`. Its `input` event listener reformats digits on every keystroke. `fill` can trigger the formatter to strip characters if they arrive faster than the widget expects.

Missing primitives:

```
# PREFERRED: single paste-like insertion, bypasses per-keystroke formatter
agent_browser(["focus", "#phone"])
agent_browser(["keyboard", "inserttext", "5551234567"])
# Verify:
agent_browser(["get", "value", "#phone"])   # simpler than eval

# FALLBACK: if inserttext doesn't trigger onChange, manually dispatch:
agent_browser(["eval", "var el=document.querySelector('#phone'); el.value='5551234567'; el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true}))"])

# FALLBACK for flag button not responding to click:
# 1. Get bounding box: agent_browser(["get", "box", ".iti__flag-button"])
# 2. agent_browser(["mouse", "move", "<cx>", "<cy>"])
# 3. agent_browser(["mouse", "down"])
# 4. agent_browser(["mouse", "up"])
```

### Async typeahead (location / city field)

```
# CURRENT (flawed — 200ms is a guess):
agent_browser(["fill", "#candidate-location", "San Francisco"])
agent_browser(["wait", "200"])
agent_browser(["find", "text", "San Francisco, CA", "click", "--exact"])

# CORRECT:
agent_browser(["fill", "#candidate-location", "San Francisco"])
agent_browser(["wait", "--fn",
  "!!document.querySelector('ul[role=listbox]') && document.querySelector('ul[role=listbox]').children.length > 0",
  "--timeout", "5000"])
# Prefer role=option over text for portal disambiguation:
agent_browser(["find", "role", "option", "click", "--name", "San Francisco, CA, USA"])
# Fallback if API returned nothing:
agent_browser(["network", "requests", "--filter", "location"])
```

### Date-pickers (not covered in prompt at all)

```
# Pattern D-1: text input date picker
agent_browser(["fill", "#date-input", "05/25/2026"])
agent_browser(["press", "Tab"])   # commits value

# Pattern D-2: calendar grid (single-click or double-click)
agent_browser(["find", "role", "gridcell", "click", "--name", "25"])  # single
agent_browser(["dblclick", "@e42"])                                    # if single-click doesn't commit

# Pattern D-3: spinner (month/day/year separate fields)
agent_browser(["find", "role", "spinbutton", "click", "--name", "Month"])
agent_browser(["press", "ArrowUp"])   # increment
```

### Portaled dropdowns — preventing input-preview collision

When the option text appears both in the input's current value preview AND in the portal listbox, `find text "Yes" click --exact` can match the wrong node:

```
# CURRENT (can match input preview):
agent_browser(["find", "text", "Yes", "click", "--exact"])

# BETTER (scoped to role=option, which only appears in the portal):
agent_browser(["find", "role", "option", "click", "--name", "Yes"])

# With visibility guard before clicking:
agent_browser(["is", "visible", "ul[role=listbox]"])   # check portal rendered
agent_browser(["find", "role", "option", "click", "--name", "Yes"])
```

---

## 4. Three concrete prompt-addition suggestions

### Suggestion A — `keyboard inserttext` for intl-tel-input phone digits

**Command:** `keyboard inserttext`  
**Widget:** intl-tel-input `<input type="tel">`, and any input whose per-keystroke event handler reformats/strips characters.  
**Exact example:**
```
agent_browser(["focus", "#phone"])
agent_browser(["keyboard", "inserttext", "5551234567"])
agent_browser(["get", "value", "#phone"])   # verify non-empty
```
**Why it helps:** `keyboard inserttext` sends a single Input.insertText CDP command, simulating a paste rather than per-keystroke typing. intl-tel-input processes paste differently (runs full-string formatter once) vs. keydown (validates each char individually and can strip on rapid input). This also demonstrates `get value` as a simpler verify primitive than the current inline `eval "document.querySelector(...).value"`.

---

### Suggestion B — `wait --fn` + `find role option` for async location typeahead

**Commands:** `wait --fn "<expr>"` and `find role option click --name`  
**Widget:** Any async typeahead (Greenhouse location/city field, Lever company-name field, etc.)  
**Exact example:**
```
agent_browser(["fill", "#candidate-location", "San Francisco"])
agent_browser(["wait", "--fn",
  "!!document.querySelector('ul[role=listbox]') && document.querySelector('ul[role=listbox]').children.length > 0",
  "--timeout", "5000"])
agent_browser(["find", "role", "option", "click", "--name", "San Francisco, CA, USA"])
```
**Why it helps:** `wait --fn` exits the moment the listbox is populated rather than guessing a fixed millisecond sleep — faster on fast connections, correct on slow ones. `find role option` only matches `role=option` ARIA nodes, which are exclusively in the portal listbox, preventing the race condition where `find text "San Francisco" click` matches the input's own current value text instead of a dropdown item.

---

### Suggestion C — `eval -b <base64>` for complex combobox verification JS

**Command:** `eval -b <base64>` (and `eval --stdin` for heredoc mode)  
**Widget:** React-Select combobox verification (the existing eval pattern has quote escaping issues).  
**Exact example:**

The current finisher prompt teaches this inline eval for verification:
```
agent_browser(["eval", "var el=document.getElementById('<FIELD_ID>').closest('.select-shell'); var sv=el&&el.querySelector('[class*=\"single-value\"]'); sv?sv.textContent:'EMPTY'"])
```

The nested `\"` sequences and single-quotes interact badly when the Python string is passed through the shell. The safe version:
```python
import base64
js = """
var el = document.getElementById('question_66747918').closest('.select-shell');
var sv = el && el.querySelector('[class*="single-value"]');
sv ? sv.textContent : 'EMPTY'
"""
b64 = base64.b64encode(js.encode()).decode()
agent_browser(["eval", "-b", b64])
```
Or in CLI form: `agent_browser(["eval", "--stdin"])` with the JS piped via stdin.

**Why it helps:** The current inline `eval "..."` breaks when the JavaScript contains double quotes (which React-Select class-name selectors require). Base64 encoding eliminates all shell-escaping issues entirely. This should replace every inline eval in the prompt that contains `\"` sequences.

---

## 5. `skills get core` vs `skills get core --full` diff

`skills get core` (truncated, ~400 lines):
- Main narrative: loop, quickstart, reading, interacting, waiting, common workflows, troubleshooting, global flags.
- React/Web Vitals section.
- Pointer to `--full`.

`skills get core --full` (~1900 lines) adds these sections entirely absent from the truncated version:

| Section | Key content not in truncated | Finisher relevance |
|---|---|---|
| `references/commands.md` | `keydown`/`keyup` commands (not in `--help` at all); `addinitscript`; `tab new --label`; `window new`; `set viewport W H 2` (retina); `network route --resource-type`; `batch` pre-navigation setup; `record restart` | HIGH — `keydown`/`keyup` are completely undocumented except here |
| `references/snapshot-refs.md` | Cross-origin iframe handling detail; one-level nesting rule; `frame @ref` vs `frame "#sel"` distinction | MEDIUM — if any ATS iframes the form |
| `references/authentication.md` | Auth vault deep dive, session persistence patterns | LOW for finisher |
| `references/session-management.md` | Multi-session patterns | LOW for finisher |
| `references/profiling.md` | Trace/profiler usage | LOW for finisher |
| `references/proxy-support.md` | Proxy config | LOW for finisher |
| `references/video-recording.md` | Video capture | LOW for finisher |
| `templates/*` | Shell starter scripts | LOW for finisher |

**Most important finding from `--full` not visible elsewhere:**

1. `keydown` and `keyup` are documented ONLY in `references/commands.md`. They do not appear in `agent-browser --help` or in `skills get core`. The finisher prompt has no concept of these commands. They are needed for modifier-key combos in date-pickers (hold Shift while clicking a calendar range) and for simulating Alt+ArrowDown to open some comboboxes that don't respond to plain click.

2. `eval -b <base64>` and `eval --stdin` are mentioned only as examples in `--full`'s commands reference. The finisher prompt exclusively uses inline `eval "..."`, which is fragile for any JS containing double quotes or backticks — precisely the pattern used in React-Select class-name selectors (`[class*="single-value"]`).

3. The `batch` command's pre-navigation setup pattern (open with no URL + route interception + cookies + navigate) appears only in `--full`. Not relevant to the finisher (no navigation) but useful for the worker.
