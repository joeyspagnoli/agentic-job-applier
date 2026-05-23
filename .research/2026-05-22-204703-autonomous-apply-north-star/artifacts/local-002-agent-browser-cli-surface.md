# local-002 — agent-browser CLI surface

- **Date:** 2026-05-22
- **Sources:**
  `reference-repos/agent-browser/README.md` (sections 80-475),
  `cli/src/main.rs` (subcommand dispatch),
  `cli/src/commands.rs` (parser),
  `cli/src/flags.rs`,
  `cli/src/output.rs` (--help generator),
  `agent-browser.schema.json`.
- **Thesis:** The CLI exposes ~80+ subcommands organised into 12 verb families (navigate, interact, query, wait, batch, network, tabs, frames, dialogs, debug, auth, config). The shape is Playwright-like but command-line first. Every command has a `--json` mode emitting `{"success": ..., "data": ..., "error": ...}`. For a Python caller the integration is "subprocess + parse `--json`".

## How the CLI is invoked

Two equivalent forms:

```bash
# Direct (after npm i -g agent-browser, or symlinked via cargo install)
agent-browser <command> [flags] [args]

# Wrapped (avoids global install)
npx agent-browser <command> [flags] [args]
```

The dogfood skill explicitly tells agents (`skill-data/dogfood/SKILL.md:24-26`):

> Always use `agent-browser` directly — never `npx agent-browser`. The direct binary uses the fast Rust client. `npx` routes through Node.js and is significantly slower.

So Node is only on the cold path for binary dispatch.

## Verb taxonomy

From `README.md:103-475` and `cli/src/commands.rs` (the ~5100-line parser dispatch). Sample sets only — full list runs ~80+ subcommands.

### 1. Lifecycle (`main.rs:540-630`)
```
open [url]              # launch+nav (aliases: goto, navigate)
close [--all]           # close session (aliases: quit, exit)
session [list]          # current/active session list
install [--with-deps]   # download Chrome from Chrome-for-Testing
upgrade                 # bump CLI to latest
doctor [--fix --json]   # diagnose & repair (220+ checks per CHANGELOG.md:36)
dashboard start|stop    # observability dashboard
```

### 2. Interaction (`README.md:107-141`)
```
click <sel> [--new-tab]      hover <sel>
dblclick <sel>                check <sel>
focus <sel>                   uncheck <sel>
type <sel> <text>             select <sel> <val>...
fill <sel> <text>             scroll <dir> [px]
press <key>                   scrollintoview <sel>
keyboard type <text>          drag <src> <tgt>
keyboard inserttext <text>    upload <sel> <files...>
keydown <key>                 screenshot [path]
keyup <key>                   pdf <path>
```

### 3. Locators (`README.md:166-193`)
```
find role <role> <action> [value] [--name <accessible-name>] [--exact]
find text <text> <action>
find label <label> <action> [value]
find placeholder <ph> <action> [value]
find alt <text> <action>
find title <text> <action>
find testid <id> <action> [value]
find first <sel> <action> [value]
find last <sel> <action> [value]
find nth <n> <sel> <action> [value]
```
Action token = `{click, fill, type, hover, focus, check, uncheck, text}`. The selector can be a CSS selector, a ref like `@e3` (from a prior `snapshot`), or `text=...` / `xpath=...`.

### 4. Reading the page (`README.md:144-208, 652-664`)
```
snapshot [-i] [-u] [-c] [-d <n>] [-s <sel>]
get text|html|value|attr|title|url|cdp-url|count|box|styles ...
is visible|enabled|checked <sel>
wait <selector|ms>
wait --text <substring> | --url <pattern> | --load <state> | --fn <js>
```

`-i` (interactive only) is the workhorse — it trims the accessibility tree down to "things you can click/fill" so the LLM only sees ~200-400 tokens (`skill-data/core/SKILL.md:43-49`).

### 5. State / auth / cookies / extensions (`README.md:264-279, 449-518`)
```
state save|load|list|show|rename|clear|clean ...
cookies [set [--curl <file>]|clear]
storage local|session [get|set|clear]
auth save|login|list ...        # local encrypted credential vault
--state <file>                  # load saved state at launch
--session-name <name>           # auto-save/restore by name
--profile <name|path>           # reuse a Chrome user-data-dir
--extension <path>              # load CRX/unpacked extension (repeatable)
```

### 6. Network (`README.md:282-298`)
```
network route <url> [--abort] [--body <json>] [--resource-type <csv>]
network unroute [url]
network requests [--filter <s>] [--type <csv>] [--method <m>] [--status <c>]
network request <requestId>
network har start|stop [output.har]
```

### 7. Tabs / frames / dialogs (`README.md:301-345`)
```
tab [list|new [--label X] [url]|<t<N>|label>|close [<id|label>]]
window new
frame <sel>          # switch CDP context to an iframe
frame main           # back to top
dialog accept [text]|dismiss|status
```

### 8. Diff / debug / trace (`README.md:348-385`)
```
diff snapshot [--baseline <file>] [--selector <sel>] [--compact]
diff screenshot --baseline <png> [-o <out>] [-t <0..1>]
diff url <u1> <u2> [--screenshot] [--wait-until <state>] [--selector <s>]
trace start|stop [path]
profiler start|stop [path]
console [--json|--clear]
errors [--clear]
highlight <sel>
inspect                # open DevTools for active page
record start|stop      # webm video
```

### 9. Batch (`README.md:212-232`, `cli/src/main.rs:1276-1418`)
```
agent-browser batch "open url" "snapshot -i" "click @e3"   # args mode
echo '[["open","url"],["snapshot","-i"]]' | agent-browser batch --json
agent-browser batch --bail ...     # stop on first error
```

