# LangChain / LangGraph — MCP Client Support

Source: https://github.com/langchain-ai/langchain-mcp-adapters
Changelog: https://changelog.langchain.com/announcements/mcp-adapters-for-langchain-and-langgraph

## Status
**Adapter package** (`langchain-mcp-adapters`), not built into LangChain core. First released March 2025. Version 0.2.0 released December 9, 2025 — adds multimodal tool support, elicitation callbacks, structured tool output, and name prefixes for multi-server setups.

## External Server Connectivity
Yes — connects to any external MCP server via `MultiServerMCPClient`:

```python
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent

client = MultiServerMCPClient({
    "playwright": {
        "command": "npx",
        "args": ["-y", "@playwright/mcp"],
        "transport": "stdio",
    }
})
tools = await client.get_tools()
agent = create_react_agent("anthropic:claude-opus-4-5", tools)
response = await agent.ainvoke({"messages": "Navigate to example.com"})
```

Registration: ~8 lines. Tools come back as standard LangChain `BaseTool` objects.

## Key Note
MCP tools are converted to LangChain-compatible tools by the adapter. Once converted, they are indistinguishable from BYO `@tool`-decorated functions — same `BaseTool` interface.

## Multi-Server
`MultiServerMCPClient` accepts a dict of multiple servers. Tool name prefixing (0.2.0+) prevents naming collisions across servers.

## Multi-Source Composition
All tool sources (BYO `@tool` functions, MCP-converted tools, sub-agent wrappers) are just items in a Python `list[BaseTool]`. Mix freely:

```python
tools = byo_tools + await mcp_client.get_tools() + [wrapped_browser_use_tool]
agent = create_react_agent(model, tools)
```
