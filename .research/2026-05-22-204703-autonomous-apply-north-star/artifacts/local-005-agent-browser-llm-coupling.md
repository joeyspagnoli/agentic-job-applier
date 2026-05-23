# local-005 — agent-browser LLM coupling (`chat` command)

- **Date:** 2026-05-22
- **Sources:**
  `reference-repos/agent-browser/cli/src/chat.rs` (CLI front-end),
  `cli/src/native/stream/chat.rs:1-156, 124-160` (system prompt, tool schema, `is_chat_enabled`),
  `cli/src/native/stream/chat.rs:721, 774` (interactive mode in the dashboard server),
  `README.md:765-795` (chat docs),
  `package.json` (no model SDK deps; AI traffic flows via HTTP),
  `Cargo.toml` (only `reqwest`, no `anthropic` / `openai` / `tonic` etc.).
- **Thesis:** agent-browser ships a single LLM loop (`agent-browser chat "<instruction>"`) that uses the **OpenAI Chat Completions API shape** routed through the **Vercel AI Gateway** (BYO key, no first-party model integration). It exposes a **single tool** to the model: `agent_browser(command: string)` — i.e. "run any agent-browser CLI string". There is no supervisor/executor split, no per-skill tool, no native MCP server. The default model is `anthropic/claude-sonnet-4.6` and is overridable.

## The `chat` command

`cli/src/chat.rs:10`:

```rust
const DEFAULT_MODEL: &str = "anthropic/claude-sonnet-4.6";
```

`cli/src/chat.rs:19-104` is the entrypoint. Three invocation modes:

```bash
agent-browser chat "open google.com and search for cats"     # single-shot
agent-browser chat                                           # interactive REPL
agent-browser chat -q "summarize this page"                  # quiet (text only)
agent-browser chat -v "fill in the login form"               # verbose (show tool I/O)
agent-browser --model openai/gpt-4o chat "take a screenshot" # model override
agent-browser --json chat "..."                              # structured output
```

(README.md:776-783)

The chat command refuses to run without an AI Gateway key (`chat.rs:20-33`):

```rust
if !chat::is_chat_enabled() {
    if flags.json {
        println!("{}", json!({
            "success": false,
            "error": "AI_GATEWAY_API_KEY not set. Set the AI_GATEWAY_API_KEY environment variable to enable chat."
        }));
    } else {
        eprintln!("{} AI_GATEWAY_API_KEY not set. ...", color::error_indicator());
    }
    exit(1);
}
```

So **BYO key, always**. No first-party Anthropic account; the maintainers expect you to route via `https://ai-gateway.vercel.sh` (`README.md:773-775`):

```bash
export AI_GATEWAY_API_KEY=gw_your_key_here
export AI_GATEWAY_MODEL=anthropic/claude-sonnet-4.6           # optional, default
export AI_GATEWAY_URL=https://ai-gateway.vercel.sh           # optional, default
```

The gateway URL is overridable, so technically you could point it at any OpenAI-compatible endpoint (your own LiteLLM, OpenRouter, vLLM, etc.) — `chat.rs:127-132`:

```rust
let gateway_url = std::env::var("AI_GATEWAY_URL")
    .unwrap_or_else(|_| chat::DEFAULT_AI_GATEWAY_URL.to_string())
    .trim_end_matches('/')
    .to_string();
let api_key = std::env::var("AI_GATEWAY_API_KEY").unwrap_or_default();
let url = format!("{}/v1/chat/completions", gateway_url);
```

The shape is the OpenAI Chat Completions `/v1/chat/completions` endpoint, requested with `stream: true`. SSE deltas are parsed (`chat.rs:398-492`) — text chunks printed to stdout, tool calls accumulated.

## Tool schema — exactly one tool

`cli/src/native/stream/chat.rs:156` (the entire schema as a const):

```rust
pub(crate) const CHAT_TOOLS: &str = r#"[{
  "type":"function",
  "function":{
    "name":"agent_browser",
    "description":"Execute an agent-browser command. Runs against the active session by default. Add --session <name> to target or create a different session, and --engine <engine> to choose a browser engine.",
    "parameters":{
      "type":"object",
      "properties":{
        "command":{
          "type":"string",
          "description":"The command to execute, e.g. 'agent-browser open https://google.com' or 'agent-browser --session new-session open https://example.com' or 'agent-browser snapshot -i' or 'agent-browser click @e3'"
        }
      },
      "required":["command"]
    }
  }
}]"#;
```

