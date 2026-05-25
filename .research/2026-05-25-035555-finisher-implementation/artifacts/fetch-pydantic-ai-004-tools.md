# Pydantic AI — Tool registration API

**URL:** https://pydantic.dev/docs/ai/tools-toolsets/tools/ (redirected from https://ai.pydantic.dev/tools/)
**Fetched:** 2026-05-25
**Prompt:** @agent.tool vs @agent.tool_plain, tools=[...] kwarg, RunContext, ModelRetry.

## Decorator registration

### `@agent.tool` — context-aware

```python
@agent.tool
def get_player_name(ctx: RunContext[str]) -> str:
    """Get the player's name."""
    return ctx.deps
```

`RunContext[T]` exposes `.deps: T`, `.usage`, `.messages`, `.tool_call_id`, `.retry`.

### `@agent.tool_plain` — context-free

```python
@agent.tool_plain
def roll_dice() -> str:
    """Roll a six-sided die and return the result."""
    return str(random.randint(1, 6))
```

## Constructor registration

```python
agent = Agent(
    'openai:gpt-5.2',
    deps_type=BrowserDeps,
    tools=[roll_dice, get_player_name],
    instructions="..."
)
```

The framework inspects function signatures to auto-detect if `RunContext` is required.

### Explicit `Tool` wrapper

```python
from pydantic_ai import Tool

agent = Agent(
    'openai:gpt-5.2',
    deps_type=BrowserDeps,
    tools=[
        Tool(click, takes_ctx=True),
        Tool(roll_dice, takes_ctx=False),
    ]
)
```

## Dependency injection

```python
@dataclass
class BrowserDeps:
    page: Page  # Playwright Page
    cache: AnswerCache
    profile: CandidateProfile

agent = Agent(model='openai:gpt-5.2', deps_type=BrowserDeps)
result = await agent.run('Fill the application', deps=BrowserDeps(page, cache, profile))
```

Inside a tool: `ctx.deps.page` gives you the Playwright Page.

## Docstring-driven schema

```python
@agent.tool_plain(docstring_format='google', require_parameter_descriptions=True)
def fill(ref: str, value: str) -> str:
    """Fill a form field.

    Args:
        ref: stable ref like @e1 from the snapshot
        value: text to type
    """
    ...
```

Pydantic extracts param descriptions from Google/NumPy/Sphinx docstrings.

## ModelRetry pattern

```python
from pydantic_ai import ModelRetry

@agent.tool
async def click(ctx: RunContext[BrowserDeps], ref: str) -> str:
    """Click element by ref."""
    locator = ctx.deps.snapshot.resolve(ref)
    if locator is None:
        raise ModelRetry(
            f"Ref {ref} not found in current snapshot. Call get_snapshot() first."
        )
    try:
        await locator.click(timeout=2000)
    except PlaywrightTimeout:
        raise ModelRetry(
            f"Click on {ref} timed out — the element may have re-rendered. "
            "Call get_snapshot() and retry with the fresh ref."
        )
    return f"clicked {ref}"
```

The `ModelRetry` exception is caught by the agent loop and surfaced to the model as a tool-failure
message, allowing the model to retry. The retry budget is governed by `Agent(retries=...)`.

## Anti-patterns called out in docs

- Don't catch the `ModelRetry` inside the tool — let it propagate.
- Don't `raise ModelRetry` without a useful message; the model needs to know what to do differently.
- The retry budget interacts with `UsageLimits.request_limit` — exhausting retries still counts
  against the request budget.
