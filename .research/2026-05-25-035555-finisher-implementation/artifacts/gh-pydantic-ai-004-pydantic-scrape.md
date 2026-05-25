# Reference: `philmade/pydantic_scrape` — toolset packaging pattern

**File:** `pydantic_scrape/agents/playwright_browse_agent.py`
**Repo:** https://github.com/philmade/pydantic_scrape
**Fetched:** 2026-05-25 via `gh api`

## Key contribution: factor tools into a `toolset` module

```python
from ..toolsets.playwright_toolset import (
    PlaywrightContext,
    click_link_by_index,
    fill_form_bulk,
    fill_input,
    get_current_url,
    navigate_to,
    navigate_to_search,
    scroll_page,
    submit_form,
)

typed_agent = Agent(
    "openai:gpt-4o",
    deps_type=PlaywrightContext,
    output_type=task.output_type,
    tools=[
        navigate_to_search,
        click_link_by_index,
        scroll_page,
        fill_input,
        submit_form,
        fill_form_bulk,
        get_current_url,
    ],
    system_prompt=f"""...""",
)
```

**Pattern:** tool functions are written as **standalone module-level functions**, NOT decorators
attached to an agent. The agent imports them via `tools=[...]` constructor kwarg.

**Why this matters for finisher:**

- Easy to unit-test each tool in isolation (just call `await fill_input(ctx, ...)`).
- Easy to swap agents that share the same toolset (Greenhouse-tuned agent and Ashby-tuned agent
  can share the same 8 tools — `tools=GREENHOUSE_TOOLS` vs `tools=ASHBY_TOOLS` with one extra tool).
- The functions take `RunContext[PlaywrightContext]` as their first arg — the framework
  auto-detects this and treats them as context-aware tools.

## Dynamic instructions via `@agent.instructions`

```python
@typed_agent.instructions
def dynamic_playwright_instructions(
    ctx: RunContext[PlaywrightContext], conversation_history=conversation_history
) -> str:
    """JSON dump of PlaywrightContext - let Pydantic structure do the work"""
    if conversation_history:
        ch = ctx.deps.agent_context.format_conversation_history(5)
    else:
        ch = ""
    return f""" {ch} Current browsing context:{ctx.deps.render_state()} \
Use the tools to accomplish your objective. ..."""
```

**Takeaway:** dynamic context that changes per-turn (e.g., "fields already filled: [name, email]")
goes in `@agent.instructions`, NOT in `system_prompt`. System prompt is static; instructions are
re-evaluated each turn.

For finisher: `@finisher_agent.instructions` should emit the current `FormState` — "Fields
filled so far: {filled}. Fields remaining: {remaining}." This is exactly the "feedback signal
that prevents the model from re-filling already-filled fields" pattern.

## Generic output type via `Type[T]`

```python
class PlaywrightBrowseTask(BaseModel, Generic[T]):
    url: str
    objective: str = "Browse and extract information from the page"
    output_type: Union[Type[T], Type[str]] = str
```

This is overkill for finisher (we have one output type: `FinisherResult`). Don't copy.

## Notable weaknesses

- No `ModelRetry` usage anywhere — tools return error strings as plain return values.
- No `UsageLimits` set — relies on agent ending naturally. Bad pattern for production.
- No `agent.iter()` — uses one-shot `agent.run()` so can't enforce per-turn budgets.

Finisher must improve on all three.