**One tool. One string parameter. That's the entire interface to the model.**

The model is expected to write full CLI strings as the value of `command`, which agent-browser then `shell_words_split`s, parses with the normal `parse_command` machinery, and routes through the daemon. So under the hood it's "LLM → tool call → CLI argv → IPC → daemon → CDP → Chrome".

This is *not* a structured tool API. The model is not told "you may call `click(ref, opts)` or `fill(ref, text)`" — it's told "emit any shell command starting with `agent-browser`".

## The loop

`cli/src/chat.rs:195-394` is the chat turn. Step by step:

1. **Build OpenAI messages array** with `chat::get_system_prompt()` as the system message + user input.
2. POST to `${gateway}/v1/chat/completions` with `tools: [CHAT_TOOLS]`, `stream: true`.
3. Parse SSE deltas (`parse_gateway_stream`, `chat.rs:398-492`). Collect text chunks (print live) and tool calls.
4. If tool calls present, run each:
   ```rust
   // chat.rs:344-376
   for (tc_id, _tc_name, tc_args) in &tool_calls {
       let input: Value = serde_json::from_str(tc_args).unwrap_or(json!({}));
       let command = input.get("command").and_then(|c| c.as_str()).unwrap_or("");

       if !json_mode && verbosity != Verbosity::Quiet {
           eprintln!("{}", color::dim(&format!("> {}", command)));
       }

       let result = match tokio::time::timeout(
           tool_timeout, chat::execute_chat_tool(session, command)
       ).await {
           Ok(r) => r,
           Err(_) => "Tool execution timed out after 60 seconds.".to_string(),
       };
       // ...
       openai_messages.push(json!({
           "role": "tool",
           "tool_call_id": tc_id,
           "content": result
       }));
   }
   ```
5. Loop up to **50 steps** (`chat.rs:232: for _step in 0..50`) or **300 seconds total deadline** (`chat.rs:225`).
6. Each individual tool call has a **60-second timeout** (`chat.rs:226`).
7. If no tool calls in the latest assistant turn, break — that's the final answer.

