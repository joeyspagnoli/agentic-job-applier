# LangChain Tool Calling — https://python.langchain.com/docs/concepts/tool_calling/

Fetched: 2026-05-24 (original URL redirected to docs.langchain.com)

## What Tool Calling Is

Tool calling is the mechanism by which a chat model requests execution of a function. The model returns a structured tool_call request (name + arguments), the application executes the function, and returns the result as a ToolMessage. LangChain standardizes this across all providers.

## Defining Tools

### Plain Python Function (simplest)

```python
def multiply(a: int, b: int) -> int:
    """Multiply two numbers together."""
    return a * b
```

Any function with a docstring and type-annotated arguments can be passed directly to `bind_tools()` or `create_react_agent()`. LangChain automatically infers the JSON schema from annotations.

### @tool Decorator

```python
from langchain_core.tools import tool

@tool
def multiply(a: int, b: int) -> int:
    """Multiply two numbers together."""
    return a * b

print(multiply.name)         # "multiply"
print(multiply.description)  # "Multiply two numbers together."
print(multiply.args_schema.schema())  # JSON schema
```

The `@tool` decorator adds `.name`, `.description`, `.args_schema` attributes and makes the function a `BaseTool` subclass.

### StructuredTool / Pydantic Input Schema

```python
from langchain_core.tools import StructuredTool
from pydantic import BaseModel

class SearchInput(BaseModel):
    query: str
    max_results: int = 10

search = StructuredTool.from_function(
    func=run_search,
    name="web_search",
    description="Search the web",
    args_schema=SearchInput,
)
```

## Binding Tools to a Model

```python
from langchain_openai import ChatOpenAI

model = ChatOpenAI(model="gpt-4o")
model_with_tools = model.bind_tools([multiply, search])

response = model_with_tools.invoke("What is 3 * 4?")
# response.tool_calls = [{"name": "multiply", "args": {"a": 3, "b": 4}, "id": "call_xyz"}]
```

## Executing Tool Calls

```python
from langchain_core.messages import ToolMessage

for tool_call in response.tool_calls:
    result = multiply.invoke(tool_call["args"])
    messages.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))
```

In LangGraph's `ToolNode` this is handled automatically.

## Tool Call Flow Summary

1. User message → model
2. Model returns AIMessage with `tool_calls`
3. Application executes each tool
4. ToolMessage results appended to message list
5. Model called again with full history
6. Repeat until model returns AIMessage without `tool_calls`

## Forced Tool Calls

```python
model.bind_tools(tools, tool_choice="multiply")  # always call multiply
model.bind_tools(tools, tool_choice="any")        # must call at least one tool
model.bind_tools(tools, tool_choice="auto")       # model decides (default)
```

## Error Handling

Tools can raise exceptions. LangGraph's `ToolNode` catches exceptions and returns them as `ToolMessage` content with `status="error"`, allowing the model to reason about errors and retry.
