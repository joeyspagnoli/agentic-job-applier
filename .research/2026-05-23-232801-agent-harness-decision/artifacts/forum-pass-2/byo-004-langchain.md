# LangChain / LangGraph — BYO Python Tool Registration (Scenario A)

Source: https://docs.langchain.com/oss/python/langchain/tools

## Registration Ceremony

```python
from langchain.tools import tool
from langgraph.prebuilt import create_react_agent

@tool
def click_element(selector: str) -> str:
    """Click a DOM element by CSS selector using Playwright."""
    page.click(selector)
    return "clicked"

agent = create_react_agent("anthropic:claude-opus-4-5", tools=[click_element])
```

## LOC Count: ~2 lines of registration ceremony
`@tool` decorator + `tools=[fn]` in agent constructor.

## Requirements
- Type hints required for schema generation.
- Docstring used as tool description.
- Args section in docstring used for per-parameter descriptions.

## Alternative: StructuredTool for complex schemas
```python
from langchain.tools import StructuredTool
my_tool = StructuredTool.from_function(fn, name="click", description="...")
```

## Primary Source
https://docs.langchain.com/oss/python/langchain/tools
https://shazaali.substack.com/p/tools-in-langgraph

## Ergonomics Rating: Excellent
Standard Python decorator. Same `BaseTool` interface as MCP-converted tools after adapter conversion. Uniform list at the agent level.
