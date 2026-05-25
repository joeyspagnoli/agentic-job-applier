# Vercel AI SDK for Browser-Fill Agent Use Case
## Primary-Source Deep Dive Analysis

**Date:** 2026-05-24  
**Repo:** agentic-job-applier  
**Use Case:** Python apply-worker with 6 browser tools, 5-25 turns per apply, $0.01-0.10/apply budget, strict "never submit" guardrail, CDP-attached Chromium + Simplify Copilot extension.

---

## 1. What It Is

The Vercel AI SDK is a **TypeScript unified provider abstraction** for building AI-powered applications. It ships as the `ai` npm package plus per-provider adapters (`@ai-sdk/anthropic`, `@ai-sdk/openai`, etc.).

Core functions:
- `generateText({ model, tools, stopWhen, prepareStep })` — one-shot with multi-turn tool loop
- `streamText(...)` — streaming variant
- `ToolLoopAgent` class — encapsulates model + tools + loop config for reuse
- `tool()` helper — define tools with Zod input schemas

It is mature (v4/v6 series), Apache 2.0 licensed, maintained by Vercel. Well-suited for Next.js/Node.js stacks. 50+ community providers.

---

## 2. Loop Primitive

### `generateText` with `stopWhen`

```typescript
import { generateText, stepCountIs, tool } from 'ai';
import { anthropic } from '@ai-sdk/anthropic';
import { z } from 'zod';

const { text } = await generateText({
  model: anthropic('claude-sonnet-4-6'),
  tools: {
    browserSnapshot: tool({
      description: 'Take screenshot of current page',
      inputSchema: z.object({}),
      execute: async () => {
        const img = await browser.screenshot();
        return { base64: img.toString('base64') };
      },
    }),
    browserClick: tool({
      description: 'Click element by CSS selector',
      inputSchema: z.object({ selector: z.string() }),
      execute: async ({ selector }) => {
        // Guard lives here — no SDK-level pre-execution hook
        if (selector.toLowerCase().includes('submit')) {
          return { blocked: true, reason: 'Submit forbidden by policy' };
        }
        await browser.click(selector);
        return { clicked: selector };
      },
    }),
    // ... 4 more tools
  },
  stopWhen: stepCountIs(25),
  prompt: 'Fill out the job application at https://...',
});
```

### `ToolLoopAgent` Class

```typescript
import { ToolLoopAgent, stepCountIs } from 'ai';

const applyAgent = new ToolLoopAgent({
  model: anthropic('claude-sonnet-4-6'),
  tools: { browserSnapshot, browserClick, browserType, browserSelect, browserWait, browserGoto },
  stopWhen: stepCountIs(25),      // Default is stepCountIs(20)
  onStepFinish: async ({ stepNumber, usage }) => {
    await logStep(stepNumber, usage);
  },
});

const result = await applyAgent.generate({ prompt: 'Apply to job at ...' });
console.log(result.text);   // final answer
console.log(result.steps);  // all steps taken
```

---

## 3. Hooks: `onStepFinish` and `prepareStep`

### `onStepFinish` — Observational Only

```typescript
onStepFinish: async ({ stepNumber, usage, finishReason, toolCalls }) => {
  // Fires AFTER step completes. Cannot block tool calls.
  const submitAttempts = toolCalls?.filter(
    tc => tc.toolName === 'browserClick' && tc.input.selector?.includes('submit')
  );
  if (submitAttempts?.length) {
    await alertOps(`SUBMIT ATTEMPTED at step ${stepNumber} — too late to block`);
  }
}
```

**Critical limitation:** `onStepFinish` fires after execution is committed. It is observational only. To refuse a tool call, the guard must live **inside each tool's `execute` function** individually. There is no SDK-level pre-execution interception equivalent to Claude Agent SDK's `PreToolUse`.

### `prepareStep` — Dynamic Loop Modification

```typescript
prepareStep: async ({ stepNumber, messages }) => {
  if (stepNumber > 3) {
    return { model: anthropic('claude-haiku-4-5') }; // Downgrade model mid-run
  }
  if (messages.length > 30) {
    return { messages: [messages[0], ...messages.slice(-15)] }; // Trim context
  }
  return {};
}
```

