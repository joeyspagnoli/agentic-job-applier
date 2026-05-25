# Claude Agent SDK — Custom Tools (Full Documentation)

**Source:** https://code.claude.com/docs/en/agent-sdk/custom-tools  
**Fetched:** 2026-05-24

---

Custom tools extend the Agent SDK by letting you define your own functions that Claude can call during a conversation. Using the SDK's in-process MCP server, you can give Claude access to databases, external APIs, domain-specific logic, or any other capability your application needs.

## Quick Reference

| Goal | Mechanism |
|------|-----------|
| Define a tool | `@tool` (Python) or `tool()` (TypeScript) with name, description, schema, handler |
| Register with Claude | Wrap in `create_sdk_mcp_server` / `createSdkMcpServer`, pass to `mcpServers` in `query()` |
| Pre-approve a tool | Add to `allowed_tools` |
| Remove a built-in | Pass `tools` array listing only the built-ins you want (unlisted built-ins are removed) |
| Parallel read-only calls | Set `readOnlyHint: True` on tools with no side effects |
| Error without stopping loop | Return `is_error: True` instead of throwing |
| Return images | Use `image` blocks in content array (base64-encoded bytes, no data-URI prefix) |
| Return structured machine-readable data | Set `structuredContent` on the result |
| Scale to dozens of tools | Use tool search to load on demand |

---

## Tool Name Format

MCP tools exposed to Claude follow this pattern:
- Pattern: `mcp__{server_name}__{tool_name}`
- Example: tool `get_temperature` in server `weather` → `mcp__weather__get_temperature`
- Wildcards: `mcp__weather__*` covers all tools on that server

---

## Create a Custom Tool (Python)

```python
from typing import Any
import httpx
from claude_agent_sdk import tool, create_sdk_mcp_server

@tool(
    "get_temperature",
    "Get the current temperature at a location",
    {"latitude": float, "longitude": float},
)
async def get_temperature(args: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": args["latitude"],
                "longitude": args["longitude"],
                "current": "temperature_2m",
                "temperature_unit": "fahrenheit",
            },
        )
        data = response.json()

    return {
        "content": [
            {
                "type": "text",
                "text": f"Temperature: {data['current']['temperature_2m']}°F",
            }
        ]
    }

weather_server = create_sdk_mcp_server(
    name="weather",
    version="1.0.0",
    tools=[get_temperature],
)
```

**Input schema options in Python:**
- Dict of `name → type` (e.g., `{"latitude": float}`) — SDK converts to JSON Schema
- Full JSON Schema dict (needed for enums, ranges, optional fields, nested objects)

**Handler must return:**
- `content` (required): array of blocks with type `"text"`, `"image"`, or `"resource"`
- `structuredContent` (optional): JSON object for machine-readable data (TypeScript only via in-process server; Python needs standalone MCP server)
- `is_error` (optional, Python) / `isError` (TypeScript): signals tool failure so agent loop continues

---

## Call a Custom Tool

```python
import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage

async def main():
    options = ClaudeAgentOptions(
        mcp_servers={"weather": weather_server},
        allowed_tools=["mcp__weather__get_temperature"],
    )

    async for message in query(
        prompt="What's the temperature in San Francisco?",
        options=options,
    ):
        if isinstance(message, ResultMessage) and message.subtype == "success":
            print(message.result)

asyncio.run(main())
```

---

## Tool Annotations

Optional metadata via `annotations` kwarg or fifth `tool()` argument:

| Field | Default | Meaning |
|-------|---------|---------|
| `readOnlyHint` | `false` | No side effects — allows parallel calls |
| `destructiveHint` | `true` | May perform destructive updates |
| `idempotentHint` | `false` | Repeated calls are no-ops |
| `openWorldHint` | `true` | Reaches systems outside your process |

```python
from claude_agent_sdk import tool, ToolAnnotations

@tool(
    "get_temperature",
    "Get the current temperature at a location",
    {"latitude": float, "longitude": float},
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def get_temperature(args):
    ...
```

---

## Control Tool Access

`tools` option vs allow/deny lists affect two layers:

| Option | Layer | Effect |
|--------|-------|--------|
| `tools: ["Read", "Grep"]` | Availability | Only listed built-ins in context; unlisted removed |
| `tools: []` | Availability | All built-ins removed; Claude uses only MCP tools |
| `allowed_tools` | Permission | Listed tools auto-approved; unlisted fall through to permission mode |
| `disallowed_tools=["Bash"]` | Availability | Bare name removes tool from context entirely |
| `disallowed_tools=["Bash(rm *)"]` | Permission | Scoped rule denies matching calls; tool stays visible |

---

## Error Handling

Return `is_error: True` (not throw) to keep agent loop alive:

```python
@tool("fetch_data", "Fetch data from an API", {"endpoint": str})
async def fetch_data(args: dict[str, Any]) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(args["endpoint"])
            if response.status_code != 200:
                return {
                    "content": [{"type": "text", "text": f"API error: {response.status_code}"}],
                    "is_error": True,
                }
            return {"content": [{"type": "text", "text": response.text}]}
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"Failed: {str(e)}"}],
            "is_error": True,
        }
```

Uncaught exception = agent loop **stops**. Returning `is_error: True` = agent loop **continues**.

---

## Return Images

```python
import base64
import httpx

@tool("fetch_image", "Fetch an image from a URL and return it to Claude", {"url": str})
async def fetch_image(args):
    async with httpx.AsyncClient() as client:
        response = await client.get(args["url"])

    return {
        "content": [
            {
                "type": "image",
                "data": base64.b64encode(response.content).decode("ascii"),
                "mimeType": response.headers.get("content-type", "image/png"),
            }
        ]
    }
```

Key points:
- `data` field: raw base64 only — **no** `data:image/...;base64,` prefix
- `mimeType`: required (`image/png`, `image/jpeg`, `image/webp`, `image/gif`)
- Image bytes must be inline; no URL field in the image block

---

## Related Documentation

- Python SDK Reference: https://code.claude.com/docs/en/agent-sdk/python
- TypeScript SDK Reference: https://code.claude.com/docs/en/agent-sdk/typescript
- MCP Specification: https://modelcontextprotocol.io
- SDK Overview: https://code.claude.com/docs/en/agent-sdk/overview
