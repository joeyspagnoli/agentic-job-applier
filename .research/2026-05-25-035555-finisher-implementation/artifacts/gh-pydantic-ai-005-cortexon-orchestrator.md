# Reference: `TheAgenticAI/CortexON` — multi-agent orchestrator with token tracking

**File:** `ta-browser/core/orchestrator.py`
**Repo:** https://github.com/TheAgenticAI/CortexON
**Fetched:** 2026-05-25 via `gh api`

## What's most relevant: per-agent token accumulation

```python
from pydantic_ai.result import Usage

class Orchestrator:
    def __init__(self, ...):
        self.cumulative_tokens = {
            'planner': {'total': 0, 'request': 0, 'response': 0},
            'browser': {'total': 0, 'request': 0, 'response': 0},
            'critique': {'total': 0, 'request': 0, 'response': 0}
        }

    def update_token_usage(self, agent_type: str, usage: Usage):
        self.cumulative_tokens[agent_type]['total'] += usage.total_tokens
        self.cumulative_tokens[agent_type]['request'] += usage.request_tokens
        self.cumulative_tokens[agent_type]['response'] += usage.response_tokens

    def log_token_usage(self, agent_type: str, usage: Usage, step: Optional[int] = None):
        self.update_token_usage(agent_type, usage)
        ...
```

**Pattern:** after each `agent.run()`, call `update_token_usage(agent_type, result.usage())`.
This is the clean way to track usage across the gate / tailor / review / finisher pipeline.

**Note:** They import `from pydantic_ai.result import Usage` — that import path was renamed
to `RunUsage` in `pydantic_ai.usage` somewhere around v1.0. This is a stale import for v1.102.
The CURRENT import is:

```python
from pydantic_ai.usage import RunUsage
```

## Tool registration — `@agent.tool_plain` for context-free, `@agent.tool` for context-aware

```python
@BA_agent.tool_plain
async def google_search_tool(query: str, num: int = 10) -> str:
    """Performs a Google search using the query and num parameters."""
    return await google_search(query=query, num=num)

@BA_agent.tool
async def bulk_enter_text_tool(ctx: RunContext[BA_Deps], entries) -> str:
    """Enters text into multiple DOM elements using a bulk operation."""
    return await bulk_enter_text(bc=ctx.deps.pm, entries=entries)

@BA_agent.tool
async def click_tool(ctx: RunContext[BA_Deps], selector: str,
                    wait_before_execution: float = 0.0) -> str:
    """Executes a click action on the element matching the given query selector."""
    return await click(bc=ctx.deps.pm, selector=selector, wait_before_execution=wait_before_execution)
```

**Verbatim 8-tool surface** — almost exactly the finisher tool list:

- `google_search_tool` (we don't need)
- `bulk_enter_text_tool` (our `fill`)
- `enter_text_tool` (our `fill` single)
- `get_dom_text` (our `get_snapshot`)
- `get_dom_fields` (alternative snapshot — fields-only)
- `get_url` (we don't need)
- `click_tool` (our `click`)
- `open_url_tool` (we don't need — Chrome already open)
- `extract_text_from_pdf_tool` (we don't need)
- `press_key_combination_tool` (we don't need)

## Agent settings worth copying

```python
BA_agent = Agent(
    model=model_instance,
    system_prompt=BA_SYS_PROMPT,
    deps_type=BA_Deps,
    name="Browser Agent",
    retries=3,                                  # <-- KEY: retries=3 for browser agent
    model_settings=ModelSettings(temperature=0.5),
)
```

**`retries=3`** is the operating value for a browser-driving agent in this prod codebase.
We should use the same or `retries=2`.

## `result_type` legacy (broken in v1.102)

```python
self.explainer_agent = Agent(
    model=model_instance,
    system_prompt=EXPLAINER_SYS_PROMPT,
    name="Explainer Agent",
    retries=2,
    model_settings=ModelSettings(temperature=0.2),
    result_type=ExplainerOutput   # <-- DEAD KWARG in v1.x
)
```

This is OLD code (pre-v0.6.0). On v1.102 this would fail with `TypeError: unexpected keyword
argument 'result_type'`. Use `output_type=` instead.

## DOM-history filter — interesting pattern

```python
def filter_dom_messages(messages):
    """Filter message history to replace all DOM responses with placeholder text."""
    DOM_TOOLS = {'get_dom_text', 'get_dom_fields'}
    ...
    new_part = ToolReturnPart(
        tool_name=part.tool_name,
        content="DOM successfully fetched",
        tool_call_id=part.tool_call_id,
        ...
    )
```

**Pattern:** they walk the agent's message history between runs and REPLACE old DOM snapshots
with the placeholder `"DOM successfully fetched"`. This prevents context bloat as the agent
takes more turns.

**For finisher:** each AX-tree snapshot can be 2-5K tokens. If we keep all 10-25 snapshots in
context, we blow through the OpenAI context window. We should adopt this filter — replace
all but the LATEST snapshot's `get_snapshot()` tool return with a stub like
`"[snapshot from turn N — superseded by turn N+k]"`.
