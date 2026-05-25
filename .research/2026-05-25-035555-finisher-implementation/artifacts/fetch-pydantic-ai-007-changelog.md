# Pydantic AI — Changelog highlights

**URL:** https://pydantic.dev/docs/ai/project/changelog/
**Fetched:** 2026-05-25

## Breaking changes relevant to finisher implementation

### v1.98.0 (2026-05-18) — `retries` unification

> "Add OpenAI Responses input token counting (`OpenAIResponsesModel.count_tokens`) and replace
> Agent `tool_retries`/`output_retries` with `retries: int | AgentRetries`."

So the **current** retry kwarg is `retries`. Old code using `tool_retries=` / `output_retries=`
will break on v1.98+.

### v1.0.1 (2025-09-05)
- Removal of `Python` evaluator from `pydantic_evals`

### v1.0.0 (2025-09-04)
- Drop support for Python 3.9
- Make many dataclasses require keyword arguments
- Change to `ModelRequest.parts` and `ModelResponse.parts` types

### v0.6.0 (2025-08-06) — `result_type` REMOVED

> "The `result_type`, `result_tool_name` and `result_tool_description` arguments were removed
> from the `Agent` class. Use `output_type` instead."

## v2.0.0b3 (2026-05-23) — pre-release, do not pin

- Bare `pydantic-ai` install ships fewer extras (must opt in to bedrock/groq/mistral)
- OpenAI model names default to Responses API (use `openai-chat:` prefix to keep Chat Completions)
- WebSearch/WebFetch native-only by default
- `MCP(url=...)` runs locally by default

## Open ModelRetry-related issues (not yet fixed)

- **#3393** — "Raising ModelRetry in output validator function crashes when streaming"
- **#3298** — "Control not being returned to the agent on ModelRetry exception in temporal worker"
- **#3197** — "ModelRetry bug with pydantic AI, AG-UI, and Open AI" (conversation-history
  corruption — initial tool_call message kept without matching tool response; OpenAI rejects)

**Mitigation for finisher:** raise `ModelRetry` only inside `@agent.tool` bodies (NOT in output
validators) and do NOT stream the finisher run. The classic synchronous `agent.run()` /
`agent.iter()` paths are unaffected by these bugs as of v1.102.0.
