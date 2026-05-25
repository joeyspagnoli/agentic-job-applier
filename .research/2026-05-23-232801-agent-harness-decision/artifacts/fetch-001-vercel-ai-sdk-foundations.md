# Vercel AI SDK — Foundations Overview

**Source:** https://ai-sdk.dev/docs/foundations  
**Fetched:** 2026-05-24

---

## Foundations Topics

The Foundations section covers six core concept areas:

1. **Overview** — Foundational concepts around AI and LLMs
2. **Providers and Models** — Available providers and models
3. **Prompts** — How prompts are used and defined
4. **Tools** — Tool definitions and usage
5. **Streaming** — Why streaming is used for AI applications
6. **Provider Options** — Provider-specific options for reasoning, caching, etc.

## Navigation Structure

The SDK documentation is organized into:
- Getting Started (Next.js, Svelte, Vue.js, Node.js, Expo, TanStack Start, Coding Agents)
- Agents section (Building, Workflows, Loop Control, Memory, Subagents)
- AI SDK Core (Text generation, structured data, tool calling, embeddings, image generation)
- AI SDK UI (Chatbot, streaming, message persistence)
- Reference documentation and migration guides

## Platform

Vercel AI SDK is a TypeScript-first library. Install via:

```bash
npm install ai
# or
pnpm add ai
```

After installation, full documentation and source code are available locally in `node_modules/ai/`.

## Key Abstractions

- `generateText` — one-shot text generation with tool calling
- `streamText` — streaming text generation with tool calling
- `ToolLoopAgent` class — encapsulates model + tools + loop
- `tool()` helper — define tools with Zod input schemas
- `stopWhen` — stopping conditions for agent loops
- `prepareStep` — modify settings between steps
- `onStepFinish` — callback after each step

## Key Fact for This Project

Vercel AI SDK is **TypeScript-only**. There is no official Python SDK. This is the decisive constraint for Python-based apply-worker integration.
