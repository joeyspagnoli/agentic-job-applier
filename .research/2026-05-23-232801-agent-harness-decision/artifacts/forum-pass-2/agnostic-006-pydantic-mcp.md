# Pydantic AI — MCP Client Support

Source: https://pydantic.dev/docs/ai/mcp/client/
Overview: https://pydantic.dev/docs/ai/mcp/overview/

## Status
Fully supported (not beta). Three connection types: `MCPServerStdio`, `MCPServerStreamableHTTP`, `MCPServerSSE` (deprecated).

## External Server Connectivity
Yes — can connect to any external MCP server.

## Registration Ceremony (Python)

```python
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStdio

server = MCPServerStdio('npx', args=['-y', '@playwright/mcp'])
agent = Agent('anthropic:claude-opus-4-5', toolsets=[server])

async with agent:
    result = await agent.run('Navigate to example.com')
```

Registration: **3 lines** (server + agent + run). The cleanest of all 6 harnesses.

## HTTP Variant

```python
from pydantic_ai.mcp import MCPServerStreamableHTTP
server = MCPServerStreamableHTTP('http://localhost:8931/mcp')
agent = Agent('openai:gpt-5.2', toolsets=[server])
```

2 lines to swap from stdio to HTTP — just change the server class.

## Multi-Source Composition
`toolsets=[]` accepts a list. BYO `@agent.tool` functions, MCP servers, and `FastMCPToolset` instances can all coexist:

```python
@agent.tool_plain
def click_ref(ref: str) -> str: ...

server = MCPServerStdio('npx', args=['-y', '@playwright/mcp'])
agent = Agent(model, toolsets=[server])  # BYO tool registered via decorator, MCP server via toolsets
```

Note: BYO tools use `@agent.tool` / `@agent.tool_plain` decorators (instance methods on the agent), while MCP servers go in `toolsets=`. They coexist without conflict.

## Swapping Browser Layers
Swapping from BYO Playwright to Playwright MCP requires only changing `toolsets=[MCPServerStdio(...)]` and removing the decorator-registered tools. The agent definition stays unchanged.
