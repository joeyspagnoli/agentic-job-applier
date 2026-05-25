# Forum Survey 004 — Playwright + Python LLM Agent Loop in Production

Date: 2026-05-24
Query: "playwright python LLM agent loop production lessons learned custom loop 2026"
Sources: stevekinney.com, scrolltest.com, testdino.com, testmuai.com, developers.googleblog.com, cegeka.com

## Google Developers Blog: 5 Lessons from Refactoring a Monolith

Source: developers.googleblog.com/production-ready-ai-agents-5-lessons-from-refactoring-a-monolith/

**Framework chosen: Google ADK**

### Lesson 1: Ditch the Monolith
"Separation of concerns. Specialized agents with narrow tasks run more reliably than a single LLM trying to execute a massive, multi-step prompt."
→ Replaced linear script with Google ADK `SequentialAgent` pipeline

### Lesson 2: Force Structured Outputs (Pydantic)
"Eliminated fragile JSON parsing by replacing prompt-embedded schema instructions with native Pydantic objects."
→ ADK's Structured Outputs enforce runtime-validated Python schemas

### Lesson 3: Replace Hardcoded State with Dynamic RAG
→ Used **Playwright for async web scraping** + Google Cloud Vector Search
This is the only mention of Playwright — as a data ingestion tool, not as the browser automation layer for the agent.

### Lesson 4: Observability is Non-Negotiable
→ OpenTelemetry on Google Cloud through ADK's native support

### Lesson 5: Taming Token Burn
→ ADK's built-in circuit breakers, exponential backoffs, timeout boundaries

**Key validation for our project**: Google's own team chose ADK for the harness. Their rationale (separation of concerns, structured outputs, built-in circuit breakers) exactly matches why we chose ADK.

## Playwright AI Agent Architecture (Testing Community)

From testdino.com, testmuai.com:

**Recommended pattern: Planner/Generator/Healer**
1. **Planner (LLM)**: reads AX tree, decides actions
2. **Generator (deterministic code)**: executes decided actions via Playwright
3. **Healer (LLM fallback)**: activates when deterministic code fails

### Production Pitfalls Identified:
1. **Test bloat** without clear constraints — "curate the Planner's output before handing it to the Generator"
2. **Black box debugging** — agents produce results without internal traces → need OpenTelemetry
3. **Resource overhead** — LLM + browser session = high CPU/RAM + slow execution
4. **Hardcoded vs. scalable**: prototype patterns don't survive at scale

## Key Production Insight (stevekinney.com)

"The fundamental agent loop: while loop that calls LLM, checks for tool calls, executes them, stops when it doesn't."

The **production-hardened version** needs:
- Context compaction (for long sessions)
- Loop detection (prevent infinite loops)
- Cost budgets (token burn limits)
- Graceful termination

→ This is exactly what Google ADK's `RunConfig(max_llm_calls=N)` provides out of the box.

## Implication for Our Project

The Google Developers Blog post is the strongest direct validation:
- A production team (Google itself) refactored to ADK
- Playwright is used as a data tool within ADK, not as the harness itself
- ADK's built-in circuit breakers prevent runaway costs
- Pydantic structured outputs = the right pattern for form fields

Our existing `root_apply_decider/runtime.py` already implements this pattern. The research confirms we're on the right architectural path.
