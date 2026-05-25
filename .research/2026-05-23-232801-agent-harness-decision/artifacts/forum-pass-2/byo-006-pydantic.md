# Pydantic AI — BYO Python Tool Registration (Scenario A)

Source: https://pydantic.dev/docs/ai/tools-toolsets/tools/
API: https://ai.pydantic.dev/tools/

## Registration Ceremony (Decorator Pattern)

```python
from pydantic_ai import Agent

agent = Agent('anthropic:claude-opus-4-5')

@agent.tool_plain
def click_element(selector: str) -> str:
    """Click a DOM element by CSS selector using Playwright."""
    page.click(selector)
    return "clicked"
```

## LOC Count: ~1 line of registration ceremony
The `@agent.tool_plain` decorator is the registration. No separate list, no wrapping.

## Alternative: Constructor tools list
```python
def click_element(selector: str) -> str:
    """Click a DOM element."""
    ...

agent = Agent('anthropic:claude-opus-4-5', tools=[click_element])
```

## Two Decorator Variants
- `@agent.tool_plain` — simple function, no agent context
- `@agent.tool` — function receives `RunContext` with deps/state

## Mixing with MCP
BYO tools via decorator coexist with MCP servers via `toolsets=[]`:
```python
server = MCPServerStdio('npx', args=['-y', '@playwright/mcp'])
agent = Agent(model, toolsets=[server])

@agent.tool_plain  # BYO tool registered separately
def my_byo_tool(x: str) -> str: ...
```

## Primary Source
https://pydantic.dev/docs/ai/tools-toolsets/tools/

## Ergonomics Rating: Best of all 6
Single decorator is the registration. No list management. Docstring auto-extracted. Most Pythonic pattern of all 6 harnesses.
