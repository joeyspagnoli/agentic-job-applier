# fetch-004: pi-mono primary source

**Date:** 2026-05-22
**Sources fetched:**
- https://github.com/earendil-works/pi (README)
- https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/README.md
- https://github.com/badlogic/pi-mono/blob/main/packages/agent/README.md (pi-agent-core)
- https://github.com/badlogic/pi-mono/blob/main/packages/ai/README.md (pi-ai)
- https://deepwiki.com/badlogic/pi-mono (top-level wiki)
- https://deepwiki.com/badlogic/pi-mono/3-pi-agent-core:-agent-framework
- https://deepwiki.com/badlogic/pi-mono/4.7-model-resolution-and-thinking-levels
- https://deepwiki.com/badlogic/pi-mono/6-pi-web-ui:-web-ui-components

## 1) What pi-mono is

A TypeScript monorepo of five npm packages that together form a "complete agent infrastructure stack where every layer is independently usable." Created by Mario Zechner (badlogic / libGDX). Originally `badlogic/pi-mono`, now hosted under `earendil-works/pi`, with packages published under both `@mariozechner/*` (legacy) and `@earendil-works/*` (current).

The repo description: **"AI agent toolkit: coding agent CLI, unified LLM API, TUI & web UI libraries, Slack bot, vLLM pods."**

## 2) Package layout

DeepWiki top-level structure (8 sections):

1. Overview
2. Monorepo Structure
3. **pi-ai** — LLM API library
4. **pi-agent-core** — Agent framework
5. **pi-coding-agent** — Coding agent CLI (13 subsections)
6. **pi-tui** — Terminal UI library
7. **pi-web-ui** — Web UI components
8. Development & Contributing

| Package | Role |
|---|---|
| `pi-coding-agent` | CLI application; also exports SDK (`AgentSession`, `SessionManager`, `SettingsManager`, `ModelRegistry`, `AuthStorage`, `createAgentSession`, `createAgentSessionRuntime`) |
| `pi-ai` | LLM abstraction layer for 20+ providers; exports `MODELS`, `AuthStorage`, `streamSimple`, `stream`, `complete` |
| `pi-agent-core` | Reusable agent framework with transport abstraction; exports `Agent`, `agentLoop`, `agentLoopContinue`, `AgentContext`, `AgentTool`, `AgentMessage` |
| `pi-tui` | Terminal rendering library with differential updates |
| `pi-web-ui` | Browser-based chat components (mini-lit + Tailwind), no DOM tools built in |

## 3) pi-ai — providers and models

From the package README, supported providers (20+):

> OpenAI, Azure OpenAI, OpenAI Codex, Anthropic, Google, Vertex AI, DeepSeek, Mistral, Groq, Cerebras, xAI, Fireworks, Together AI, Cloudflare (AI Gateway & Workers AI), GitHub Copilot, Amazon Bedrock, OpenRouter, Vercel AI Gateway, MiniMax, OpenCode Zen/Go, Kimi For Coding, Xiaomi MiMo, and "Any OpenAI-compatible API"

Hard requirement: **every supported model must support tool-calling** (the runtime assumes tool-use is available).

Confirmed small/cheap models in registry:
- **GPT-4o mini** (OpenAI) — quick-start example uses `getModel('openai', 'gpt-4o-mini')`
- **Claude 3.5 Haiku** (Anthropic)
- **Gemini 2.5 Flash** (Google)
- (Implied: gpt-5-mini, gemini flash variants, groq llama-small, cerebras llama, deepseek-chat, etc., via the same registry)

Standalone APIs (no agent loop needed):

```js
// Streaming
const s = stream(model, context);
for await (const event of s) { /* events */ }
const finalMessage = await s.result();

// Non-streaming
const response = await complete(model, context);
```

Tool definitions (TypeBox):

```js
const tools = [{
  name: 'get_weather',
  description: 'Get current weather for a location',
  parameters: Type.Object({
    location: Type.String({ description: 'City name' }),
    units: StringEnum(['celsius', 'fahrenheit'])
  })
}];
```

### Model resolution & thinking levels (DeepWiki 4.7)

