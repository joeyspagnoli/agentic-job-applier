# Source: https://openai.github.io/openai-agents-python/tools/
# Fetched: 2026-05-23

## Tool categories

1. **Hosted OpenAI tools** – run on OpenAI servers
2. **Local/runtime execution tools** – run in your environment
3. **Function calling** – wrap Python functions
4. **Agents as tools**
5. **Experimental Codex tool**

## @function_tool

```python
from agents import Agent, function_tool

@function_tool
async def fetch_weather(location: Location) -> str:
    """Fetch the weather for a given location.

    Args:
        location: The location to fetch the weather for.
    """
    return "sunny"

agent = Agent(name="Assistant", tools=[fetch_weather])
```

Schema inferred from `inspect` + `griffe`. Supports Google, Sphinx, and NumPy docstring formats. Disable with `use_docstring_info=False`.

### Constraints via Pydantic Field

```python
from typing import Annotated
from pydantic import Field
from agents import function_tool

@function_tool
def score_a(score: int = Field(..., ge=0, le=100, description="Score 0-100")) -> str:
    return f"Score recorded: {score}"
```

### Error handling

```python
def my_custom_error_function(context, error: Exception) -> str:
    return "An internal error occurred. Please try again later."

@function_tool(failure_error_function=my_custom_error_function)
def get_user_profile(user_id: str) -> str:
    pass
```

### Timeouts

```python
@function_tool(timeout=2.0)
async def slow_lookup(query: str) -> str:
    await asyncio.sleep(10)
    return f"Result for {query}"
```

`timeout_behavior="error_as_result"` (default) or `"raise_exception"`.

## Hosted tools (Responses API only)

- `WebSearchTool`, `FileSearchTool`, `CodeInterpreterTool`, `HostedMCPTool`, `ImageGenerationTool`, `ToolSearchTool`

```python
agent = Agent(
    name="Assistant",
    tools=[
        WebSearchTool(),
        FileSearchTool(max_num_results=3, vector_store_ids=["VECTOR_STORE_ID"]),
    ],
)
```

### Deferred tool loading

```python
@function_tool(defer_loading=True)
def get_customer_profile(customer_id: str) -> str:
    """Fetch a CRM customer profile."""
    return f"profile for {customer_id}"

agent = Agent(
    name="Operations assistant",
    tools=[get_customer_profile, ToolSearchTool()],
)
```

## Custom FunctionTool (manual)

```python
from agents import FunctionTool

async def run_function(ctx, args: str) -> str:
    parsed = FunctionArgs.model_validate_json(args)
    return do_some_work(data=f"{parsed.username} is {parsed.age}")

tool = FunctionTool(
    name="process_user",
    description="Processes extracted user data",
    params_json_schema=FunctionArgs.model_json_schema(),
    on_invoke_tool=run_function,
)
```

## Agents as tools

```python
spanish_agent = Agent(name="Spanish agent", instructions="...")
orchestrator_agent = Agent(
    name="orchestrator_agent",
    tools=[spanish_agent.as_tool(tool_name="translate_to_spanish", tool_description="Translate to Spanish")],
)
```

Supports structured input (`parameters=TranslationInput`), custom output extraction, streaming events, conditional `is_enabled`.

## Local runtime tools

```python
class NoopComputer(AsyncComputer):
    environment = "browser"
    dimensions = (1024, 768)
    async def screenshot(self): return ""
    # ... other methods

async def run_shell(request):
    return "shell output"

agent = Agent(
    name="Local tools agent",
    tools=[
        ShellTool(executor=run_shell),
        ComputerTool(),  # Requires Computer/AsyncComputer implementation
    ],
)
```

## Codex (experimental)

```python
from agents.extensions.experimental.codex import codex_tool, ThreadOptions

agent = Agent(
    name="Codex Agent",
    tools=[
        codex_tool(
            sandbox_mode="workspace-write",
            working_directory="/path/to/repo",
            default_thread_options=ThreadOptions(
                model="gpt-5.5",
                approval_policy="never",
            ),
        )
    ],
)
```
