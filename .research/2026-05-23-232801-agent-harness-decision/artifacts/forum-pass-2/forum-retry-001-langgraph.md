# forum-retry-001-langgraph.md
# Source: GitHub Issues + forum search
# Date: 2026-05-24

## GitHub Issue #7138 — "ToolNode: surface model output metadata in tool error messages to enable self-correction"
URL: https://github.com/langchain-ai/langgraph/issues/7138
Comments: 9 (open)

**Core quote from issue description:**
"The model receives this error but has no access to its own output metadata — information like why it stopped generating, how many tokens it used, or whether its output was complete."

**Real failure scenario (from @vinayakSharm):**
"A model calling `write_file` with large content hit `max_tokens=16384`, truncating the tool call JSON mid-argument. Pydantic raised a cryptic validation error that gave no indication of the truncation. The result was brutal: The model retried 249 times, never learning WHY its arguments were malformed."

**Community response (@mykolademyanov):**
"This is a classic infinite-loop failure mode. If `max_tokens` cuts off the tool call JSON, the model receives a validation error without any signal that the output was truncated — so retries often produce the same broken call again and again. In practice this usually needs more than better error messages. Runtimes tend to add retry budgets or divergence checks to stop loops when no progress is made."

**Key takeaway:** LangGraph ToolNode retries don't tell the model WHY it failed. 249 retry loops possible.

---

## GitHub Issue #6486 — "Tool node error handling disabled by default after 1.0.1"
URL: https://github.com/langchain-ai/langgraph/issues/6486

**Summary:** After LangGraph 1.0.1, ToolNode changed default behavior — tool errors that were previously caught and converted to error messages now bubble up as unhandled exceptions, crashing agents. Developers must explicitly set `handle_tool_errors=True` or existing production graphs break silently.

**User quote:** "tool error handling is now off unless explicitly enabled"

---

## Forum: "The best way in LangGraph to control flow after retries exhausted"
URL: https://forum.langchain.com/t/the-best-way-in-langgraph-to-control-flow-after-retries-exhausted/1574

Community discussing boilerplate complexity of implementing retry flow after exhaustion. Multiple nodes, state routing, conditional edges required.

---

## Issue #6027 — ValidationError not retried by RetryPolicy
URL: https://github.com/langchain-ai/langgraph/issues/6027

"Node Retry Policies are not respected when a node fails with Pydantic ValidationError" — ValidationError not in default retry list. Malformed model output silently fails instead of retrying.