`ModelResolver` strategies:
1. Exact ID match: `claude-sonnet-4-5`
2. Provider/ID: `anthropic/claude-sonnet-4-5`
3. Fuzzy: `sonnet` matches any model containing the substring
4. Thinking-level suffix: `sonnet:high` appends reasoning depth

`ModelRegistry` has built-in models (from provider catalogs) **plus** user-defined `~/.pi/agent/models.json`. Custom `baseUrl` and `headers` can override existing providers without redefining all their models. Config values support shell-command `!command` and env-var resolution.

Six unified thinking levels: `off`, `minimal`, `low`, `medium`, `high`, `xhigh`. They map per-provider — e.g. on OpenAI they translate to `reasoning_effort: minimal/.../xhigh`; on Anthropic, to budget tokens; on DeepSeek/Together via `thinkingLevelMap`. **This is exactly the knob you'd use to push easy field-fill decisions to `minimal/low` and only escalate to `high` when stuck.**

## 4) pi-agent-core — the runtime

Stateful machine that owns a multi-turn conversation cycle including LLM calls and tool execution.

### Architecture (DeepWiki section 3)

- `Agent` class fields: `_state: MutableAgentState`, `steeringQueue: PendingMessageQueue`, `followUpQueue: PendingMessageQueue`
- Functional entry: `agentLoop()` (used internally; also exported)
- Pipeline: `transformContext` (context optimization, e.g. compaction) → `convertToLlm` (filter messages before send) → LLM call → tool execution → repeat
- Tool execution lifecycle, in order:
  1. `tool_execution_start` event
  2. `beforeToolCall` hook
  3. Tool invocation
  4. `afterToolCall` hook
  5. `tool_execution_end` event
- Execution modes: `parallel` (default) or `sequential`
- Lifecycle events include: `message_update` (streaming text deltas), `turn_end`, `tool_execution_*`, `agent_end`
- Stateful: `Agent` keeps `MutableAgentState`; `AgentHarness` preserves history through `Session` layer (tree-based branching + JSONL persistence)

### High-level Agent API (verbatim from README)

```js
await agent.prompt("Hello");
await agent.prompt("What's in this image?", [
  { type: "image", data: base64Data, mimeType: "image/jpeg" }
]);
await agent.prompt({ role: "user", content: "Hello", timestamp: Date.now() });
await agent.continue();

agent.state.systemPrompt = "New prompt";
agent.state.model = getModel("openai", "gpt-4o");
agent.state.thinkingLevel = "medium";
agent.state.tools = [myTool];
agent.toolExecution = "sequential";
agent.state.messages = newMessages;
agent.reset();

agent.abort();
await agent.waitForIdle();
const unsubscribe = agent.subscribe(async (event, signal) => {
  if (event.type === "agent_end") {
    await flushSessionState(signal);
  }
});
```

### Custom tool API (verbatim)

```js
const readFileTool: AgentTool = {
  name: "read_file",
  label: "Read File",
  description: "Read a file's contents",
  parameters: Type.Object({
    path: Type.String({ description: "File path" }),
  }),
  executionMode: "sequential",
  execute: async (toolCallId, params, signal, onUpdate) => {
    const content = await fs.readFile(params.path, "utf-8");
    onUpdate?.({ content: [{ type: "text", text: "Reading..." }], details: {} });
    return {
      content: [{ type: "text", text: content }],
      details: { path: params.path, size: content.length },
    };
  },
};

agent.state.tools = [readFileTool];
```

Tool result shape: `{ content: ContentBlock[], details: object }` (content is the LLM-visible payload; details are extra metadata for UI rendering).

### Custom message types (declaration merging)

```ts
declare module "@earendil-works/pi-agent-core" {
  interface CustomAgentMessages {
    notification: { role: "notification"; text: string; timestamp: number };
  }
}

const msg: AgentMessage = { role: "notification", text: "Info", timestamp: Date.now() };
```

You can interleave domain-specific events (e.g. `page_observed`, `simplify_fill_complete`) into the message stream and decide in `convertToLlm` whether to forward them to the LLM.

### Embedding without the CLI (verbatim)