`prepareStep` is useful for cost management (switch to cheaper model after planning phase) and context trimming, but provides no tool interception.

---

## 4. Provider Abstraction

Swap providers by changing one `model` argument:

```typescript
const model = anthropic('claude-sonnet-4-6');
// const model = openai('gpt-4o');
// const model = bedrock('anthropic.claude-3-5-sonnet-20241022-v2:0');
```

Official providers: OpenAI, Anthropic, Azure OpenAI, Google Gemini, Google Vertex, Amazon Bedrock, Groq, Mistral, Cohere, DeepSeek, Together.ai, Fireworks, Hugging Face. Community: 50+, including Ollama, OpenRouter.

For this project (Anthropic-only), provider portability provides no benefit.

---

## 5. License and Maturity

- **License:** Apache 2.0
- **Version:** v4.x core / v6 provider API
- **Maintained by:** Vercel (well-funded, production-grade)
- **Language:** TypeScript/Node.js only — no Python SDK exists or is planned

---

## 6. The Python Interop Problem

The Vercel AI SDK is **TypeScript-only**. The `ai` package is npm-only. Three integration paths exist:

### Option A: Full TypeScript Rewrite of Worker — NO

Rewrite ~2,000+ lines of Python into TypeScript: asyncio → Node event loop, `playwright` Python → Node, CDP attachment, job queue, retry logic, all existing tests.

- **Estimate:** 3-6 weeks minimum
- **Risk:** Destroys existing working infrastructure
- **Gain:** Access to Vercel AI SDK; no other benefit for Anthropic-only Python worker

**Verdict: Not justified.**

### Option B: Node Sidecar via JSON-RPC — Significant Lift

Python worker spawns a Node.js process running the Vercel AI SDK. Tool execution round-trips: Python → Node (model call) → Python (tool execution, because CDP is Python-native) → Node (continue loop).

Problems:
- Subprocess lifecycle management per apply run (or long-lived sidecar with health checks)
- Bespoke JSON-RPC schema for tool registration and dispatch
- Tools must round-trip to Python anyway (CDP is Python-native, not portable)
- Two async runtimes (asyncio + Node event loop)
- Two error-propagation paths across process boundary
- ~200-500ms Node startup latency per apply

- **Estimate:** 1-2 weeks to build; ongoing maintenance burden
- **Gain:** None over using `anthropic` Python SDK directly

**Verdict: Adds infrastructure complexity for zero functional gain.**

### Option C: Reject Vercel AI SDK — Simplest

Use bare `anthropic` Python SDK (already at `anthropic==0.96.0`) or Claude Agent SDK (`pip install claude-agent-sdk`). No cross-language complexity.

- **Estimate:** 0 additional infrastructure work
- **Gain:** All existing Python tooling intact; full CDP integration stays in-process

**Verdict: Correct choice.**

---

## 7. Verdict

**Vercel AI SDK is "no" for this project.**

The language mismatch is fatal. Every integration path either destroys existing infrastructure (Option A) or adds complexity for zero gain (Option B). The guardrail story is also structurally weaker: blocking a submit requires patching each tool's `execute` function individually, versus a single `PreToolUse` hook in Claude Agent SDK that intercepts all tool calls centrally before execution.

The SDK's genuine strengths — provider portability, TypeScript ergonomics, rich npm ecosystem — are irrelevant to a Python-native CDP-based apply-worker using Anthropic exclusively.

**Recommendation: Reject Vercel AI SDK. Proceed with Claude Agent SDK (Python) or bare `anthropic` SDK.**

---

## Sources Verified

- fetch-001-vercel-ai-sdk-foundations.md (ai-sdk.dev/docs/foundations)
- fetch-002-vercel-ai-sdk-tools.md (ai-sdk.dev/docs/foundations/tools)
- fetch-003-vercel-ai-sdk-agents.md (ai-sdk.dev/docs/agents)
- fetch-004-vercel-ai-sdk-agentic-loop.md (ai-sdk.dev/docs/agents/loop-control)
- fetch-005-vercel-ai-sdk-providers.md (ai-sdk.dev/providers/ai-sdk-providers)
