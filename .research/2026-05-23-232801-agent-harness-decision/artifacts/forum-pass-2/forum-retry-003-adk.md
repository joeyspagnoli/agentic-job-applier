# forum-retry-003-adk.md
# Source: GitHub Discussions + search
# Date: 2026-05-24

## GitHub Discussion #2756 — "Is there any way to retry the last tool call or task when LLM call throws error?"
URL: https://github.com/google/adk-python/discussions/2756

Community discussion seeking retry mechanism. Before Reflect and Retry plugin, workaround was wrapping in Python try/except at app level.

---

## GitHub Discussion #795 — "Tool Failure Crashes Entire ADK Multi-Agent Workflow"
URL: https://github.com/google/adk-python/discussions/795

Tool failures in multi-agent pipelines would crash the entire workflow. The plugin system was designed to address this.

---

## GitHub Issue #1521 — "Random MALFORMED_FUNCTION_CALL Error from Gemini Agent"
URL: https://github.com/google/adk-python/issues/1521
Comments: 29 (closed)

**@halfpasttense:**
"I'm seeing something similar and it is also intermittent. In this case it seems to be caused by the sysml parameter string somehow being encoded wrong. There's a newline in there that isn't encoded as a \\n."

**@hangfei (collaborator):** "Could you share the frequency of this issue? Could you share the model you used? Need to collect some data points to figure out which model has this problem."

**Multiple reporters:** Gemini 2.0 Flash and 2.5 Flash both affected. Error is random, only occurs with complex/long parameter strings.

**Key takeaway:** ADK with Gemini models has a known MALFORMED_FUNCTION_CALL issue that is NOT addressed by the Reflect and Retry plugin — it's a model-level serialization bug. Workaround: retry at Python level.

---

## ADK Roadmap Q3 2025 Issue #2133 (47 comments, closed)
Reflect and Retry plugin shipped in ADK 1.16 (October 2025) as part of R⁵ capabilities. Community was actively waiting for this.

---

## Positive Signal
"Building Resilient Multi-Agent Systems with Google ADK" (Medium 2025): Sequential patterns with reflection and retry allow agents to generate a query, execute it, evaluate the result, and if it failed, generate another query and try again. The Reflect and Retry plugin makes this first-class.
