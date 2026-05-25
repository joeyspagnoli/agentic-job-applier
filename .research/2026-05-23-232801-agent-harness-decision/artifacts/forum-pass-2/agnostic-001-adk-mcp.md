# Google ADK — MCP Client Support

Source: https://adk.dev/tools-custom/mcp-tools/

## Status
First-class feature. Supported in Python v0.1.0+, TypeScript v0.2.0+, Go v0.1.0+, Java v0.1.0+.

## External Server Connectivity
Yes — ADK can connect to any standards-compliant MCP server. Two transport types:

- **stdio** — local subprocess via `StdioServerParameters`
- **HTTP (StreamableHTTP)** — remote/cloud servers via `StreamableHTTPConnectionParams`

## Registration Ceremony (Python)

```python
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset, StdioConnectionParams
from mcp import StdioServerParameters

toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command='npx',
            args=["-y", "@playwright/mcp"]
        )
    )
)
agent = LlmAgent(tools=[toolset])
```

Registration is roughly 5 lines. `McpToolset` handles lifecycle (connect, list tools, disconnect) automatically.

## Gotcha
The `McpToolset` is a context manager in Python — it must be used with `async with` or passed to the `runner` which manages it. If you pass it bare into `tools=[]`, you may hit lifecycle issues. The docs recommend letting the `runner` or `InMemoryRunner` manage it.

## Tool Filtering
Optional `tool_filter` parameter restricts which tools from the server are exposed to the agent.

## Multi-Server
Multiple `McpToolset` instances can be listed in `tools=[]` alongside BYO Python tools.
