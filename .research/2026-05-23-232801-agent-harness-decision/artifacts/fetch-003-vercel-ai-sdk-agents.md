# Vercel AI SDK — Agents Overview

**Source:** https://ai-sdk.dev/docs/agents (coding agents page) + https://ai-sdk.dev/docs/foundations/agents  
**Fetched:** 2026-05-24

---

## Core Concept

"Agents are large language models (LLMs) that use tools in a loop to accomplish tasks."

Three essential components:
- **LLMs** — Process input and determine next actions
- **Tools** — Extend capabilities beyond text generation
- **Loop** — Orchestrates execution through context management and stopping conditions

---

## ToolLoopAgent Class

```typescript
import { ToolLoopAgent, tool } from 'ai';
import { z } from 'zod';

const weatherAgent = new ToolLoopAgent({
  model: "anthropic/claude-sonnet-4.5",
  tools: {
    weather: tool({
      description: 'Get the weather in a location (in Fahrenheit)',
      inputSchema: z.object({
        location: z.string().describe('The location to get the weather for'),
      }),
      execute: async ({ location }) => ({
        location,
        temperature: 72 + Math.floor(Math.random() * 21) - 10,
      }),
    }),
    convertFahrenheitToCelsius: tool({
      description: 'Convert temperature from Fahrenheit to Celsius',
      inputSchema: z.object({
        temperature: z.number().describe('Temperature in Fahrenheit'),
      }),
      execute: async ({ temperature }) => {
        const celsius = Math.round((temperature - 32) * (5 / 9));
        return { celsius };
      },
    }),
  },
});

const result = await weatherAgent.generate({
  prompt: 'What is the weather in San Francisco in celsius?',
});

console.log(result.text);   // agent's final answer
console.log(result.steps);  // steps taken by the agent
```

---

## Agent Configuration Options

```typescript
const agent = new ToolLoopAgent({
  model: "anthropic/claude-sonnet-4.5",
  instructions: 'You are a helpful assistant.',
  tools: { /* ... */ },
  stopWhen: stepCountIs(50),      // Default is stepCountIs(20)
  toolChoice: 'required',         // or 'auto' (default), 'none'
  onStepFinish: async ({ stepNumber, usage, finishReason, toolCalls }) => {
    console.log(`Step ${stepNumber}:`, usage.totalTokens);
  },
});
```

---

## Agent Methods

```typescript
// One-time generation
const result = await agent.generate({ prompt: 'What is the weather?' });
console.log(result.text);

// Streaming
const result = await agent.stream({ prompt: 'Tell me a story' });
for await (const chunk of result.textStream) {
  process.stdout.write(chunk);
}
```

---

## For Coding Agents (Claude Code context)

Install the AI SDK skill:
```bash
npx skills add vercel/ai
```

Install DevTools for observability:
```bash
pnpm add @ai-sdk/devtools
```

```typescript
import { wrapLanguageModel, gateway } from 'ai';
import { devToolsMiddleware } from '@ai-sdk/devtools';

const model = wrapLanguageModel({
  model: gateway('anthropic/claude-sonnet-4.5'),
  middleware: devToolsMiddleware(),
});
```

DevTools captures all LLM requests, responses, tool calls, token usage, multi-step interactions.

---

## Alternative: `generateText` with Manual Loop

For complete control without `ToolLoopAgent`:

```typescript
const messages = [{ role: 'user', content: '...' }];
let step = 0;

while (step < maxSteps) {
  const result = await generateText({
    model: "anthropic/claude-sonnet-4.5",
    messages,
    tools: { /* tools */ },
  });

  messages.push(...result.response.messages);
  if (result.text) break;
  step++;
}
```

---

## Key Note

`ToolLoopAgent` is the high-level abstraction. `generateText` / `streamText` with `stopWhen` is the lower-level manual approach. Both are TypeScript-only.
