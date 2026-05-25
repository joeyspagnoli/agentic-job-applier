# analysis-012-tool-retry-mechanisms.md
# Topic: How each candidate harness handles tool retries
# Date: 2026-05-24
# Built on: forum-pass-2 fetch + forum artifacts

## Use Case

The agent runs browser automation tools. Tools fail in two ways:
1. Runtime failures: click(@e3) "element no longer in DOM"; select(@e7) option mismatch
2. Malformed args: model emits empty ref, wrong type, missing required field

---

## 1. Pydantic AI

### Built-in mechanism
raise ModelRetry("message") from inside any tool. Declarative: @agent.tool(retries=2) per-tool, Agent(retries=N) global. Both levels independently configurable.

### Failure feedback to model
The string passed to ModelRetry("element no longer in DOM") becomes the tool result verbatim. Documented behavior.

### Validation error retry on malformed args
AUTOMATIC. Pydantic validation errors on tool args trigger retry without any extra code.

### Simplest "easy retry" (1 line beyond tool definition):
    raise ModelRetry(f"@{ref} no longer in DOM — call snapshot() for fresh refs")

### Forum voices
- Dev.to builder (8 months production): "In production, set retries=2 on your agent and handle UnexpectedModelBehavior"
- Alice Labs 2026: "strongest framework for typed, conventional agents"
- ZERO GitHub issues on ModelRetry being broken (gh-retry-004 found 0 results)

---

## 2. AWS Strands

### Built-in mechanism
Two layers: (1) Default: exceptions auto-converted to model-visible error result. (2) Hooks: AfterToolCallEvent.retry = True for mechanical re-run; BeforeToolCallEvent.cancel_tool = "message" to block with model-visible reason.

### Failure feedback to model
Default: "the agent converts it to an error result and returns it to the model, allowing the model to adjust its approach and retry." Zero extra code for basic case.

### Validation error retry on malformed args
Not automatic. BeforeToolCallEvent can validate and cancel with message (~4 lines).

### Simplest "easy retry" (0 lines — default behavior):
No code needed. Exceptions reach model automatically. Hooks add structured retry on top.

### Forum voices
- AWS blog 2026: "Steering Hooks could provide 100% accuracy pass rate vs 80.8% for graph-based"
- Issue #667 "Release hooks as non-experimental" — still OPEN as of research date
- SDK launched May 2025 — younger ecosystem

---

## 3. Google ADK

### Built-in mechanism
Callbacks (before_tool_callback, after_tool_callback, on_tool_error) + Reflect and Retry Plugin (ADK 1.16, Oct 2025): intercepts failures, synthesizes reflection guidance for LLM, retries up to max_retries.

### Failure feedback to model
Plugin synthesizes structured guidance (not just raw error text) to help LLM correct. More opinionated than ModelRetry but more powerful for complex failures.

### Validation error retry on malformed args
before_tool_callback can validate and return error dict (~4 lines). Not automatic.

### Simplest "easy retry" (10 lines, global plugin):
    app = App(name="browser-agent", agent=my_agent,
              plugins=[ReflectAndRetryToolPlugin(max_retries=3)])
After this, all tool failures get reflection + retry automatically.

### Forum voices
- Issue #1521 (29 comments): "MALFORMED_FUNCTION_CALL" random Gemini errors with complex args — plugin helps but root bug persists
- Issue #3940 (31 comments, open): Tool called multiple times — loop detection missing from plugin
- ADK is ALREADY the chosen harness in this project

---

## 4. OpenAI Agents SDK

### Built-in mechanism
failure_error_function on @function_tool(failure_error_function=fn). Default: default_tool_error_function. No retries=N parameter.

### Failure feedback to model
Return value of failure_error_function becomes LLM-visible tool output. BUT: ModelBehaviorError (model calls nonexistent tool or emits bad JSON) bypasses this and CRASHES the entire agent run. Issue #325 OPEN, no resolution.

### Validation error retry on malformed args
NOT handled. ModelBehaviorError on bad args crashes the run without retrying.

### Simplest "easy retry" (1 decorator arg, but no retry budget):
    @function_tool(failure_error_function=lambda ctx, err: str(err))

### Forum voices
- Issue #325 opener: "a nonexistent tool call crashed a whole 10-minute agent run"
- @timdoctronic and @jackien1 both asking "what is the proper retry mechanism" — no answer from maintainers
- Users reaching for tenacity (external library) as workaround

