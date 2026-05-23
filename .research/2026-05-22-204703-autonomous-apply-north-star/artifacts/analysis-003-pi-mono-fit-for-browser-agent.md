# analysis-003 — pi-mono fit for the browser job-applier agent

**Date:** 2026-05-22  
**Built on:** search-004, gh-001, fetch-004, fetch-005 (this pass)  
**Verdict (1 sentence):** **pi-mono is real, well-maintained, and the right shape — Mario Zechner's TypeScript agent monorepo (`badlogic/pi-mono` → `earendil-works/pi`, 52,971 ⭐, MIT, pushed today); use `@earendil-works/pi-agent-core` as the headless agent loop and write your own DOM tools — but the language boundary (TS vs. our Python worker) is a real cost and should be weighed against replicating the same pattern in Python.**

---

## What pi-mono is — verified facts

| Property | Value |
|---|---|
| Canonical repo | `badlogic/pi-mono` → moved to `earendil-works/pi` |
| Stars | 52,971 (+12,999 in May 2026 alone) |
| Primary language | TypeScript (93.4%) |
| License | MIT |
| Last push | 2026-05-22 22:16 UTC (today) |
| Maintainer | Mario Zechner (badlogic, libGDX) |
| npm scopes | `@mariozechner/*` (legacy), `@earendil-works/*` (current) |