This is the multi-command-in-one-IPC-call mode. Per the README:212-215: "This avoids per-command process startup overhead when running multi-step workflows."

### 10. AI chat (covered in `local-005`)
```
chat "<instruction>"   # single-shot
chat                   # interactive REPL
chat -q|-v             # quiet/verbose tool output
--model <name>         # override openai/gpt-4o / anthropic/claude-sonnet-4.6
```

### 11. Skills (covered in `local-003`)
```
skills [list]
skills get <name> [--full] [--all]
skills path [name]
```

### 12. Security gates (covered in `local-006`)
```
--allowed-domains "ex.com,*.ex.com"
--action-policy <path>            # JSON file: deny/allow/confirm by action name
--confirm-actions eval,download
--confirm-interactive             # TTY-only y/N prompt
--content-boundaries              # wrap page output in delimiters
--max-output 50000                # cap returned text size
```

## --help quotes (from `cli/src/output.rs`)

The README and `--help` are kept in sync per `AGENTS.md:18-26`. Sample lines from `output.rs`:

```
$ wc -l cli/src/output.rs  # → 3385 lines
```

`output.rs` is a single hand-written Rust function that prints the help text per subcommand (`print_command_help`, called from `main.rs:521`). Every subcommand has its own help block. The dispatcher is:

```rust
// main.rs:517-525
let has_help = args.iter().any(|a| a == "--help" || a == "-h");
if has_help {
    if let Some(cmd) = clean.first() {
        if print_command_help(cmd) { return; }
    }
    print_help();
    return;
}
```

## JSON-mode contract

Every command supports `--json`. Examples from the README + `cli/src/output.rs`:

```bash
$ agent-browser snapshot --json
{"success":true,"data":{"snapshot":"...","refs":{"e1":{"role":"heading","name":"Title"},...}}}

$ agent-browser get text @e1 --json
{"success":true,"data":{"text":"Welcome"}}

$ agent-browser is visible @e2 --json
{"success":true,"data":{"visible":true}}

$ agent-browser screenshot --json
{"success":true,"data":{"path":"/tmp/screenshot-2026-02-17T...png","size":[1280,720]}}
```

Error shape (`cli/src/main.rs:48-61`):

```json
{ "success": false, "error": "<human-readable>", "type": "<error_type?>" }
```

Where `type` is one of (`commands::ParseError` → main.rs:636-642):
- `unknown_command`
- `unknown_subcommand`
- `missing_arguments`
- `invalid_value`
- `invalid_session_name`

For runtime errors from the daemon (selector not found, click intercepted, etc.) the daemon returns `success: false` with `error` set but no `type`. This is the contract a Python subprocess caller would parse.

## Exit codes

`main.rs:1261-1273`:

```rust
print_response_with_opts(&resp, action, &output_opts);
if !success {
    exit(1);
}
// ...
Err(e) => {
    if flags.json { print_json_error(e); } else { eprintln!(...); }
    exit(1);
}
```

`0` on success, `1` on any error (parse or runtime). `confirm-interactive` denial also exits 1 (`main.rs:1243-1246`).

## Worked example for a Python caller

```python
import subprocess, json, os

env = {**os.environ, "AGENT_BROWSER_SESSION": "apply_worker"}

def ab(*args):
    r = subprocess.run(
        ["agent-browser", "--json", *args],
        capture_output=True, text=True, env=env, timeout=30
    )
    payload = json.loads(r.stdout)
    if not payload.get("success"):
        raise RuntimeError(payload.get("error"))
    return payload.get("data") or {}

# attach to the already-running Chrome our flow opened on :9222
ab("--cdp", "9222", "open", "https://app.simplify.jobs/jobs/abc")

# read the page
snap = ab("snapshot", "-i")["snapshot"]   # multi-line text with @e1...@eN refs

# act
ab("fill", "@e3", "Looking for new opportunities in distributed systems.")
ab("click", "@e5")     # next page
```

There is **no Python or TypeScript SDK** in this repo. Every integration is shell-out + JSON parse. There is no MCP server either (see `local-005`).

## Configuration file

Per `README.md:793-823` and `agent-browser.schema.json` (full content fetched as evidence in `local-001`):

```
1. ~/.agent-browser/config.json      (user defaults)
2. ./agent-browser.json              (project overrides)
3. AGENT_BROWSER_* env vars          (override config)
4. CLI flags                         (override everything)
```

Schema lists ~30 settable keys (`headed`, `cdp`, `autoConnect`, `profile`, `state`, `proxy`, `allowedDomains`, `actionPolicy`, `confirmActions`, `engine: chrome|lightpanda`, etc.). All optional. `additionalProperties: true` so unknown keys are tolerated.

## Why this matters for our pipeline

A Python worker can drive agent-browser **today** with `subprocess.run(["agent-browser", "--json", ...])`. There is no need for an SDK, no async runtime to coordinate, no MCP stdio dance — the daemon stays warm across calls because the session name pins it.

But: every command crosses a process boundary (Python → CLI client → IPC → daemon → CDP → Chrome → back). Latency is non-trivial. The README's own benchmarks (`benchmarks/README.md:69-74`) say "Command latency is dominated by Chrome (CDP round-trips), not the daemon" — i.e. the per-call overhead from the CLI itself is small, but you'll still pay the Chrome round-trip for every `snapshot`, `fill`, `click`. The `batch` command and the long-lived daemon are the mitigations.
