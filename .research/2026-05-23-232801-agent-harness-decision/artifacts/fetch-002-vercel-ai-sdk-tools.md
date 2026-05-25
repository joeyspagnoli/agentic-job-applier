# Vercel AI SDK — Tools (Full Documentation)

**Source:** https://ai-sdk.dev/docs/foundations/tools  
**Fetched:** 2026-05-24

---

## What is a Tool?

"A tool is an object that can be called by the model to perform a specific task."

Tools are passed to `generateText` and `streamText` via the `tools` parameter.

Each tool has three components:
- **description**: Optional text influencing when the model selects the tool
- **inputSchema**: Zod or JSON schema defining required inputs and validating LLM calls
- **execute**: Optional async function processing tool call arguments

---

## Three Types of Tools

### 1. Custom Tools (Provider-Agnostic)

```javascript
import { tool } from 'ai';
import { z } from 'zod';

const weatherTool = tool({
  description: 'Get the weather in a location',
  inputSchema: z.object({
    location: z.string().describe('The location to get the weather for'),
  }),
  execute: async ({ location }) => {
    return { temperature: 72, conditions: 'sunny' };
  },
});
```

Use when: full control needed, provider portability required, application-specific functionality.

### 2. Provider-Defined Tools

Provider specifies the tool's inputSchema and description; you provide the execute function.

```javascript
import { anthropic } from '@ai-sdk/anthropic';
import { generateText } from 'ai';

const result = await generateText({
  model: anthropic('claude-opus-4-5'),
  tools: {
    bash: anthropic.tools.bash_20250124({
      execute: async ({ command }) => {
        return runCommand(command);
      },
    }),
  },
  prompt: 'List files in the current directory',
});
```

### 3. Provider-Executed Tools

Run entirely on provider's servers; provider handles execution.

```javascript
import { openai } from '@ai-sdk/openai';
import { generateText } from 'ai';

const result = await generateText({
  model: openai('gpt-5.2'),
  tools: {
    web_search: openai.tools.webSearch(),
  },
  prompt: 'What happened in the news today?',
});
```

---

## Supported Schemas

- Zod v3 and v4 directly or via `zodSchema()`
- Valibot via `valibotSchema()`
- Standard JSON Schema compatible schemas
- Raw JSON schemas via `jsonSchema()`

---

## Tool Packages (Ecosystem)

Ready-made npm packages:
- `@exalabs/ai-sdk` — Web search
- `@tavily/ai-sdk` — Search, extract, crawl, map
- Stripe agent tools — Stripe integration
- Composio — 250+ tools (GitHub, Gmail, Salesforce)
- Amazon Bedrock AgentCore — Browser and code interpreter
- Toolhouse — 25+ AI function-calling actions

MCP tool marketplaces:
- Smithery — 6,000+ MCPs
- Pipedream — 3,000+ integrations
- Apify — Web scraping and automation

---

## Key Difference vs Claude Agent SDK

The Vercel AI SDK's `tool()` helper is a **TypeScript** construct using Zod for schema validation. There is no Python equivalent. The Claude Agent SDK's `@tool` decorator serves an equivalent role in Python.
