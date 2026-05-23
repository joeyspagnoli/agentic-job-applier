# local-006 — coexistence with our existing Playwright/CDP/Simplify pipeline

- **Date:** 2026-05-22
- **Sources:**
  `reference-repos/agent-browser/cli/src/main.rs:887-1019` (--cdp, --auto-connect),
  `cli/src/commands.rs:938-980` (the `connect` subcommand parser),
  `cli/src/native/cdp/discovery.rs` (CDP endpoint discovery),
  `cli/src/native/cdp/chrome.rs:8-130` (Chrome spawn model),
  `cli/src/native/snapshot.rs:1310-1340` (shadow-root traversal),
  `cli/src/native/snapshot.rs:228, 295-302` (Accessibility.getFullAXTree usage),
  `cli/src/native/policy.rs` (action policy mechanism — full file),
  `README.md:482-517` (auth import via existing Chrome),
  current pipeline: `src/agents/apply_worker/browser.py` (from project description).
- **Thesis:** agent-browser can **attach to our existing localhost:9222 Chrome over CDP cleanly**, but the unit of interop is "another CDP client", not "share a Playwright Page". Shadow DOM is traversed automatically. The "no-submit" guarantee we need cannot be enforced by agent-browser's built-in `--action-policy` (which is action-name-only) — we'd have to add a selector-level guard ourselves. There is no Python SDK; integration is shell-out plus `--json`.

## Q5a — Attach to a Chrome already running on `localhost:9222`?

**Yes, two equivalent ways.**

### Way 1: explicit port

`cli/src/commands.rs:938-980` (the `connect` subcommand parser):

```rust
"connect" => {
    let endpoint = rest.first().ok_or_else(|| ParseError::MissingArguments { ... })?;
    if endpoint.starts_with("ws://") || endpoint.starts_with("wss://")
       || endpoint.starts_with("http://") || endpoint.starts_with("https://")
    {
        Ok(json!({ "id": id, "action": "launch", "cdpUrl": endpoint }))
    } else {
        // port number — parse and validate
        let port: u16 = match endpoint.parse::<u32>() { ... };
        Ok(json!({ "id": id, "action": "launch", "cdpPort": port }))
    }
}
```

Two surface forms work:

```bash
# A) one-shot connect
agent-browser connect 9222

# B) implicit at any other command via --cdp
agent-browser --cdp 9222 snapshot -i
agent-browser --cdp ws://localhost:9222/devtools/browser/abc123 click @e3
```

In both cases, `cli/src/main.rs:928-985` packages the request into a daemon `launch` action with `cdpPort: 9222` (or `cdpUrl: "..."`). The daemon then runs CDP discovery to find the browser-level WebSocket and connects.

### Way 2: auto-discovery

`README.md:725` and `cli/src/main.rs:887-923`:

```bash
agent-browser --auto-connect snapshot -i
```

This sends `{"action":"launch","autoConnect":true}` and the daemon scans known CDP endpoints. CHANGELOG.md:60 notes recent reliability work here: "Fixed `--auto-connect` CDP discovery preferring HTTP endpoint discovery over the DevToolsActivePort websocket path." It reads `/json/version` first (`cdp/discovery.rs:35-47`), falls back to `/json/list`, then to a raw WebSocket on `/devtools/browser` (`cdp/discovery.rs:55-65`):

```rust
// Primary: /json/version (standard path)
let version_err = match fetch_cdp_info(host, port, timeout).await { ... };

// Fallback: /json/list (returns target list; look for the browser target)
let list_err = match fetch_cdp_list(host, port, timeout).await { ... };

// Final fallback: direct WebSocket at /devtools/browser.
// Chrome 136+ with UI-based remote debugging (chrome://inspect) exposes
// CDP over WebSocket but does not serve HTTP discovery endpoints.
match discover_cdp_ws(host, port, timeout).await { ... }
```

### What this means for our worker

Our `apply_worker/browser.py` already launches Chrome with `--remote-debugging-port=9222`. agent-browser can attach to that Chrome **without restarting it, without invalidating the Simplify extension, without losing cookies**. From agent-browser's perspective, the Chrome is "discovered" — it doesn't own the process, it just talks CDP to it.

