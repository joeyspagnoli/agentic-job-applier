# local-001 — agent-browser overview

- **Date:** 2026-05-22
- **Sources:**
  `reference-repos/agent-browser/package.json`,
  `cli/Cargo.toml`,
  `bin/agent-browser.js`,
  `cli/src/main.rs`,
  `cli/src/native/cdp/{chrome.rs,discovery.rs,client.rs}`,
  `cli/src/native/daemon.rs`,
  `CHANGELOG.md` (v0.27.0, v0.26.0),
  `README.md`.
- **Thesis:** agent-browser is a native Rust CLI that speaks Chrome DevTools Protocol (CDP) directly over WebSocket, with no Playwright/Puppeteer/Node dependency at runtime. Each `--session` runs as a long-lived background daemon, and the CLI sends JSON-RPC-ish action messages over a Unix domain socket to the daemon, which translates them into raw CDP calls.

## What ships

`package.json:1-52` advertises a single bin entry:

```json
"name": "agent-browser",
"version": "0.27.0",
"engines": { "node": ">=24.0.0", "pnpm": ">=11.0.0" },
"bin": { "agent-browser": "./bin/agent-browser.js" }
```

`bin/agent-browser.js:31-66` is a thin Node shim that detects platform/arch and `spawn`s the appropriate native binary:

```js
function getBinaryName() {
  // ...
  return `agent-browser-${osKey}-${archKey}${ext}`;   // e.g. agent-browser-linux-x64
}
// ...
const child = spawn(binaryPath, process.argv.slice(2), { stdio: 'inherit', ... });
```

So Node is required only for `npx`/global-install dispatch — it disappears after launch. The Rust binary does everything.

## Rust runtime, not a Playwright wrapper

`cli/Cargo.toml:13-37` lists every dep:

```toml
tokio = { version = "1", features = ["rt-multi-thread", "macros", "net", "io-util", "time", "sync", "signal", "process"] }
tokio-tungstenite = { version = "0.24", features = ["rustls-tls-webpki-roots"] }
futures-util = "0.3"
url = "2"
reqwest = { version = "0.12", default-features = false, features = ["json", "rustls-tls-webpki-roots", "stream"] }
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
sha2 = "0.10"
aes-gcm = "0.10"
image = "0.25"
zip = { version = "8.2.0", default-features = false, features = ["deflate"] }
# ...
[target.'cfg(unix)'.dependencies]
libc = "0.2"
[target.'cfg(windows)'.dependencies]
windows-sys = { version = "0.52", features = ["Win32_System_Threading", "Win32_Foundation"] }
```

There is **no `playwright`, `puppeteer`, `headless_chrome`, `chromiumoxide`, `fantoccini`, or `webdriver` crate**. The CDP transport is `tokio-tungstenite` (raw WebSocket) and `reqwest` (for `/json/version` discovery). Chrome itself is downloaded from Chrome for Testing by the `install` subcommand (`README.md:451`: "Download Chrome from Chrome for Testing (Google's official automation channel)"). README:77 confirms: "No Playwright or Node.js required for the daemon."

## Daemon model

`cli/src/main.rs:488-499`:

```rust
// Native daemon mode: when AGENT_BROWSER_DAEMON is set, run as the daemon process
if env::var("AGENT_BROWSER_DAEMON").is_ok() {
    // ...
    let session = env::var("AGENT_BROWSER_SESSION").unwrap_or_else(|_| "default".to_string());
    let rt = tokio::runtime::Runtime::new().expect("Failed to create tokio runtime");
    rt.block_on(native::daemon::run_daemon(&session));
    return;
}
```

The CLI re-execs *itself* with `AGENT_BROWSER_DAEMON=1` to spawn a background daemon, one per `--session` name. Each CLI invocation:

1. `flags::parse_flags` (main.rs:514) → strips flags into a `Flags` struct.
2. `connection::ensure_daemon(session, opts)` (main.rs:761) → if no live daemon for this session, fork one; if one exists, reuse it.
3. `commands::parse_command(clean, flags)` (main.rs:632) → translates the user CLI args into a JSON action object like `{"id": "...", "action": "click", "selector": "@e2"}`.
4. `connection::send_command(cmd, session)` (main.rs:1202) → ships the JSON over the daemon's Unix domain socket.
5. Daemon executes via `native::actions::execute_command` (daemon.rs:14, 406) and returns a `Response { success, data, error, warning }`.

