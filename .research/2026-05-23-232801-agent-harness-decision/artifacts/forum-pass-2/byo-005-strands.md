# AWS Strands — BYO Python Tool Registration (Scenario A)

Source: https://strandsagents.com/docs/user-guide/concepts/tools/custom-tools/
Blog: https://dev.to/aws/building-strands-agents-with-a-few-lines-of-code-custom-tools-and-mcp-integration-3c1c

## Registration Ceremony

```python
from strands import Agent, tool

@tool
def click_element(selector: str) -> str:
    """Click a DOM element by CSS selector using Playwright.
    
    Args:
        selector: CSS selector for the element to click.
    """
    page.click(selector)
    return "clicked"

agent = Agent(tools=[click_element])
```

## LOC Count: ~2 lines of registration ceremony
`@tool` decorator + `tools=[fn]`.

## Optional Name/Description Override
```python
@tool(name="click", description="Click element by selector")
def click_element(selector: str) -> str: ...
```

## Requirements
- Type hints required.
- Docstring + Args section used for tool description and parameter docs.

## Primary Source
https://strandsagents.com/docs/user-guide/concepts/tools/custom-tools/
https://dev.to/aws/building-strands-agents-with-a-few-lines-of-code-custom-tools-and-mcp-integration-3c1c

## Ergonomics Rating: Excellent
Same `tools=[]` list accepts both `@tool` functions and `MCPClient` instances — uniform mixing interface. Single list, no separation between BYO and MCP sources.
