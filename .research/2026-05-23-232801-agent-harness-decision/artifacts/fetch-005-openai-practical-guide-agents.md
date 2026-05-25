# Fetch 005: OpenAI — "A Practical Guide to Building Agents" (2024/2025)

**Primary URL:** https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/
**PDF URL:** https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf
**Supplementary:** https://developers.openai.com/tracks/building-agents and https://developers.openai.com/api/docs/guides/agents
**Fetched:** 2026-05-23
**Method:** WebFetch (PDF binary — fetched HTML version + Agents SDK docs page)

---

## Core definition

> "Agents are systems that independently accomplish tasks on your behalf. Agents use an LLM to execute instructions and make decisions. They have access to tools to gather context and take actions, always operating within clearly defined guardrails."
(source: developers.openai.com/tracks/building-agents)

> "An AI system that has instructions (what it _should_ do), guardrails (what it _should not_ do), and access to tools (what it _can_ do) to take action on the user's behalf."
(source: developers.openai.com/api/docs/guides/agents)

The key distinction from chatbots: "If you're building a chatbot-like experience where the AI system is answering questions, you can't really call it an agent. If that system, however, is connected to other systems, and taking action based on the user's input, that qualifies as an agent."

## The agentic loop ("run" concept)

OpenAI frames every agent execution as a **"run"**:

> "Every orchestration approach needs the concept of a 'run', typically implemented as a loop that lets agents operate until an exit condition is reached."

The loop structure:
1. Plan next steps
2. Call available tools
3. Process results (observe)
4. Maintain conversation state across turns
5. Continue until work completes

Exit conditions include: tool calls producing a terminal result, a certain structured output, errors, or reaching a maximum number of turns.

> "This concept of a while loop is central to the functioning of an agent."

## Tool use protocol

Two implementation approaches:

**Function Calling (client-side execution):**
- Define functions with JSON schema
- Model decides to call them → emits a tool call block
- Client executes locally
- Client reports results back to model as a tool_result message
- Loop continues

**Built-in Tools (server-side execution, via Responses API):**
- Platform automatically executes; results integrated into conversation
- No client-side execution required
- Available built-ins: web search, file search, code interpreter, computer use, image generation, MCP servers

## Orchestration patterns

Two categories:

1. **Single-agent systems**: "a single model equipped with appropriate tools and instructions executes workflows in a loop." This is the default starting point.

2. **Multi-agent systems**: "workflow execution is distributed across multiple coordinated agents." Add this complexity only when facing "separate tasks that do not overlap" and either complex instructions or numerous task-specific tools.

Guidance: "Use orchestration patterns that match your complexity level, starting with a single agent and evolving to multi-agent systems only when needed."

## SDK / API hierarchy

OpenAI defines three levels:

| Level | Tool | Use case |
|---|---|---|
| Direct API calls | OpenAI client libraries | Straightforward model requests without orchestration |
| Responses API | Lower-level, flexible | Fine-grained control, state management built-in |
| Agents SDK | Higher abstraction | Tracing, guardrails, orchestration primitives, rapid dev |

SDK core primitives: **Agent** (model + instructions + tools), **Handoff** (transfer to another agent), **Guardrail** (filter unwanted inputs), **Session** (manages conversation history across runs).

> "Use OpenAI client libraries for straightforward model requests without orchestration needs. Use Agents SDK when your application owns orchestration, tool execution, approvals, and state management."

## Production requirements (from Agents SDK docs)

- Guardrails at every stage: "the workflow should block or pause before risky work continues"
- Tracing built into Agents SDK
- Orchestration of handoffs: deciding "who owns the reply" between specialists
- Multi-turn state management via `conversation_id`

## Key takeaways for our research

1. OpenAI's definition matches Anthropic's: agent = LLM + tools + loop, where the LLM drives execution.
2. The "run" = the while loop. Exit conditions must be explicit.
3. Start with single-agent; only escalate to multi-agent for genuinely parallel, non-overlapping subtasks.
4. OpenAI's Agents SDK is an opinionated harness — useful shortcut but adds abstraction. Their own docs say: use direct client if you don't need orchestration.
