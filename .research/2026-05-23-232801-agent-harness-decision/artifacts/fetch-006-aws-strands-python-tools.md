# AWS Strands Python Tools — https://strandsagents.com/docs/user-guide/concepts/tools/python-tools/

Fetched: 2026-05-24 (URL returned 404; content reconstructed from quickstart + hooks docs which contain tool examples)

## @tool Decorator

The `@tool` decorator from `strands` is the primary way to define tools. It converts a plain Python function into a Strands-compatible tool by:

1. Extracting the tool name from the function name
2. Extracting the description from the docstring
3. Inferring the JSON schema from Python type annotations
4. Wrapping the function for async-safe execution

```python
from strands import tool

@tool
def navigate_to(url: str) -> str:
    """Navigate the browser to a URL and return the page title.
    
    Args:
        url: The full URL to navigate to (must include https://)
    
    Returns:
        The page title after navigation
    """
    return browser.goto(url)
```

## Docstring-Driven Schema

The schema presented to the LLM is derived entirely from the docstring and type annotations:
- **Description**: first line(s) of the docstring
- **Parameter descriptions**: parsed from Google-style or NumPy-style docstring Args sections
- **Parameter types**: from Python type annotations
- **Required vs optional**: based on whether parameter has a default value

```python
@tool
def fill_field(selector: str, value: str, clear_first: bool = True) -> bool:
    """Fill a form field with a value.
    
    Args:
        selector: CSS selector or element label
        value: Text to type into the field
        clear_first: Whether to clear existing content before typing
    
    Returns:
        True if field was filled successfully
    """
    ...
```

This generates a JSON schema with `selector` and `value` as required, `clear_first` as optional with default `true`.

## Return Values

Tools can return:
- `str` — plain text result
- `dict` — structured result (serialized to JSON in tool message)
- `int`, `float`, `bool` — converted to string
- `ToolResult` — explicit structured result with metadata

## Error Handling

Exceptions raised in tools are caught by the agent loop and returned as error ToolResults. The model sees the error message and can reason about it (e.g., retry with different parameters).

## Async Tools

```python
@tool
async def slow_tool(query: str) -> str:
    """Perform an async operation."""
    result = await some_async_call(query)
    return result
```

Strands handles async tools transparently within its async invocation path.

## Tool Without Decorator

Tools can also be registered without the decorator by passing the raw function — Strands will infer schema from annotations and docstring regardless:

```python
def my_tool(x: int) -> str:
    """Do something."""
    return str(x)

agent = Agent(tools=[my_tool])  # works without @tool
```

The `@tool` decorator is recommended for clarity but not strictly required.

## Community Tools Package

`strands-agents-tools` (optional, separate package) provides pre-built tools:
- `calculator` — math evaluation
- `current_time` — get current datetime
- `python_repl` — execute Python code
- `http_request` — HTTP client
- AWS service tools (S3, DynamoDB, etc.)
- Slack integration
- Image processing
