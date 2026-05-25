# Fetch 006: OpenAI Cookbook — Agents Topic

**URL:** https://cookbook.openai.com/topic/agents (redirects to https://developers.openai.com/cookbook/topic/agents)
**Fetched:** 2026-05-23
**Method:** WebFetch (followed 308 redirect)

---

## Definition

> "Agents are systems that independently accomplish tasks on your behalf. Agents use an LLM to execute instructions and make decisions. They have access to tools to gather context and take actions, always operating within clearly defined guardrails."

## Core components (from cookbook page)

The cookbook structures agent documentation across:

- **Agent Definition** — how to specify behavior and capabilities
- **Model Selection** — choosing appropriate models and providers
- **Execution** — methods for running agents effectively
- **Sandbox Environments** — isolated execution contexts for safety
- **Orchestration** — coordinating complex multi-agent workflows
- **Guardrails & Approvals** — security mechanisms and approval workflows
- **Results & State** — managing agent outputs and persistent state
- **Observability** — monitoring and integration capabilities

## Governance / guardrails emphasis

The cookbook treats agents as production-ready systems requiring:
- Safety and operational boundary definitions (guardrails)
- Cost optimization
- Operational reliability

## Key cookbook examples (topics linked)

- Multi-agent portfolio collaboration (Agents SDK)
- Building governed AI agents — agentic scaffolding
- Agent loops with tool calling
- Agents with web search, file search, code interpreter

## Relationship to Agents SDK

The cookbook examples predominantly use the Agents SDK for orchestration patterns. The raw function-calling protocol (define schema → emit tool_call → execute → return tool_result → loop) is the underlying primitive; the SDK wraps this loop.

## Key takeaways for our research

1. OpenAI's cookbook confirms: guardrails are not optional for production agents — they're core architecture.
2. Observability (tracing, monitoring) is listed as a first-class concern alongside tool use.
3. The cookbook's examples show the Agents SDK as the production path, but the underlying protocol (JSON schema → tool_call → tool_result loop) is always present under the abstraction.
