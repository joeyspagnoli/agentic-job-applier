# Claude Agent SDK — MCP Client Support

Source: https://code.claude.com/docs/en/agent-sdk/mcp

## Status
First-class. MCP is the primary (and only) mechanism for both external servers and custom tools. There is no separate "function tool" registration path — even BYO tools must go through `create_sdk_mcp_server()`.

## External Server Connectivity
Yes — connects to any external MCP server via:
- **stdio**: `command` + `args` dict (e.g., `npx @playwright/mcp`)
- **HTTP**: `type: "http"` + `url`
- **SSE**: `type: "sse"` + `url`

## Registration Ceremony (Python, external server)

```python
options = ClaudeAgentOptions(
    mcp_servers={
        "playwright": {
            "command": "npx",
            "args": ["-y", "@playwright/mcp"],
        }
    },
    allowed_tools=["mcp__playwright__*"],
)
async for message in query(prompt="...", options=options):
    ...
```

Registration: 8 lines. The `allowed_tools` wildcard is required — without it, Claude sees the tools but cannot call them.

## Key Constraint
BYO Python tools must be wrapped in `create_sdk_mcp_server()` first, then passed via `mcp_servers=`. This adds ~5 extra lines of boilerplate per tool group compared to frameworks with direct function registration:

```python
@tool("my_tool", "Description", {"param": str})
async def my_tool(args): ...

server = create_sdk_mcp_server(name="mytools", version="1.0.0", tools=[my_tool])
options = ClaudeAgentOptions(
    mcp_servers={"mytools": server},
    allowed_tools=["mcp__mytools__my_tool"],
)
```

## Tool Search
Enabled by default. Withholds tool definitions from context window and loads only tools Claude needs per turn — important when mixing many browser tools.

## Multi-Source Composition
`mcp_servers={}` dict accepts multiple keys (multiple servers). BYO + external MCP + sub-agent tools can all coexist as separate server entries.
