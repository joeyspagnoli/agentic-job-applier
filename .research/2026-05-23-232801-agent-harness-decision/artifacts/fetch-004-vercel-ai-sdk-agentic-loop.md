# Vercel AI SDK — Agentic Loop Control (Full Documentation)

**Source:** https://ai-sdk.dev/docs/agents/loop-control + https://ai-sdk.dev/docs/agents/building-agents  
**Fetched:** 2026-05-24

---

## Loop Control Primitives

Two parameters control agent execution:
- `stopWhen` — defines stopping conditions
- `prepareStep` — modifies settings between steps

Default safety limit: **20 steps** (`stopWhen: stepCountIs(20)`).

---

## Stop Conditions (`stopWhen`)

### Built-in Conditions

```typescript
import { stepCountIs, hasToolCall, isLoopFinished } from 'ai';

// Stop after N steps
stopWhen: stepCountIs(50)

// Stop when a specific tool is invoked
stopWhen: hasToolCall('done')

// Run until naturally finished (no step limit — use with caution)
stopWhen: isLoopFinished()

// Combine multiple conditions
stopWhen: [stepCountIs(20), hasToolCall('someTool')]
```

### Custom Stop Conditions

```typescript
const hasAnswer = ({ steps }) => {
  return steps.some(step => step.text?.includes('ANSWER:')) ?? false;
};

// Budget-based stopping
const budgetExceeded = ({ steps }) => {
  const totalTokens = steps.reduce(
    (sum, step) => sum + (step.usage?.totalTokens ?? 0), 0
  );
  const costEstimate = totalTokens * 0.000015; // Rough Sonnet rate
  return costEstimate > 0.10;
};
```

---

## `prepareStep` Callback

Executes before each iteration. Enables dynamic modifications based on execution history.

### Dynamic Model Selection

```typescript
prepareStep: async ({ stepNumber, messages }) => {
  if (stepNumber > 2 && messages.length > 10) {
    return { model: "anthropic/claude-sonnet-4.5" };
  }
  return {};
}
```

### Context Management (Trim Growing History)

```typescript
prepareStep: async ({ messages }) => {
  if (messages.length > 20) {
    return {
      messages: [
        messages[0],       // Keep system message
        ...messages.slice(-10),  // Keep last 10
      ],
    };
  }
  return {};
}
```

### Tool Selection Per Step

```typescript
prepareStep: async ({ stepNumber }) => {
  if (stepNumber <= 2) {
    return { activeTools: ['search'], toolChoice: 'required' };
  }
  if (stepNumber <= 5) {
    return { activeTools: ['analyze'] };
  }
  return { activeTools: ['summarize'], toolChoice: 'required' };
}
```

---

## `onStepFinish` Callback

Fires after each LLM step. Access token usage, tool calls, finish reason:

```typescript
const result = await myAgent.generate({
  prompt: 'Research and summarize the latest AI trends',
  onStepFinish: async ({ stepNumber, usage, finishReason, toolCalls }) => {
    console.log(`Step ${stepNumber} completed:`, {
      inputTokens: usage.inputTokens,
      outputTokens: usage.outputTokens,
      finishReason,
      toolsUsed: toolCalls?.map(tc => tc.toolName),
    });
  },
});
```

### "No Submit" Guardrail Using `onStepFinish`

```typescript
// NOTE: onStepFinish is OBSERVATIONAL only — it cannot block tool calls
// It fires AFTER the tool call has already been decided
// To block a tool call in Vercel AI SDK, you must use a tool without an execute function

const result = await generateText({
  model: "anthropic/claude-sonnet-4.5",
  tools: {
    click: tool({
      description: 'Click an element by selector',
      inputSchema: z.object({ selector: z.string() }),
      execute: async ({ selector }) => {
        if (selector.toLowerCase().includes('submit')) {
          throw new Error('Submit buttons are forbidden'); // Stops the loop
          // Better: check before handing to execute, or use the no-execute pattern
        }
        return await browserClick(selector);
      },
    }),
  },
  stopWhen: stepCountIs(25),
});
```

**Critical limitation:** `onStepFinish` cannot block a step — it only observes. The guardrail must live inside the tool's `execute` function or by using a tool without an execute function (forces `staticToolCalls`).

---

## Forced Tool Pattern (Structured Completion)

```typescript
const agent = new ToolLoopAgent({
  model: "anthropic/claude-sonnet-4.5",
  tools: {
    search: searchTool,
    done: tool({
      description: 'Signal task completion with an answer',
      inputSchema: z.object({ answer: z.string() }),
      // No execute function — loop stops when this tool is called
    }),
  },
  toolChoice: 'required',
});

// Access the tool call that stopped the loop
const toolCall = result.staticToolCalls[0];
if (toolCall?.toolName === 'done') {
  console.log(toolCall.input.answer);
}
```

---

## `generateText` with `stopWhen` (Functional Style)

```typescript
import { generateText, stepCountIs } from 'ai';

const { text } = await generateText({
  model: 'anthropic/claude-haiku-4.5',
  prompt: 'Research and summarize AI trends',
  tools: { /* ... */ },
  stopWhen: stepCountIs(10),
  onStepFinish: async ({ toolResults }) => {
    if (toolResults.length) {
      console.log(JSON.stringify(toolResults, null, 2));
    }
  },
});
```

---

## `prepareStep` Inputs Available

```typescript
prepareStep: async ({
  model,
  stepNumber,
  steps,      // Full step history
  messages,   // All messages
}) => {
  const previousToolCalls = steps.flatMap(s => s.toolCalls);
  const previousResults = steps.flatMap(s => s.toolResults);
  return {};
}
```

---

## Summary: Loop Control vs Claude Agent SDK Hooks

| Feature | Vercel AI SDK | Claude Agent SDK |
|---------|--------------|-----------------|
| Pre-tool interception | Only inside `execute` function | `PreToolUse` hook (external, before execution) |
| Post-tool observation | `onStepFinish` | `PostToolUse` hook |
| Block a tool call | Must throw inside `execute` or use no-execute tool | `permissionDecision: "deny"` in hook |
| Stop conditions | `stopWhen: [...]` built-ins + custom functions | `max_turns`, `max_budget_usd` |
| Per-step modification | `prepareStep` callback | N/A (single query() call) |
| Language | TypeScript only | Python + TypeScript |
