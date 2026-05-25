# Head-to-Head: Google ADK vs. OpenAI Agents SDK for the Layer-3 Browser Finisher

## The Question

Both frameworks can drive a 6-tool, 5–25 turn browser-fill agent. Which one
should we use for the new Layer-3 browser finisher?

## Decision Matrix

| Dimension | ADK (google-adk==1.23.0) | OpenAI Agents SDK (not in repo) |
|---|---|---|
| Already in pyproject.toml | YES — zero new deps | NO — add openai-agents + optional [litellm] |
| Already proven in this codebase | YES — root_apply_decider is in production | NO |
| LiteLLM portability | YES — LiteLlm(model="openai/...") already wired in model.py | YES — via openai-agents[litellm], separate install |
| Submit guardrail | before_tool_callback (Python-layer, cannot be bypassed) | @tool_input_guardrail + reject_content (same strength) |
| Loop ergonomics | Verbose async-for event generator (already templated in repo) | Cleaner — single await Runner.run() |
| Hard LLM-call cap | YES — RunConfig(max_llm_calls=N) | NO direct equivalent |
| Session isolation per apply | InMemorySessionService + uuid4 session_id | SQLiteSession(f"apply_{job_id}") in-memory |
| In-process | YES | YES |
| Parallel framework burden | No — ADK is already the one framework | Yes — two frameworks in one process |
| Tracing footgun | None | Must call set_tracing_disabled(True) for non-OpenAI |

## The Decisive Factors

Three factors tip the scale decisively to ADK:

**1. Zero net-new dependencies.** `google-adk==1.23.0` is already pinned. Adding
`openai-agents` and `openai-agents[litellm]` — in a repo that mandates `==`
pinning for everything — means finding compatible versions, running the test suite,
and owning that dependency forever. For no functional gain over ADK.

**2. The pattern is already written.** `src/agents/root_apply_decider/runtime.py`
is a complete, production-tested template for `Runner + InMemorySessionService +
run_async`. The browser-finisher is a diff on that file: add tools, add
`before_tool_callback`, change the system prompt. The async-generator verbosity is
real but it is already understood by the team and already templated.

**3. One framework, not two.** Running ADK for the decider and OpenAI Agents SDK
for the finisher puts two agent framework import trees in the same Python process,
doubles the concepts a contributor needs to understand, and creates drift between
the two agents over time. Consistency beats ergonomics.

## Verdict: Use ADK

Build the Layer-3 browser finisher as a second ADK agent. Copy
`root_apply_decider/runtime.py` as the starting point. Add the 6 Playwright-CDP
tools, wire `before_tool_callback=block_submit_callback`, set
`RunConfig(max_llm_calls=40)`, and start with `LiteLlm(model="openai/gpt-4.1-mini")`.
Switch model provider with one line if cost or quality adjustments are needed.

OpenAI Agents SDK is the right answer if ADK were not already in the repo. It is
not the right answer here.
