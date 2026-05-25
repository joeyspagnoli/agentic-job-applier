# fetch-retry-001-pydantic.md
# Source: https://pydantic.dev/docs/ai/core-concepts/agent/ (redirected from https://ai.pydantic.dev/agents/#reflection-and-self-correction)
# Fetched: 2026-05-24
# Prompt: ModelRetry, tool retry, reflection, self-correction, code examples

## ModelRetry Exception

**Purpose:** Signal that the model should retry after a tool or validator encounters an issue.

**Raising from tools (7-line core example):**
```python
@agent.tool(retries=2)
def get_user_by_name(ctx: RunContext[DatabaseConn], name: str) -> int:
    user_id = ctx.deps.users.get(name=name)
    if user_id is None:
        raise ModelRetry(
            f'No user found with name {name!r}'
        )
```

When raised, the error message is communicated back to the model as context for its retry attempt.

## Retry Configuration — Three Levels

1. **Agent-level**: `Agent(retries=N)` or `AgentRetries` — default for all tools + outputs
2. **Tool-level**: `@agent.tool(retries=N)` decorator — per-tool override
3. **Run-level**: `agent.run(retries={'output': ...})` — per-run override

**Default retry count is 1** (configurable).

Within tools, check current retry progress with `ctx.retry` from the `RunContext` parameter.

## Validation Error Retries

Both function tool parameter validation errors AND structured output validation errors automatically trigger retries WITHOUT requiring explicit `ModelRetry`. The model receives validation failure details and attempts correction.

## Error Feedback to Model

When `ModelRetry` is raised, the error message string goes directly back to the model as the tool result for that turn. The model sees "No user found with name 'foo'" and tries again with different arguments.

## Output Retry Limits

- **Text output** (`output_type=str`): Global budget; exhausted → raises `UnexpectedModelBehavior: 'Exceeded maximum output retries (N)'`
- **Tool output** (`output_type=ToolOutput(...)`): Per-tool limits via `ToolOutput(max_retries=N)`

## Key Ergonomic Properties

- `raise ModelRetry("message")` is 1 line from inside any tool
- Error message reaches model automatically on next turn
- Malformed args (Pydantic validation) auto-retry without any extra code
- Per-tool AND per-agent retry budgets prevent runaway loops
- Production guidance: "set `retries=2` on your agent and handle `UnexpectedModelBehavior`"
