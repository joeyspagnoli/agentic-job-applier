# Fetch 001: Anthropic — "Building Effective Agents" (Dec 2024)

**URL:** https://www.anthropic.com/research/building-effective-agents
**Fetched:** 2026-05-23
**Method:** WebFetch (content paywalled in places; key quotes extracted)

---

## Core distinction (Anthropic's framing — quote)

Anthropic divides agentic systems into two architecturally distinct categories:

> **Workflows** are "systems where LLMs and tools are orchestrated through predefined code paths."
>
> **Agents** are "systems where LLMs dynamically direct their own processes and tool usage, maintaining control over how they accomplish tasks."

This is the most important sentence in the piece. Workflows are scripted; agents drive themselves.

## The foundational building block: the "augmented LLM"

Anthropic names the basic atomic unit:

> The "augmented LLM" is "an LLM enhanced with augmentations such as retrieval, tools, and memory."

Every workflow and every agent in their taxonomy is composed of augmented LLMs as nodes. The augmentation set (retrieval / tools / memory) is the canonical list.

## The five workflow patterns

Anthropic enumerates exactly five pre-built workflow patterns. These are NOT agents — they are deterministic compositions of augmented LLMs:

1. **Prompt chaining** — "decomposes tasks into sequential steps with programmatic checks" between steps. Each LLM call's output becomes the next call's input; gates can validate intermediate results.

2. **Routing** — "classifies inputs and directs them to specialized tasks." A classifier LLM dispatches to one of N downstream prompts/models.

3. **Parallelization** — "runs LLMs simultaneously on independent subtasks or multiple attempts." Two flavors: sectioning (split into independent parts) and voting (run N times, aggregate).

4. **Orchestrator-workers** — "central LLM dynamically breaks down tasks and delegates to worker LLMs." Differs from routing: the subtasks are not pre-defined but synthesized at runtime.

5. **Evaluator-optimizer** — "one LLM generates responses while another provides iterative feedback." Generator + critic in a loop.

## When to use agents vs workflows

Anthropic's explicit guidance:

> "You should consider adding complexity only when it demonstrably improves outcomes."

Workflows fit when the task decomposition is known in advance. Agents fit when "steps cannot be predicted and multiple turns are needed," requiring "some level of trust in [the LLM's] decision-making."

The piece is emphatic: most production "agentic" systems are actually workflows. Don't reach for a full autonomous agent if a chain or router solves the problem.

## Framework recommendation (verbatim — load-bearing for our decision)

> "Rather than complex frameworks, successful implementations use simple, composable patterns. Start with direct API calls; frameworks can obscure underlying prompts and create unnecessary complexity."

Anthropic explicitly recommends starting WITHOUT a framework. Their stated reasons:

- Frameworks **obscure the underlying prompts** the LLM actually sees.
- Frameworks add **unnecessary abstraction layers** that make debugging harder.
- Frameworks bake in **opinionated patterns** that may not fit your use case.

The recommendation flips only when you have a stable system whose abstractions you understand from the inside — i.e., when you could write the framework yourself.

## What an agent IS (Anthropic's operational definition)

Pulled from the piece and the companion context-engineering essay (see fetch-002): an agent is an augmented LLM running **in a loop**, where the LLM itself decides which tool to call next and when the task is done. The harness (the code around the LLM) is responsible only for: calling the model, executing requested tools, appending results, and re-invoking. No branching logic. No pre-defined DAG. The LLM is the controller.

## Key takeaways for our research

1. Workflow ≠ agent. A scripted multi-step LLM pipeline is a workflow.
2. The five workflow patterns are the right baseline — only escalate to a true agent if none fit.
3. Anthropic explicitly says: do not start with a framework.
4. The augmented-LLM-in-a-loop is the canonical agent shape.
