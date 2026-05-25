# Google ADK — BYO Python Tool Registration (Scenario A)

Source: https://adk.dev/tools-custom/function-tools/

## Registration Ceremony

```python
from google.adk.agents import LlmAgent

def click_element(selector: str) -> dict:
    """Click a DOM element by CSS selector using Playwright.
    
    Args:
        selector: CSS selector for the element to click.
    Returns:
        dict with 'status' key.
    """
    page.click(selector)
    return {"status": "clicked"}

agent = LlmAgent(
    name="browser_agent",
    model="gemini-2.5-flash",
    tools=[click_element],  # Pass function directly
)
```

## LOC Count: ~2 lines of registration ceremony
Pass any Python function directly in `tools=[]`. ADK auto-wraps it as `FunctionTool`.

## Requirements
- Docstring is **required** — ADK uses it as the tool description for the LLM.
- Type hints are **required** — parameter types derived from hints.
- Supports sync and async functions.

## Primary Source
https://google.github.io/adk-docs/tools/function-tools/ (redirects to adk.dev)

## Ergonomics Rating: Excellent
Zero boilerplate. Works with any callable. Docstring serves double duty as documentation and tool description.
