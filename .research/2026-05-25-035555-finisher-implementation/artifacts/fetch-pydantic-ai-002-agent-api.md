# Pydantic AI — Agent class public API

**URL:** https://pydantic.dev/docs/ai/api/pydantic-ai/agent/ (redirected from https://ai.pydantic.dev/api/agent/)
**Fetched:** 2026-05-25
**Prompt:** Extract full public API for Agent class — constructor, run methods, RunResult, deprecations.

## Agent constructor (verbatim)

```python
Agent(
    model: models.Model | models.KnownModelName | str | None = None,
    output_type: OutputSpec[OutputDataT] = str,
    instructions: AgentInstructions[AgentDepsT] = None,
    system_prompt: str | Sequence[str] = (),
    deps_type: type[AgentDepsT] = NoneType,
    name: str | None = None,
    description: TemplateStr[AgentDepsT] | str | None = None,
    model_settings: AgentModelSettings[AgentDepsT] | None = None,
    retries: int | AgentRetries | None = None,
    validation_context: Any | Callable[[RunContext[AgentDepsT]], Any] = None,
    tools: Sequence[Tool[AgentDepsT] | ToolFuncEither[AgentDepsT, ...]] = (),
    toolsets: Sequence[AgentToolset[AgentDepsT]] | None = None,
    defer_model_check: bool = False,
    end_strategy: EndStrategy = 'early',
    metadata: AgentMetadata[AgentDepsT] | None = None,
    tool_timeout: float | None = None,
    max_concurrency: AnyConcurrencyLimit = None,
    capabilities: Sequence[AgentCapability[AgentDepsT]] | None = None,
) -> None
```

### Key parameters

- **`model`** — e.g. `'openai:gpt-5.2'`. Required at construct or run time.
- **`output_type`** — schema for structured output; defaults to `str`. (Replaces older `result_type` kwarg.)
- **`deps_type`** — type for `RunContext[T].deps`; use `None` if no deps.
- **`instructions`** — initial instructions string/callable.
- **`system_prompt`** — static system prompt(s).
- **`retries`** — `int` for a uniform tool/output budget, or `AgentRetries` dict for per-category control. (Replaces older `tool_retries` / `output_retries` kwargs.)
- **`end_strategy`** — `'early'` (default), `'graceful'`, or `'exhaustive'`.
- **`tool_timeout`** — per-tool timeout in seconds.

## Run methods

```python
async def run(
    user_prompt: str | Sequence[UserContent] | None = None,
    output_type: OutputSpec[RunOutputDataT] | None = None,
    message_history: Sequence[ModelMessage] | None = None,
    model: models.Model | models.KnownModelName | str | None = None,
    deps: AgentDepsT = None,
    model_settings: AgentModelSettings[AgentDepsT] | None = None,
    retries: int | AgentRetries | None = None,
    toolsets: Sequence[AbstractToolset[AgentDepsT]] | None = None,
    capabilities: Sequence[AgentCapability[AgentDepsT]] | None = None,
    usage_limits: UsageLimits | None = None,
    # ... additional parameters
) -> AgentRunResult[OutputDataT]
```

`run_sync` and `run_stream` mirror the same kwargs.

## AgentRunResult interface

- `.output` — final output matching `output_type` schema (Pydantic model instance if model class supplied)
- `.usage()` — returns `RunUsage` with `requests`, `tool_calls`, `input_tokens`, `output_tokens`, etc.
- `.all_messages()` — full conversation history (list of `ModelMessage`)
- `.metadata` — resolved run metadata as dict

## Decorators

```python
@agent.tool
def my_tool(ctx: RunContext[DepsT], param: int) -> str:
    """Tool description."""
    return "result"

@agent.tool_plain
def simple_tool(x: float) -> float:
    """No context needed."""
    return x * 2

@agent.system_prompt
def dynamic_prompt(ctx: RunContext[DepsT]) -> str:
    return f"Instruction: {ctx.deps}"

@agent.output_validator
async def validate_output(ctx: RunContext[DepsT], data: str) -> str:
    if "invalid" in data:
        raise ModelRetry("Retry with corrections")
    return data
```

## Override context (testing)

```python
with agent.override(model='openai:gpt-4'):
    result = agent.run_sync("test")
```

## Deprecations (v0.x → v1.x)

- `run_mcp_servers()` is deprecated; use `async with agent:` instead.
- `result_type` kwarg → renamed `output_type` (the current kwarg).
- `tool_retries` / `output_retries` → unified `retries: int | AgentRetries`.