There's even a documented "import auth from your browser" flow that does exactly this kind of attach (`README.md:494-510`):

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --remote-debugging-port=9222
agent-browser --auto-connect state save ./my-auth.json
agent-browser --state ./my-auth.json open https://app.example.com/dashboard
```

The maintainers explicitly support attaching to a user-launched Chrome and using its session state.

## Q5b — Can we hand off a live Playwright `Page`?

**Not directly. There is no Playwright integration anywhere in agent-browser.** It speaks raw CDP via `tokio-tungstenite`, not Playwright's protocol abstractions. But the **practical equivalent works**:

- Both Playwright and agent-browser are CDP clients pointed at the same Chrome instance.
- They can **coexist as concurrent CDP clients** on the same browser endpoint. CDP is multi-client-safe (this is the whole point of the `Target.attachToTarget` / `sessionId` model).
- Each tab is a separate CDP target. Either client can operate on any target. Switching "ownership" is just a matter of "which client is sending commands to which `targetId`".

Practical pattern for our worker:

1. Our Playwright code launches the page, runs the Simplify autofill, gets to the screener.
2. We capture the **active CDP target ID** (Playwright exposes it via `page.context().cdp_session(page)` or `chromium.connect_over_cdp(...).contexts[0].pages[0]`). The simpler proxy: just leave the page focused, since `agent-browser --auto-connect` picks the most-recently-active target.
3. We invoke `agent-browser --cdp 9222 snapshot -i` (or via `--session apply_worker` for daemon stickiness). agent-browser attaches to the same browser, finds the same active page, takes the snapshot.
4. Drive the screener via agent-browser CLI calls.
5. When agent-browser stops at the pre-submit gate, hand back to our Python code (which still has its Playwright `Page` alive and pointing at the same Chrome target).

**Caveat:** Playwright maintains internal state (network interception routes, dialog handlers, request listeners) that agent-browser doesn't know about. Concurrent operations could conflict (both clients setting `Network.enable` with different filters, etc.). Practical mitigation: avoid concurrent commands. Treat the handoff as "Playwright pauses, agent-browser runs, Playwright resumes".

**There is no "transfer this Page object" call** — Page objects are SDK-side abstractions, not over-the-wire entities. Both clients see the same Chrome target by `targetId`, that's the interop primitive.

## Q5c — Shadow DOM piercing

**Yes, supported, automatically.**

agent-browser's snapshot is built from `Accessibility.getFullAXTree` (`cli/src/native/snapshot.rs:228, 295-302`):

```rust
client.send_command_no_params("DOM.enable", Some(session_id)).await?;
client.send_command_no_params("Accessibility.enable", Some(session_id)).await?;
// ...
let ax_tree: GetFullAXTreeResult = client
    .send_command_typed("Accessibility.getFullAXTree", &ax_params, Some(effective_session_id))
    .await?;
```

CDP's `Accessibility.getFullAXTree` returns the **flattened a11y tree across shadow roots and same-origin iframes by default**. We don't have to ask for it; the protocol does it.

For CSS-selector-based interactions, when `--selector` is provided, agent-browser uses `Runtime.evaluate(document.querySelector(...))` to get an `objectId`, then `DOM.describeNode` with `depth: -1` (`snapshot.rs:246-272`). The traversal explicitly walks shadow roots (`snapshot.rs:1320-1341`):

```rust
/// Recursively collect all `backendNodeId` values from a CDP DOM node tree
/// (as returned by `DOM.describeNode` with `depth: -1`).
fn collect_backend_node_ids(node: &Value, ids: &mut std::collections::HashSet<i64>) {
    if let Some(id) = node.get("backendNodeId").and_then(|v| v.as_i64()) {
        ids.insert(id);
    }
    if let Some(children) = node.get("children").and_then(|v| v.as_array()) {
        for child in children {
            collect_backend_node_ids(child, ids);
        }
    }
    // Shadow DOM and content documents
    if let Some(shadow) = node.get("shadowRoots").and_then(|v| v.as_array()) {
        for child in shadow {
            collect_backend_node_ids(child, ids);
        }
    }
    if let Some(doc) = node.get("contentDocument") {
        collect_backend_node_ids(doc, ids);
    }
}
```

But there's a wrinkle: `document.querySelector(...)` itself does **not** pierce open shadow roots. So if the user passes `--selector "div.simplify-jobs-shadow-root button"`, the initial `querySelector` will only resolve `div.simplify-jobs-shadow-root` (a normal DOM node) — the button inside the shadow root would have to be found via the snapshot ref system (`@eN`) or via JavaScript that explicitly pierces (`eval ...shadowRoot.querySelector(...)`).

Iframes: the dedicated `frame <sel>` and `frame main` subcommands (README.md:330-333) switch CDP context into a same-origin iframe. Cross-origin iframes are explicitly noted (`skill-data/core/SKILL.md:392-397`):

> Cross-origin iframes that block accessibility tree access are silently skipped. Use `frame "#iframe"` to switch into them explicitly if the parent opts in, otherwise the iframe's contents aren't available via snapshot — fall back to `eval` in the iframe's origin or use the `--headers` flag to satisfy CORS.

For Simplify specifically: the Simplify Copilot injects a shadow-DOM widget (`div.simplify-jobs-shadow-root`). The buttons we currently click via Playwright's `locator("div.simplify-jobs-shadow-root").locator("button[aria-label='Autofill']").click()` — agent-browser would see these in the accessibility snapshot as ordinary `[button] "Autofill"` entries with refs, because `getFullAXTree` walks the shadow.

We'd verify this with:
```bash
agent-browser --auto-connect open https://app.simplify.jobs/jobs/<id>
agent-browser --auto-connect snapshot -i
# expected: @e<N> [button] "Autofill" appears in the tree even though it lives inside a shadow root
```

## Q5d — Wait / visibility primitives

Rich and built in. From `README.md:196-208`:

```bash
agent-browser wait <selector>         # Wait for element to be visible
agent-browser wait <ms>               # Wait for time (milliseconds)
agent-browser wait --text "Welcome"   # Wait for text to appear (substring match)
agent-browser wait --url "**/dash"    # Wait for URL pattern (glob)
agent-browser wait --load networkidle # Wait for load state
agent-browser wait --fn "window.ready === true"  # Wait for JS condition

