# Fetch 004: Lilian Weng — "LLM Powered Autonomous Agents" (June 2023)

**URL:** https://lilianweng.github.io/posts/2023-06-23-agent/
**Author:** Lilian Weng (then OpenAI Head of Safety Systems)
**Date:** 23 June 2023

This is the canonical "what is an LLM agent" survey from before the field had standardized vocabulary.

---

## The three-component architecture

Weng's diagram makes the LLM the **brain** and adds three peripheral systems:

```
                  ┌──────────────┐
                  │   PLANNING   │
                  │  (decompose, │
                  │   reflect)   │
                  └──────┬───────┘
                         │
   ┌──────────┐    ┌─────▼─────┐    ┌─────────┐
   │  MEMORY  │◄──►│    LLM    │◄──►│  TOOLS  │
   │ (short + │    │  (brain)  │    │  (APIs) │
   │  long)   │    └───────────┘    └─────────┘
   └──────────┘
```

Direct framing: the LLM is the brain; the other components are accessories that extend its cognitive reach (memory) and its causal reach (tools).

## Component 1: Planning

Two sub-mechanisms:

**Task decomposition** — Chain of Thought (CoT) prompts the model to "think step by step." Tree of Thoughts (ToT) explores multiple reasoning branches and prunes. **ReAct** interleaves thoughts with actions: the model emits `Thought: ... Action: ... Observation: ...` in a loop.

**Self-reflection** — Critical for autonomous agents that must recover from mistakes:
- **ReAct** — explicit thought/action/observation traces.
- **Reflexion** — adds dynamic episodic memory of past failures; the agent reflects in natural language after each trial and uses the reflection on the next trial.
- **Chain of Hindsight** — train models on sequences of past outputs labeled with quality feedback so they learn to revise.

## Component 2: Memory

Weng maps human memory taxonomy onto LLM agents:

| Human memory | LLM agent analog |
|---|---|
| Sensory memory | Raw input embeddings |
| Short-term / working memory | In-context window |
| Long-term memory | External vector store (FAISS, HNSW indexes) |

The **context window is short-term memory**. Anything beyond it must be retrieved via embedding similarity from an external store. This framing predates Anthropic's "context engineering" essay by two years and contains essentially the same insight.

## Component 3: Tool use

Survey of tool-use research:

- **MRKL** (Modular Reasoning, Knowledge, Language) — routes subproblems to specialist modules (calculator, DB, etc.).
- **TALM** and **Toolformer** — fine-tune the LLM to emit tool calls inline in its text.
- **HuggingGPT** — uses an LLM as a router that selects and chains specialist models from HuggingFace Hub.
- **API-Bank** — benchmark for tool-using LLMs.

The unifying idea: tools extend the LLM's action space beyond text generation. Without tools, the LLM can only output language. With tools, it can read the filesystem, query a DB, call an API, fill a form.

## Case studies (Weng's examples)

- **ChemCrow** — LLM + 17 expert chemistry tools for drug/material discovery.
- **Generative Agents** (Park et al., 2023) — 25 simulated characters in a sandbox, each with memory streams, reflection, and planning. The first influential demo of multi-agent emergent behavior.
- **AutoGPT** — open-source loop-based autonomous agent (LLM + memory + browser + filesystem). Famously brittle but conceptually canonical.
- **GPT-Engineer** — generates entire codebases from a prompt.

## Acknowledged challenges (from 2023, still mostly true)

1. **Finite context length** — limits how much history can be carried.
2. **Long-term planning + error recovery** — agents struggle to recover from compounding errors over many steps.
3. **Reliability of natural-language interfaces** — parsing tool calls and intermediate outputs out of free-form text is fragile. (This is what JSON tool-call APIs largely solved later.)

## Why this source is foundational

This essay is the most-cited "what is an agent" article in the field. The three-pillar (planning / memory / tools) decomposition shows up nearly verbatim in every later survey and curriculum, including HuggingFace's smolagents course. Read it once to get the vocabulary; later sources refine the details but don't replace the framework.
