# AWS Strands Agents Python Quickstart — https://strandsagents.com/docs/user-guide/quickstart/python/

Fetched: 2026-05-24

## Requirements

- Python 3.10+
- `pip install strands-agents` (core)
- Optional: `pip install strands-agents-tools` (community tool library)
- Optional: `pip install 'strands-agents[openai]'` for OpenAI provider

## Minimal Agent

```python
from strands import Agent, tool
from strands_tools import calculator, current_time

@tool
def letter_counter(word: str, letter: str) -> int:
    """Count occurrences of a specific letter in a word."""
    if len(letter) != 1:
        raise ValueError("The 'letter' parameter must be a single character")
    return word.lower().count(letter.lower())

agent = Agent(tools=[calculator, current_time, letter_counter])
agent("What time is it? Calculate 100 * 50. Count R's in 'strawberry'")
```

## Default Model Provider

By default, Strands uses **Amazon Bedrock** with Claude Sonnet 4. This requires:
- AWS credentials configured (environment variables, `~/.aws/credentials`, or IAM role)
- Bedrock model access enabled for Claude 4 Sonnet in us-west-2

**This is a hard requirement for the default setup.** Non-technical Windows users without AWS accounts cannot use the default configuration.

## Alternate Providers (no AWS required)

```python
# OpenAI
from strands import Agent
from strands.models.openai import OpenAIModel

model = OpenAIModel(
    client_args={"api_key": "sk-..."},
    model_id="gpt-4o",
)
agent = Agent(model=model, tools=[my_tool])

# Anthropic direct
from strands.models.anthropic import AnthropicModel
model = AnthropicModel(model_id="claude-sonnet-4-5")

# LiteLLM (any provider)
from strands.models.litellm import LiteLLMModel
model = LiteLLMModel(model_id="openai/gpt-4o")

# Ollama (local, no API key)
from strands.models.ollama import OllamaModel
model = OllamaModel(model_id="llama3.2")
```

## Agent Result

```python
result = agent("What is 2 + 2?")
print(result)           # prints final response text
print(result.metrics)   # token counts, latency, etc.
```

## Async / Streaming

```python
# Async streaming for web frameworks
async for event in agent.stream_async(prompt):
    if "data" in event:
        print(event["data"], end="", flush=True)
```

## Disabling Console Output

```python
agent = Agent(tools=[...], callback_handler=None)
```

## Package Dependencies (strands-agents core)

Key dependencies pulled in:
- `opentelemetry-sdk`, `opentelemetry-api` (tracing)
- `pydantic` (schemas)
- `docstring-parser` (tool schema from docstrings)
- `boto3`, `botocore` (present even if using non-Bedrock provider — Bedrock is the default)
- `mcp` (Model Context Protocol client)
- `watchdog`, `pyyaml`, `jsonschema`

**boto3/botocore are core dependencies, not optional**, even for OpenAI-only usage. This adds ~8 MB to the install footprint.