# Wait for text/element to disappear:
agent-browser wait --fn "!document.body.innerText.includes('Loading...')"
agent-browser wait "#spinner" --state hidden
```

Default action timeout is 25s (`README.md:840-855`, env var `AGENT_BROWSER_DEFAULT_TIMEOUT`). Configurable up to ~30s before the CLI-to-daemon read timeout kicks in. Same primitive set Playwright offers.

`is` subcommands (`README.md:159-164`):

```bash
agent-browser is visible <sel>
agent-browser is enabled <sel>
agent-browser is checked <sel>
```

Sufficient to replace the Playwright `locator.is_visible()` / `wait_for(state="visible")` we use today.

## Q5e — Language: Python interop story

agent-browser is a Rust binary with **no Python or TypeScript SDK shipped**. The only library-style integration in the repo is `examples/environments/lib/agent-browser-sandbox.ts` — a TypeScript wrapper for the Vercel-sandbox demo (covered in `local-004`). It's a thin `subprocess.runCommand("agent-browser", args)` wrapper.

For our Python worker, the contract is:

```python
import subprocess, json, os

env = {**os.environ, "AGENT_BROWSER_SESSION": "apply_worker"}

def ab(*args, timeout=30, input=None):
    r = subprocess.run(
        ["agent-browser", "--json", *args],
        capture_output=True, text=True, env=env, timeout=timeout, input=input,
    )
    if r.returncode != 0:
        # JSON error envelope still goes to stdout when --json is set
        try:
            err = json.loads(r.stdout)
            raise RuntimeError(err.get("error", r.stderr))
        except json.JSONDecodeError:
            raise RuntimeError(f"agent-browser failed (exit {r.returncode}): {r.stderr}")
    return json.loads(r.stdout).get("data", {})
