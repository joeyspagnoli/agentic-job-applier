# OpenAI Agents SDK — MCP Client Support

Source: https://openai.github.io/openai-agents-python/mcp/

## Status
First-class. Five transport options built into the core SDK (not an adapter).

## External Server Connectivity
Yes — connects to any external MCP server via:
1. Streamable HTTP (`MCPServerStreamableHttp`)
2. HTTP + SSE (`MCPServerSse`, deprecated)
3. stdio (`MCPServerStdio`)
4. Hosted MCP tool (OpenAI Responses API handles remote calls)
5. MCP server manager (orchestrates multiple)

## Registration Ceremony (Python)

```python
from agents import Agent, Runner
from agents.mcp import MCPServerStreamableHttp

async with MCPServerStreamableHttp(
    name="playwright",
    params={"url": "http://localhost:8931/mcp"}
) as server:
    agent = Agent(
        name="browser_agent",
        instructions="Use browser tools to complete tasks.",
        mcp_servers=[server]
    )
    result = await Runner.run(agent, "Navigate to example.com")
```

Registration: ~8 lines including context manager. The `async with` is required for lifecycle management.

## Additional Features
- Tool filtering: static allow/block lists or dynamic per-call context
- `tool_meta_resolver`: inject tenant IDs or trace context per call
- Optional caching of server tool definitions (performance optimization)
- Automatic tracing of MCP activity

## Multi-Source Composition
`mcp_servers=[server1, server2]` + `tools=[byo_tool1, byo_tool2]` are separate lists — BYO function tools go in `tools=[]`, MCP servers go in `mcp_servers=[]`. Both lists coexist on the same `Agent`.