---

## 5. Claude Agent SDK

### Built-in mechanism
is_error: True in the tool result dict. Agent loop continues only if you catch and return — not automatic. If exception propagates uncaught, "agent loop stops. Claude never sees the error."

### Failure feedback to model
The content array text in the is_error: True response is what Claude sees. Explicit catch-and-return required every time.

### Validation error retry on malformed args
Not documented. Likely crashes (since SDK requires explicit is_error: True for loop continuation).

### Simplest "easy retry" (~5 lines boilerplate per tool):
    try:
        ...
    except Exception as e:
        return {"content":[{"type":"text","text":str(e)}],"is_error":True}

### Forum voices
- "The isError: True return is the single most important pattern" — framed as pattern to learn, not automatic
- Issue #812: 429 rate limits crash agent sessions — unresolved
- Pre-1.0 SDK (v0.1.48 Python), production patterns still emerging

---

## 6. LangGraph

### Built-in mechanism
Two separate mechanisms at wrong granularity: (1) RetryPolicy on nodes (re-runs entire node, model starts fresh without error context); (2) ToolNode(handle_tool_errors=True) (must be explicitly enabled since 1.0.1 breaking change).

### Failure feedback to model
ToolNode(handle_tool_errors=True) does feed errors to model. But ToolNode does NOT surface stop_reason or token counts — model can retry 249 times without knowing why (Issue #7138 open).

### Validation error retry on malformed args
Issue #6027: ValidationError NOT in default RetryPolicy retry list — silently fails.

### Simplest "easy retry" (30-40 lines, full graph wiring required):
Must define StateGraph, MessagesState, LLM node, ToolNode, conditional edges, compile. RetryPolicy and error_handler are additional.

### Forum voices
- Issue #7138 reporter: "The model retried 249 times, never learning WHY its arguments were malformed"
- Issue #6486: Breaking change in 1.0.1 silently broke production agents' error handling
- LangGraph 2.0 (Feb 2026) more mature but fundamental boilerplate unchanged

---

## Line Count Comparison: Express a Retry

| Harness | Mechanism | Lines for easy retry | Auto malformed-args |
|---|---|---|---|
| Pydantic AI | raise ModelRetry("msg") | 1 | YES |
| Strands | Default (nothing) | 0 | No |
| Google ADK | ReflectAndRetryPlugin (global) | 0 global / 4 per-tool | No |
| OpenAI SDK | failure_error_function decorator arg | 1 (no budget) | NO (crash) |
| Claude SDK | try/except + is_error:True | 5 per tool | Unknown |
| LangGraph | Graph wiring + ToolNode + RetryPolicy | 30-40 | NO (silent fail) |

---

## Final Ranking on Retry Ergonomics

1. Pydantic AI — raise ModelRetry("msg") is 1 line; per-tool budget is 1 decorator arg; malformed-args retry is automatic; V1 stable; zero bug reports on core mechanic
2. AWS Strands — default behavior (exceptions auto-reach model) is cleanest; mechanical retry hook clean when needed; held back by experimental hooks (Issue #667 open) and younger ecosystem
3. Google ADK — Reflect and Retry plugin is first-class and already in this project; MALFORMED_FUNCTION_CALL Gemini bug is real production friction; ranked 3rd as incumbent
4. OpenAI Agents SDK — failure_error_function works for soft failures; fatal flaw: ModelBehaviorError crashes entire runs (Issue #325 unresolved); not suitable for "often" retries
5. Claude Agent SDK — is_error: True works but requires explicit boilerplate per tool; pre-1.0; rate limit crashes unresolved
6. LangGraph — RetryPolicy at wrong abstraction level; 249-retry loop bug open; breaking defaults change; 3x boilerplate; not recommended for "easily and often"

---

## Implication for This Project (ADK is incumbent)

1. Add ReflectAndRetryToolPlugin(max_retries=3) to App — covers all tool failures globally
2. Use before_tool_callback for known arg validation failures (empty ref, stale snapshot) — returns model-visible error before tool even runs (0-cost)
3. Keep tool arg schemas simple (primitives only) — mitigates MALFORMED_FUNCTION_CALL Gemini bug
4. RunConfig(max_llm_calls=N) remains the circuit breaker

If switching harnesses were in scope, Pydantic AI's ModelRetry would be the cleaner primitive — but ADK's existing integration already covers the use case with the plugin.
