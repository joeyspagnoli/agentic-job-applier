# OpenAI Agents SDK — BYO Python Tool Registration (Scenario A)

Source: https://openai.github.io/openai-agents-python/tools/

## Registration Ceremony

```python
from agents import Agent, function_tool

@function_tool
def click_element(selector: str) -> str:
    """Click a DOM element by CSS selector using Playwright."""
    page.click(selector)
    return "clicked"

agent = Agent(
    name="browser_agent",
    instructions="Use browser tools to complete tasks.",
    tools=[click_element],
)
```

## LOC Count: ~2 lines of registration ceremony
`@function_tool` decorator on the function + `tools=[fn]` on the Agent.

## Requirements
- Type annotations required — SDK uses `inspect` + `griffe` + `pydantic` to extract schema.
- Docstring used as tool description.
- Supports sync and async functions.

## Primary Source
https://openai.github.io/openai-agents-python/tools/

## Ergonomics Rating: Excellent
Single decorator. Schema auto-extracted. Identical pattern to ADK's zero-ceremony approach.
