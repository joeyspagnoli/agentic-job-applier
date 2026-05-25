# Forum Survey 003 — browser-use vs Custom Agent Loop

Date: 2026-05-24
Query: "browser-use vs custom agent loop harness Python 2025 2026"
Sources: browser-use.com/posts/bitter-lesson-agent-harnesses, pyshine.com, theagentpost.co, flowtivity.ai, nxcode.io, jimmysong.io

## The Browser-Use Team's Own Position on Harnesses

From "The Bitter Lesson of Agent Harnesses" (browser-use.com blog):

### Core argument:
> "Every one of them is a constraint the RL'd model has to fight around."

- Helper functions like `click()`, `type()`, `scroll()` **limit** model capabilities
- LLMs "were trained on millions of tokens of Page.navigate, DOM.querySelector, Runtime.evaluate" — CDP is the lowest level Chrome exposes
- The model already knows CDP; wrappers hide this knowledge

### What they recommend:
- Direct CDP command access
- Ability to edit its own helper functions
- Plain Python execution environment

### Self-healing mechanism:
When a tool is missing, the agent identifies the gap, writes the function, and reruns — "treating it as a missing-import problem."

### Irony noted:
browser-use themselves shipped BOTH products:
1. `browser-use` (95k stars) — a framework with a structured agent loop
2. `browser-harness` (13.6k stars) — "delete the helpers, let the agent write what it needs"

The harness was built AFTER browser-use became popular, suggesting the team learned from production experience with browser-use's abstractions and moved toward rawer access.

## Community Position

From nxcode.io analysis:
> "Deterministic workflows: Use Playwright. No contest. It's faster, cheaper, and more reliable."
> "Many production systems use Playwright for the 80% of steps that are predictable and Stagehand or Browser Use for the 20% that require AI understanding."

From firecrawl analysis:
- "Success rates range from 30% to 89% depending on tool and task type"
- "Developers prefer brittleness of scripts to non-deterministic workflows for critical production tasks"

## When to Use What

| Scenario | Recommendation |
|----------|----------------|
| Deterministic flows (known selectors, predictable pages) | Playwright direct (no LLM) |
| Semi-structured forms (known schema, some variability) | BYO Playwright tools + LLM harness |
| Complex unpredictable tasks | browser-use or Skyvern |
| Maximum agent freedom (coding/research agents) | browser-harness or raw CDP |

## Implication for Our Project

Our architecture (BYO 6 Playwright tools + Google ADK harness) is the "semi-structured forms" category:
- Known form schemas (most apply flows follow patterns)
- Some variability (custom questions, unusual layouts)
- Need guard rails (no-submit protection, circuit breakers)

browser-use owns its own loop and would conflict with Google ADK. Our approach of BYO tools + ADK is the architecturally sound choice for our use case.

## The "Own Loop" Problem with browser-use

browser-use has its own `Agent` class with its own loop. If you try to use browser-use inside Google ADK or OpenAI Agents SDK, you end up with two competing loops:
- The harness loop (ADK's `Runner`)
- browser-use's internal `Agent.run()` loop

This is why browser-use ships as a browser layer (exposed as a tool), not as a harness. You call `Agent.run()` from inside your harness's tool execution, surrendering the loop to browser-use for the duration.

The alternative: BYO Playwright tools. Each tool call is a single deterministic action; your harness (ADK) controls the loop. This is what we do in `root_apply_decider`.
