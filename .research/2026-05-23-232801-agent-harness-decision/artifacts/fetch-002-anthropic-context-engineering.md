# Fetch 002: Anthropic — "Effective Context Engineering for AI Agents"

**URL:** https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
**Fetched:** 2026-05-23

---

## Operational definition of an agent (verbatim)

This essay contains Anthropic's tightest definition of an agent:

> Agents are **"LLMs autonomously using tools in a loop."**

That's it. Seven words. The loop is essential; the autonomy (LLM picks the next action, not a script) is essential; the tools are the only way the LLM affects the world.

Followed by the elaboration:

> "An agent running in a loop generates more and more data that could be relevant for the next turn of inference."

This is the operational reason context engineering exists: an agent's context grows monotonically across iterations until something is done to manage it.

## Context engineering vs prompt engineering

> "Prompt engineering refers to methods for writing and organizing LLM instructions for optimal outcomes."
>
> Context engineering is "the set of strategies for curating and maintaining the optimal set of tokens (information) during LLM inference."

Prompt engineering is a one-shot artifact-design discipline. Context engineering is a runtime, multi-turn resource-management discipline. Agents need the latter.

## Context as a finite resource

> "LLMs, like humans, lose focus or experience confusion at a certain point."
>
> Research on "needle-in-the-haystack style benchmarking have uncovered the concept of context rot: as the number of tokens in the context window increases, the model's ability to accurately recall information from that context decreases."

Context must be treated as "a finite resource with diminishing marginal returns." LLMs have an "attention budget."

The guiding principle:

> "Find the smallest set of high-signal tokens that maximize the likelihood of some desired outcome."

This applies across system prompts, tools, examples, message history.

## System prompts: the Goldilocks zone

> The "right altitude is the Goldilocks zone between two common failure modes":
> - Overly complex hardcoded logic (brittle, doesn't generalize).
> - Vague guidance that assumes shared context (model can't follow).

Aim for "the minimal set of information that fully outlines your expected behavior." Use "XML tagging or Markdown headers to delineate these sections."

## Tool design principles

> "Self-contained, robust to error, and extremely clear with respect to their intended use."

The acid test:

> "If a human engineer can't definitively say which tool should be used in a given situation, an AI agent can't be expected to do better."

Avoid "bloated tool sets that cover too much functionality or lead to ambiguous decision points." Overlapping tools are worse than too-few tools.

## Examples (few-shot)

Don't enumerate edge cases. Instead:

> "Curate a set of diverse, canonical examples that effectively portray the expected behavior of the agent."
>
> "For an LLM, examples are the 'pictures' worth a thousand words."

## "Just in time" context retrieval

Field shift, per Anthropic:

> Agents now "maintain lightweight identifiers (file paths, stored queries, web links, etc.) and use these references to dynamically load data into context at runtime."
>
> This "mirrors human cognition: we generally don't memorize entire corpuses of information, but rather introduce external organization and indexing systems."

Implication for harness design: the harness should support tools that return references (paths, IDs) and other tools that resolve references to content.

## Long-horizon techniques

Three named techniques for keeping agents on-task across many iterations:

1. **Compaction** — "Taking a conversation nearing the context window limit, summarizing its contents, and reinitiating a new context window with the summary." Preserve "architectural decisions, unresolved bugs, and implementation details while discarding redundant tool outputs."

2. **Structured note-taking** — Agents "regularly write notes persisted to memory outside of the context window. These notes get pulled back into the context window at later times." Enables "persistent memory with minimal overhead."

3. **Sub-agent architectures** — Rather than one agent holding all state, "specialized sub-agents can handle focused tasks with clean context windows," each returning "only a condensed, distilled summary of its work."

## Implications for harness selection

A production harness for any non-trivial loop must support:
- Context window monitoring.
- Programmable compaction (summarize → reinitiate).
- External note storage (tool result that writes to disk/db).
- Sub-agent spawning with isolated context.
- Just-in-time reference resolution (don't dump everything; let the LLM ask).