```

Latency: every call is process-spawn + IPC + CDP round-trip. The daemon stays warm across calls (so we don't re-spawn Chrome), but each `subprocess.run(["agent-browser", ...])` still spawns the CLI client process.

Mitigations:
- Use `--session apply_worker` consistently so the same daemon is reused.
- Use `agent-browser batch` for multi-step sequences (`README.md:212-232`). One process spawn, N commands in one IPC call.
- For tight loops, prefer `eval --stdin` over many individual `get` calls.

There is **no async API**. `subprocess.run` is blocking. Our worker is async (per the project description), so we'd wrap calls in `loop.run_in_executor` or `asyncio.create_subprocess_exec`.

## Q5f — The no-submit safety story

We hard-refuse to click "Submit Application" / "Submit" today. Our enforcement is in Python (the `apply_worker/browser.py` selector guard). agent-browser's built-in safety primitives:

1. **`--allowed-domains "ex.com,*.ex.com"`** — restricts navigation. Useful: we can scope the agent to `*.simplify.jobs,*.greenhouse.io,*.workday.com,*.lever.co,...` and forbid Outlook/Mail/etc. Not useful for submit-blocking.

2. **`--action-policy <path>`** (`cli/src/native/policy.rs`, full file read). A JSON file with `allow`, `deny`, `confirm`, `default` keys, but the matching unit is the **action name** (`click`, `fill`, `eval`, etc.):

   ```rust
   // policy.rs:84-119
   pub fn check(&self, action: &str) -> PolicyResult {
       if let Some(deny) = &self.deny {
           if deny.iter().any(|a| a == action) {
               return PolicyResult::Deny(format!("Action '{}' is denied by policy", action));
           }
       }
       if let Some(confirm) = &self.confirm {
           if confirm.iter().any(|a| a == action) {
               return PolicyResult::RequiresConfirmation;
           }
       }
       // ...
   }
   ```

   Tests confirm the granularity is "the verb, not what you act on" (`policy.rs:140-205`):

   ```rust
   #[test]
   fn test_policy_confirm() {
       let json = r#"{"allow": [], "deny": [], "confirm": ["submit"]}"#;
       let policy: ActionPolicy = serde_json::from_str(json).unwrap();
       assert_eq!(policy.check("submit"), PolicyResult::RequiresConfirmation);
   }
   ```

   But agent-browser **does not have a `submit` action** in its CLI. Submit happens via `click <submit-button>` or `press Enter` on a form field. So `{"deny": ["click"]}` would block all clicks (useless), and there is no way in the built-in policy file to say "deny clicks whose accessible name matches /submit application/i" or "deny clicks on `<button type=submit>`".

3. **`--confirm-actions click,eval`** — adds an interactive `[y/N]` prompt for those action categories. With `--confirm-interactive` plus a TTY, the agent waits for human approval. With no TTY (our worker), it **auto-denies** (`README.md:733`, `agent-browser.schema.json:124`). This is potentially usable as a hard-stop ("require confirmation for every click, run headless without a TTY → all clicks denied"), but it's binary — we lose the ability to click anything.

4. **`--content-boundaries`** — wraps page output (snapshots, get text) in delimiter markers so the LLM can distinguish tool output from page-controlled instructions. Defense against prompt injection from the page, not against bad clicks.

5. **`--max-output 50000`** — caps returned text size to avoid context flooding. Not safety-relevant for submit-blocking.

**Conclusion on safety:** the built-in primitives don't give us "stop before Submit". We'd have to either:

- Pre-process every model-emitted command in our worker (intercept the `agent-browser` CLI invocation, parse the args, refuse to forward if the target ref/selector resolves to a "Submit" button).
- Or write a Python pre-flight check that runs `agent-browser get text @<ref>` and `agent-browser get attr @<ref> aria-label` before forwarding any `click` command, then `RAISE` if the text matches a forbid list.
- Or — most reliable — **never grant the agent the `click` command on submit buttons**. Snapshot the page, identify the submit button ourselves (Python-side), and remove it from the snapshot before showing it to the model. The model literally cannot reference a ref it never saw.

The third option is the strongest. The accessibility snapshot is just text returned by `agent-browser snapshot -i --json` — we can filter it programmatically before passing it to the LLM.

## Q5g — Extensions, profile, file uploads

- **Extensions:** `--extension <path>` repeatable, or `AGENT_BROWSER_EXTENSIONS` env (`README.md:707`). Works in both headed and headless mode (`README.md:962`: "Browser extensions work in both headed and headless mode (Chrome's `--headless=new`)"). **But:** "Cannot use --extension with --cdp (extensions require local browser)" (`main.rs:873-881`). So if we attach to our existing Chrome (with the Simplify extension already loaded), agent-browser does **not** re-add extensions — it inherits them from the Chrome we attached to. This is what we want.

- **Profile:** `--profile <name|path>` reuses a Chrome user-data-dir (read-only snapshot copy by default, `README.md:551-569`). Same restriction: cannot combine with `--cdp` or `--provider`. Again: attaching to our pre-launched Chrome means we inherit its profile.

- **File upload:** `agent-browser upload @e5 file1.pdf` (`README.md:124`, `skill-data/core/SKILL.md:111`). This drives CDP's `Input.dispatchKeyEvent` / `Input.setFileInputFiles` underneath. Should work for the resume PDF upload step we currently do via Playwright.

## TL;DR for the verdict file

- **Attach to our Chrome:** Yes, clean. Three mechanisms (`connect <port>`, `--cdp <port|url>`, `--auto-connect`).
- **Share a Playwright Page:** Not via SDK, but both can be CDP clients on the same browser. Requires care (avoid concurrent commands).
- **Shadow DOM:** Pierced automatically via `Accessibility.getFullAXTree`. Refs work.
- **Waits:** Full suite, comparable to Playwright.
- **Python driving:** Subprocess + `--json`. No SDK, no MCP.
- **No-submit:** Built-in policy is action-level only. We'd enforce in our worker by filtering snapshots before showing the model.