User's spelling was correct. **Not** "phi" (Microsoft's small models). **Not** "Pi" (Inflection's chatbot). **Not** an org named `principal-labs` or `pi-labs` (neither exists with this repo). High confidence on identification.

Package map (from `fetch-004` + `fetch-005`):
- `@earendil-works/pi-ai` — provider registry covering 20+ LLM providers (OpenAI, Anthropic, Google, Groq, Cerebras, DeepSeek, Together, Ollama, and a `~/.pi/agent/models.json` extension point for user-defined providers).
- `@earendil-works/pi-agent-core` — the **headless** agent loop: tool calling, message types, hooks (`beforeToolCall` / `afterToolCall`), streaming events, abort/idle semantics, JSONL session branching, thinking-level mapping.
- `@earendil-works/pi-coding-agent` — opinionated CLI + embeddable SDK (sits on top of `pi-agent-core`).
- `@earendil-works/pi-tui` and `@earendil-works/pi-web-ui` — UI surfaces; **not needed** for our worker.

---

## How it would slot into the autonomous job-applier

### 1. See
Register a `read_dom` AgentTool (custom). Its `execute()` returns the page snapshot — text + screenshot via tool-result content blocks (the protocol supports multimodal tool results).

### 2. Decide
`pi-agent-core` runs the canonical loop: LLM call → tool calls → tool results → repeat. Swap model mid-conversation via `agent.state.model = getModel("openai", "gpt-5-mini")`. Six thinking levels (`off/minimal/low/medium/high/xhigh`) — default to `minimal` for cheap decisions, escalate on observed loop.

### 3. Act
Register `type_text`, `click`, `select_option`, `wait_for_navigation` tools. Their `execute()` bridges to Chrome via CDP (ChromeClaw-style) or the existing Playwright session.

### 4. Stop before Submit
`beforeToolCall` hook is the right gate — throw on Submit clicks so the agent sees a tool error and continues. Combine with a `before_agent_start` hook that injects the no-Submit rule every turn. Belt + suspenders with our snapshot filter (see `analysis-004`).

### 5. Cost dial
Model registry includes gpt-5-mini, gpt-4o-mini, Claude 3.5 Haiku, Gemini 2.5 Flash, plus Groq/Cerebras/DeepSeek/Together small Llamas. Pick the floor with `thinking: "minimal"`; only escalate if `afterToolCall` detects a loop.

---

## Concrete embedding shape (from `fetch-004`)

**Headless loop pattern:**
```ts
import { agentLoop } from "@earendil-works/pi-agent-core";

const context: AgentContext = {
  systemPrompt: APPLY_SYSTEM_PROMPT,
  messages: [],
  tools: [readDomTool, typeTextTool, clickTool, selectOptionTool],
};

const config: AgentLoopConfig = {
  model: getModel("openai", "gpt-5-mini"),
  toolExecution: "sequential",
  beforeToolCall: async ({ toolCall, args }) => {
    if (toolCall.name === "click" && isSubmitButton(args.selector)) {
      throw new Error("BLOCKED: Submit click is disabled");
    }
  },
  afterToolCall: async ({ toolCall, result, isError }) => {
    // persist + budget + loop-detection
  },
  convertToLlm: (msgs) =>
    msgs.filter((m) => ["user", "assistant", "toolResult"].includes(m.role)),
};

for await (const event of agentLoop([userMessage], context, config)) {
  emitToUI(event);
}
```

**Full session pattern (preferred for extensions + persistence):**
```ts
import { createAgentSession, SessionManager } from "@earendil-works/pi-coding-agent";

const { session } = await createAgentSession({
  model: getModel("openai", "gpt-5-mini"),
  customTools: [readDomTool, typeTextTool, clickTool, selectOptionTool],
  sessionManager: SessionManager.inMemory(),
});
```

---

## Why this beats rolling our own loop

- Agent loop, message types, tool lifecycle, parallel/sequential dispatch, streaming events, abort/idle semantics, JSONL session branching — all paid for and battle-tested at 52K stars of usage.
- Provider registry handles auth, model resolution, and thinking-level mapping for 20+ vendors.
- Custom message types via declaration merging let you emit `simplify_fill_complete` / `page_observed` events the UI renders but the LLM never sees.
- `--mode rpc` (documented protocol) gives a stdio side-channel for non-Node hosts — i.e., our Python worker can drive a long-running pi-mono process via JSON-RPC over stdin/stdout instead of spinning a process per turn.
- Production precedent: `algopian/chromeclaw` already wires pi-mono inside a Chrome extension with CDP-backed DOM tools — nearly exactly our target deployment shape.

---

## What pi-mono does NOT give you for free

- **No DOM tools.** You write `read_dom`, `click`, `type_text` yourself (or borrow the patterns from `algopian/chromeclaw` / `vercel-labs/agent-browser`).
- **No shadow-root / iframe handling.** That's the tool layer's job; Chrome's `Accessibility.getFullAXTree` (see `analysis-001`) handles it for free.
- **No request batching.** Cost dial = model + thinking level, not batching.
- **No built-in token-budget circuit breakers.** Implement via `afterToolCall` — easy.
- **Hard requirement: tool-calling support on every model.** Stick to mini / Haiku / Flash / Groq-Llama tier.
- **The stateful `Agent` class assumes single-conversation ownership.** One Agent instance per tab/worker.

---

## The TypeScript-vs-Python integration cost

This is the one piece of news the user should hear plainly: **the rest of our worker is Python**.

Options:

1. **`pi-agent-core` over JSON-RPC subprocess.** Long-running Node child process; Python sends `apply(url, profile)` calls, Node returns event streams. ~1 process per worker shard; clean isolation. Costs: extra runtime dep (Node 24+), more deploy complexity, and per-message marshaling overhead.
2. **In-process Python re-implementation of the same patterns.** `agent_loop()`, `before_tool_call`, `after_tool_call`, `getModel(provider, model)`, six thinking levels — none of this is conceptually hard. The reason to use pi-mono is to avoid writing + maintaining it. Costs: maintenance forever, but no language boundary, no extra binary.
3. **Skip both pi-mono and own-loop — use the Anthropic SDK directly + a small dispatcher.** Plain Python, `anthropic.Messages.create(...)` + tool-use schema. ~300 lines. Costs: rebuild the conveniences pi-mono gives (hooks, session branching, multi-provider) when you eventually want them.

I lean toward **option 1 (JSON-RPC subprocess)** for the first cut: it borrows pi-mono's battle-tested loop and pays the language-boundary cost only at IPC time, which is dwarfed by the LLM call latency anyway. See `analysis-004` for the full integration story.

---

## Risk table

| Risk | Mitigation |
|---|---|
| Workday / Greenhouse shadow roots break a naive DOM serializer | Use the `Accessibility.getFullAXTree` snapshot pattern from `analysis-001` — pierces shadow roots natively |
| Per-apply cost balloons on loop | `beforeToolCall` enforces max-iterations; switch thinking level only on observed loop |
| Auto-submit slips through | Belt + suspenders: snapshot filter + `beforeToolCall` gate + per-host allowlist + system-prompt directive + (optional) human-approval message in `steeringQueue` |
| pi-mono's "self-modifying agent" philosophy clashes with locked-down apply | Don't enable `bash` or extension-write tools; agent only sees the DOM tools you register |
| 10–50 sequential turns @ 30–120 s | Stream events to UI; one Agent per tab for concurrency |
| Namespace migration | Pin to `@earendil-works/*`; ignore legacy `@mariozechner/*` snippets |

---

## Verdict

**Fit: strong.** `pi-agent-core` is the smallest credible runtime that already solves model abstraction, tool calling, streaming, hooks, sessions, and lifecycle gating — without forcing a particular UI or coupling to bash/filesystem. The Chrome-extension deployment shape is proven by `algopian/chromeclaw`, and `agentLoop()` is clean enough to live inside any background worker.

**Recommendation order** (if I'm wrong about user intent or it turns out pi-mono is the wrong shape for our worker):

1. **`@earendil-works/pi-agent-core` + `@earendil-works/pi-ai`** — headless slice of pi-mono. Default choice.
2. **OpenAI Agents SDK / Claude Agent SDK** — official, similar primitives, single-provider lock-in.
3. **`browser-use` (Python) or `Stagehand` (Browserbase, TS)** — browser tools included out of the box; both are "LLM drives browser" libraries vs. pi-mono's "LLM drives anything we register" generality.
4. **LangGraph + small model** — heavier ceremony, popular in Python.
5. **Magentic-One** — multi-agent + browser, Python-only, heavier.

Most likely-misheard alternatives if the user meant something else: **"Phi"** (Microsoft small models — not an agent framework) and **"Pi"** (Inflection chatbot — not developer-facing). Neither has a "mono" flavor or fits the "agent monorepo" shape. **pi-mono identification stands.**

See `analysis-004-north-star-synthesis.md` for how pi-mono interleaves with Simplify (`analysis-002`) and agent-browser (`analysis-001`) into a single architecture.