The CLI is essentially a thin client over a local IPC protocol. The daemon owns the WebSocket connection to Chrome.

## Browser-launch model: spawns OR attaches

Three launch modes, all selected from CLI flags (`cli/src/main.rs:887-1185`):

1. **Spawn its own Chrome** (default). `native::cdp::chrome::ChromeProcess` (cdp/chrome.rs:8-87) `Command::new(chrome_exe)`-spawns Chrome with `--remote-debugging-port=<free>` and a temp `--user-data-dir`. Cleanup on `Drop` kills the process group on Unix.
2. **Attach to an existing Chrome over CDP.** `--cdp <port|url>` (main.rs:928-1019) sends `{"action": "launch", "cdpPort": 9222}` or `{"action": "launch", "cdpUrl": "ws://..."}`. The daemon does HTTP `/json/version` discovery (`cdp/discovery.rs:20-65`) to find the actual browser-level WebSocket URL, then connects via `tokio-tungstenite`.
3. **Auto-discover a running Chrome.** `--auto-connect` (main.rs:887-923) sends `{"action": "launch", "autoConnect": true}`. The daemon scans known ports for a live CDP endpoint.

Cloud providers (`--provider browserbase|browserless|browser-use|kernel|agentcore`) follow path #2 by routing through `native::providers::connect_provider` (`providers.rs:26-69`) which calls the provider's API to obtain a CDP URL, then connects normally.

CHANGELOG.md:60 documents path #2's reliability story: "Fixed `--auto-connect` CDP discovery preferring HTTP endpoint discovery over the DevToolsActivePort websocket path." Real reliability work has gone into the discovery layer.

## What the daemon-to-Chrome wire looks like

`cli/src/native/snapshot.rs:228, 295-302` (the `snapshot` command):

```rust
client.send_command_no_params("DOM.enable", Some(session_id)).await?;
client.send_command_no_params("Accessibility.enable", Some(session_id)).await?;
// ...
let ax_tree: GetFullAXTreeResult = client
    .send_command_typed("Accessibility.getFullAXTree", &ax_params, Some(effective_session_id))
    .await?;
```

It calls the raw CDP methods (`DOM.enable`, `Accessibility.getFullAXTree`, `Runtime.evaluate`, `DOM.describeNode`, etc.) by name. There is no Playwright `Page` abstraction in between.

## Entry points exposed to a calling agent

There is exactly one runtime interface: **the CLI binary**, with two output modes:

- Default (text) — `--help`, `--version`, snapshot rendered as indented tree.
- `--json` — every command emits `{"success": bool, "data": {...}, "error": "..."}` to stdout.

Stdin path: `batch --json` (README.md:226) accepts JSON arrays of arg arrays via stdin. Some commands like `cookies set --curl <file>` and `eval --stdin` also consume stdin.

There is **no MCP server**, **no JSON-RPC server over a socket** exposed to external callers, **no language SDK** (Python/TS bindings), and **no library mode**. The only external integrations are:

- `chat` subcommand → Vercel AI Gateway (HTTP, OpenAI-compat) — analyzed in `local-005`.
- `dashboard start` → spawns a separate process that runs a same-process Rust HTTP server on port 4848 with WebSocket streaming for live viewport.

Distribution model:

- npm: `npm i -g agent-browser` (postinstall downloads platform binary)
- Homebrew: `brew install agent-browser`
- Cargo: `cargo install agent-browser`
- Source: clone, `pnpm install`, `pnpm build:native`

Node 24+ is required only for `npx` / pnpm builds, not for running the binary.

## Operational telemetry

- ~5100-line `cli/src/commands.rs` parser, ~17680 lines of Rust total across `cli/src/`.
- ~320 unit tests (`AGENTS.md:99-101`).
- 18 e2e tests gated behind `--ignored` (AGENTS.md:108-115) that launch real headless Chrome.
- Active release cadence: v0.27.0 in this checkout, recent commits adding React DevTools introspection (#1257), Web Vitals (`vitals`), SPA `pushstate`, init scripts, dashboard proxy support.
- Windows debugging via remote SSM-managed EC2 (`AGENTS.md:127-185`) — real cross-platform investment.

## Bottom line for the report

This is a serious browser-automation engineering project. It is **not** a thin shim. It owns its own CDP client, its own daemon model, its own accessibility-tree snapshot logic. It does not depend on Playwright at any layer.

The unit of integration is the CLI — there is no library/SDK/MCP/RPC. Anything that wants to drive it must shell out and parse `--json` stdout.
