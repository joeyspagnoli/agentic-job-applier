# AWS Strands — MCP Client Support

Source: https://strandsagents.com/docs/user-guide/concepts/tools/mcp-tools/
Blog: https://aws.amazon.com/blogs/opensource/open-protocols-for-agent-interoperability-part-3-strands-agents-mcp/

## Status
First-class, built into core SDK. `MCPClient` implements `ToolProvider` interface — passed directly to `Agent(tools=[mcp_client])`.

## External Server Connectivity
Yes — stdio, Streamable HTTP, SSE transports supported.

## Registration Ceremony (Python)

```python
from mcp import stdio_client, StdioServerParameters
from strands import Agent
from strands.tools.mcp import MCPClient

mcp_client = MCPClient(lambda: stdio_client(
    StdioServerParameters(
        command="npx",
        args=["-y", "@playwright/mcp"]
    )
))

agent = Agent(tools=[mcp_client])
agent("Navigate to example.com")
```

Registration: ~7 lines. The lambda factory pattern is used for lifecycle management.

## Multi-Server
Multiple `MCPClient` instances can be listed in `tools=[]`:

```python
agent = Agent(tools=[byo_func, mcp_client_playwright, mcp_client_other])
```

## Tool Filtering and Name Prefixing
Both available in Python version — restricts exposed tools and prevents cross-server naming collisions.

## Elicitation
Strands contributes to MCP spec: supports elicitation callbacks (MCP server can request additional input from agent mid-execution) — relevant for browser tools that may need human confirmation.

## Long-Running MCP Servers
Amazon Bedrock AgentCore (public preview July 2025) supports long-running MCP servers (up to 8 hours) with async tool execution — relevant for browser automation sessions.
