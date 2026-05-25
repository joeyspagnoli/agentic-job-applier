# Source: https://adk.dev/tools/ + https://adk.dev/integrations/

Fetched 2026-05-23. The `/tools/` URL now redirects into `/integrations/`.

## Tool categories

ADK groups tool sources into:

- **Function tools** — plain Python functions added to `tools=[...]`. ADK introspects signature + docstring to build the schema. (See fetch-005 for full detail.)
- **Built-in tools** — Google Search, Code Execution, Vertex AI Search.
- **MCP tools** — first-class support for connecting to any MCP server.
- **Third-party tools** — wrappers for LangChain tools and CrewAI tools.
- **OpenAPI tools** — auto-generate a toolset from an OpenAPI spec.
- **Agents-as-tools** — wrap an `LlmAgent` in `AgentTool(...)` to call it as a sub-routine.
- **Computer Use Toolset** — `ComputerUseToolset(computer=PlaywrightComputer(...))`. See fetch-010.

## Integrations catalog (`/integrations/`)

The Integrations page is a catalog of 80+ pre-built integrations across:
- **Data & Search**: BigQuery, MongoDB, Pinecone, Qdrant, Redis, Chroma
- **Communication**: AgentMail, AgentPhone, ElevenLabs, Mailgun
- **Observability**: Datadog, Arize AX, AgentOps, LangWatch, Phoenix
- **Connectors**: GitHub, GitLab, Stripe, Asana, Notion, Linear
- **Enterprise**: Apigee API Hub, Atlassian, StackOne (200+ SaaS providers)
- **Resilience**: Temporal, Restate, DBOS, Dapr

The page directs custom-tool authors to a separate "Custom Tools" section covering:
- Function tools
- MCP tools
- OpenAPI tools
- Authentication

## Passing tools to an agent (verbatim pattern)

```python
def get_stock_price(symbol: str):
    """..."""
    ...

stock_price_agent = Agent(
    model="gemini-2.0-flash",
    name="stock_agent",
    tools=[get_stock_price]  # Automatically wrapped as FunctionTool
)
```

Functions in `tools=[...]` are auto-wrapped as `FunctionTool`. No manual `Tool(...)` boilerplate required.
