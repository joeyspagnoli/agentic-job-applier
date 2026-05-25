# Claude Agent SDK — BYO Python Tool Registration (Scenario A)

Source: https://code.claude.com/docs/en/agent-sdk/custom-tools

## Registration Ceremony

```python
from claude_agent_sdk import tool, create_sdk_mcp_server, query, ClaudeAgentOptions

@tool(
    "click_element",
    "Click a DOM element by CSS selector",
    {"selector": str},
)
async def click_element(args: dict) -> dict:
    await page.click(args["selector"])
    return {"content": [{"type": "text", "text": "clicked"}]}

# Mandatory: wrap in in-process MCP server
browser_server = create_sdk_mcp_server(
    name="browser",
    version="1.0.0",
    tools=[click_element],
)

options = ClaudeAgentOptions(
    mcp_servers={"browser": browser_server},
    allowed_tools=["mcp__browser__click_element"],
)
async for message in query(prompt="...", options=options): ...
```

## LOC Count: ~12 lines of registration ceremony
**Most verbose of all 6 harnesses.** Requires: `@tool` decorator (3 args: name, description, schema dict), `create_sdk_mcp_server()` call, `mcp_servers=` dict entry, `allowed_tools=` list entry.

## Key Constraint
No direct function-to-tool path. Every BYO function must:
1. Be decorated with `@tool(name, description, schema_dict)`
2. Be wrapped in `create_sdk_mcp_server()`
3. Be added to `mcp_servers=` dict
4. Be added to `allowed_tools=` list

The handler return format is also non-standard: must return `{"content": [{"type": "text", "text": "..."}]}` (MCP CallToolResult format).

## Primary Source
https://code.claude.com/docs/en/agent-sdk/custom-tools

## Ergonomics Rating: Poor for BYO tools
Highest ceremony of all 6. However, the upside is total uniformity — BYO and external tools are identical at the agent level (both are MCP).