Compaction: in interactive mode, `chat.rs:159-177` summarizes old turns when the conversation exceeds `chat::COMPACT_THRESHOLD_CHARS`. Single-shot mode has no compaction (it can't run long enough to matter at 50 steps × 60s).

## Supervisor/executor split? No.

One model, one loop, one tool. No planner-vs-executor decomposition. No two-model setup. No vision-LLM-for-screenshots side path.

The model **does** receive a system prompt (`get_system_prompt()` at `native/stream/chat.rs:124`) which presumably teaches it the snapshot-then-act pattern — but everything happens in one Chat Completions stream. There is no orchestration layer like LangGraph or PydanticAI agents.

## MCP server? No.

Searched all the way through `cli/src/`:

```
grep -rln "mcp\|model.context.protocol\|Model Context Protocol" cli/src/
# (no results)
```

agent-browser is **not** an MCP server. It cannot be wired into Claude Desktop / Cursor / Codex as an MCP tool source. The way Cursor etc. pick it up today is via the **skill** mechanism (a markdown file describing the CLI) — see `local-003`. The model invokes it by writing shell commands, not by making MCP `tools/call` requests.

If we wanted an MCP server in front of agent-browser, we'd build one ourselves — a thin shim that proxies MCP `tools/call` requests to `subprocess.run(["agent-browser", "--json", ...])`. (See `local-004` for prior art shape via the `agent-browser-sandbox.ts` wrapper.)

## Streaming / dashboard

`cli/src/native/stream/` (chat.rs, websocket.rs, dashboard.rs, http.rs, cdp_loop.rs, discovery.rs) implements:

- The dashboard HTTP server on port 4848 (`main.rs:503-510`):
  ```rust
  if env::var("AGENT_BROWSER_DASHBOARD").is_ok() {
      let port: u16 = env::var("AGENT_BROWSER_DASHBOARD_PORT")
          .ok().and_then(|s| s.parse().ok()).unwrap_or(4848);
      // ...
      rt.block_on(native::stream::run_dashboard_server(port));
      return;
  }
  ```
- A **dashboard-side chat panel** that reuses the same `CHAT_TOOLS` and OpenAI Gateway flow via the Vercel AI SDK's UI Message Stream protocol (README.md:789-791). Implementation: `native/stream/chat.rs:721, 774` (`get_system_prompt()` and `CHAT_TOOLS` reused by the WebSocket-based dashboard chat).
- A WebSocket-based live viewport stream (the dashboard shows JPEG frames of the browser, plus the command activity feed).

The dashboard's chat panel is a parallel surface to the CLI `chat` — same backend, different transport. Both target the Vercel AI Gateway.

## What the model sees per turn

A rough reconstruction of one chat turn:

```
SYSTEM: <the system prompt — defines snapshot-and-ref workflow, safety,
         common commands, etc., served by stream/chat.rs:124>

TOOLS: [
  {
    "name": "agent_browser",
    "description": "Execute an agent-browser command. ...",
    "parameters": { "type": "object", "properties": { "command": { "type": "string" } } }
  }
]

USER: "Open example.com and click the first link."

ASSISTANT:
  text: "I'll open the page, snapshot for interactive refs, and click the first link."
  tool_calls: [ {name: "agent_browser", arguments: '{"command":"agent-browser open https://example.com"}'} ]

TOOL (id=...): "<text output of `agent-browser open https://example.com`>"

ASSISTANT:
  tool_calls: [ {name: "agent_browser", arguments: '{"command":"agent-browser snapshot -i"}'} ]

TOOL (id=...): "<snapshot output with @e1...@eN refs>"

ASSISTANT:
  tool_calls: [ {name: "agent_browser", arguments: '{"command":"agent-browser click @e1"}'} ]

TOOL: "<click result>"

ASSISTANT:
  text: "Done — clicked the first link."
  (no tool_calls → loop ends)
```

## What's exposed vs what isn't

| Thing | Exposed to model? | Notes |
|---|---|---|
| `agent_browser` tool taking arbitrary CLI string | yes | the only tool |
| Specific tools per skill (e.g. `dogfood_run`) | no | skills are prompt-content, not callable tools |
| Page screenshot bytes inline | no | screenshots return file paths, model reads via separate `agent-browser get text`-style calls or `--annotate` legend |
| Action-policy hooks for the model | no | policy is enforced *after* the tool call, blocking it; the model just sees an error |
| Confirmation-required prompts | yes (kind of) | if `--confirm-actions` is set, daemon returns `confirmation_required: true`; the chat loop does *not* currently auto-handle that — it would just see the response as a tool result |
| Multi-turn conversation memory | yes | `openai_messages` array, with compaction in REPL mode |

## Operational limits

- Total chat-turn deadline: 5 minutes (`chat.rs:225`)
- Per-tool-call timeout: 60 seconds (`chat.rs:226`)
- Max steps: 50 (`chat.rs:232`)
- Default model: `anthropic/claude-sonnet-4.6` (`chat.rs:10`)
- Compaction: triggered at `COMPACT_THRESHOLD_CHARS` chars, keeps last `KEEP_RECENT_MESSAGES` turns (constants are in `native/stream/chat.rs` — not directly read)

## How this matters for the apply pipeline

If we adopt `agent-browser chat` as our LLM driver:

- **Plug-and-play:** point `AI_GATEWAY_API_KEY` and `AI_GATEWAY_URL` at our chosen gateway (we already use Anthropic; we'd either go via Vercel AI Gateway or stand up our own OpenAI-shaped proxy).
- **Hard ceiling:** 5min per task, 50 tool calls. A 12-step Workday application could fit inside that budget; an EEO + cover-letter + 6 screener questions task is at risk.
- **No structured "stop before submit" handle:** the model just sees CLI string output. We'd enforce via `--action-policy` (action-level only — see `local-006`) or pre-process the model's intended commands ourselves before forwarding to the daemon.
- **Replaceable.** Because the loop is OpenAI-shape over HTTP, we could also **bypass `agent-browser chat` entirely** and run our own loop (PydanticAI, Anthropic SDK, etc.) that emits `subprocess.run(["agent-browser", "--json", ...])` calls. This is probably the right path for us since:
  - We already author tools/loops in Python.
  - We need our own safety policies (no-submit, audit logging, per-job context).
  - We want to send screenshots to the model directly, not just text snapshots.

The `chat` command exists, but it is **a thin convenience wrapper, not the value proposition** of agent-browser. The value is the CLI + accessibility-snapshot + daemon. We can keep those and bring our own loop.
