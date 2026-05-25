# Open Pydantic AI ModelRetry bugs as of 2026-05-25

## Issue #3197 — ModelRetry + AG-UI + OpenAI conversation-history corruption

**Status:** Partially fixed in unreleased branch (PR #2923); some adjacent issues remain.
**Affects:** v1.0.0 through v1.3.x (and likely v1.102) when using AG-UI streaming.

> "When a tool raises ModelRetry, the conversation history can become corrupted because streamed
> messages keep the initial tool_call message in the conversation history without a corresponding
> tool response, creating an invalid message sequence that OpenAI's API rejects on the next turn."

Symptom: `HTTP 422: Extra inputs are not permitted` on the second turn after a ModelRetry.

**Workaround for finisher:** do NOT stream finisher runs. Use `agent.iter()` synchronously.
Streaming is for chat-style UIs; finisher is a structured background job.

## Issue #3393 — ModelRetry in output validator crashes when streaming

**Status:** Open. Tagged "as designed-but-painful".
**Affects:** `run_stream()` + `@agent.output_validator` + `raise ModelRetry`.

The streaming path doesn't go back through the agent graph when the validator rejects output —
it just propagates the exception.

**Workaround for finisher:** don't use `@agent.output_validator` with `ModelRetry`. If we need
to validate `FinisherResult`, do it in the calling code after `result.output` is returned.

## Issue #3298 — ModelRetry in Temporal worker doesn't return control to agent

**Status:** Partially fixed in v1.x; an MCP-server variant remains open.
**Affects:** Pydantic AI Temporal integration.

Not relevant to finisher — we don't use Temporal.

## Issue #1987 — "Gotcha: usage_limits must be in run* function"

> "`usage_limits` cannot be passed to the `Agent()` constructor — it must go on `run()` /
> `run_sync()` / `run_stream()` / `iter()`."

**Mitigation:** put `usage_limits=UsageLimits(request_limit=25)` on the `agent.iter(...)` call,
NOT on the Agent constructor.

## Issue #2593 — "Enforce usage limits by exact tool call count (not just request count)"

Open feature request. Today, `request_limit` counts model requests, not tool calls. If the
model makes 10 parallel tool calls in one turn, that's 1 request but 10 tool calls.

**Mitigation:** use BOTH `request_limit=25` AND `tool_calls_limit=40` (which already exists).
The 40 is permissive enough to account for parallel calls within turns.

## Bottom line

Of the four open bugs, **only #1987 (`usage_limits` location)** affects our planned finisher
architecture, and the mitigation is trivial: pass it to `iter()`, not `Agent()`. The other
three only bite if we use streaming or AG-UI or Temporal — none of which apply here.

The `agent.iter()` + non-streaming + tools-raising-`ModelRetry` path is **safe** on v1.102.0.