```js
import { agentLoop, agentLoopContinue } from "@earendil-works/pi-agent-core";

const context: AgentContext = {
  systemPrompt: "You are helpful.",
  messages: [],
  tools: [],
};

const config: AgentLoopConfig = {
  model: getModel("openai", "gpt-4o"),
  convertToLlm: (msgs) =>
    msgs.filter(m => ["user", "assistant", "toolResult"].includes(m.role)),
  toolExecution: "parallel",
  beforeToolCall: async ({ toolCall, args, context }) => undefined,
  afterToolCall: async ({ toolCall, result, isError, context }) => undefined,
};

const userMessage = { role: "user", content: "Hello", timestamp: Date.now() };

for await (const event of agentLoop([userMessage], context, config)) {
  console.log(event.type);
}

for await (const event of agentLoopContinue(context, config)) {
  console.log(event.type);
}
```

**This is the load-bearing snippet for the job-applier use case.** Embedding pi-agent-core means: build an `AgentContext` with your custom tools (DOM read/click/type), give it a small model via `getModel`, drive it with `agentLoop`, and gate the tool stream with `beforeToolCall` to enforce hard rules (e.g. "never click Submit").

## 5) pi-coding-agent — CLI and SDK

Built-in tools shipped by default: `read`, `write`, `edit`, `bash` (plus `grep`, `find`, `ls` as additional built-ins). The system prompt is intentionally under 1000 tokens — much smaller than competitor agents.

Operating modes:
- Interactive TUI (default)
- **Print mode** (`-p`) — non-interactive, prints final answer and exits (good for scripted use)
- **JSON mode** (`--mode json`) — emits all events as JSON lines (good for parent processes)
- **RPC mode** (`--mode rpc`) — stdin/stdout RPC protocol (good for embedded use, with a documented protocol at `packages/coding-agent/docs/rpc.md`)

SDK exports:

```js
import {
  AuthStorage,
  createAgentSession,
  createAgentSessionRuntime,
  ModelRegistry,
  SessionManager,
  SettingsManager,
  AgentSessionRuntime,
} from "@earendil-works/pi-coding-agent";

const { session } = await createAgentSession({
  model,
  customTools: [deployTool],
  sessionManager: SessionManager.inMemory(),
});
```

`createAgentSession` is the canonical entry for embedding a full session (with persistence, extension loading, defaults) into another app. Persistence is optional — `SessionManager.inMemory()` keeps everything ephemeral, which matters for a Chrome extension that wants per-tab sessions without writing to disk.

## 6) pi-web-ui — what it covers and doesn't

Reusable web components for browser-based AI chat (mini-lit + Tailwind):
- `ChatPanel` — orchestrator with chat history + artifact previews
- `MessageList` + custom renderers
- `StreamingMessageContainer`
- Tool renderer registry for custom tool output visualization
- `SandboxIframe` for sandboxed code execution via message bridging
- IndexedDB storage for sessions, API keys, settings
- CORS proxy support for LLM requests in the browser

It bridges UI to `pi-agent-core` via an `AgentInterface` component but **does not itself run the agent loop, and ships no DOM-observation or DOM-manipulation tools.** No Chrome extension or side-panel scaffolding either.

## 7) Extension system

From the coding-agent README (verbatim shape):

```ts
export default function (pi: ExtensionAPI) {
  pi.registerTool({ name: "deploy", ... });
  pi.registerCommand("stats", { ... });
  pi.on("tool_call", async (event, ctx) => { ... });
}
```

Extensions can:
- Replace built-in tools entirely (e.g. remove `bash` for a browser context)
- Add custom UI components
- Implement sub-agents and plan modes
- Gate permissions and manage credentials
- Hook every lifecycle event (`tool_call`, `before_agent_start`, etc.)
- Be async at the default export for one-time init

The default export can also be async, enabling one-time initialization before startup continues.

## 8) Language and runtime

TypeScript 93.4% of the codebase. Node-targeted but the agent-core and ai packages are written portably enough that Chrome-extension and Cloudflare-Workers ports already exist in the wild (`funtuan/pi-agent-cf`, ChromeClaw service worker).

License: MIT.
