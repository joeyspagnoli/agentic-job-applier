# Pydantic AI — Structured output modes

**URL:** https://pydantic.dev/docs/ai/core-concepts/output/
**Fetched:** 2026-05-25

## Confirmed kwarg name: `output_type`

`result_type` was removed in v0.6.0 (2025-08-06). The current name in v1.x is **`output_type`**.

## Basic usage

```python
from pydantic import BaseModel
from pydantic_ai import Agent

class CityLocation(BaseModel):
    city: str
    country: str

agent = Agent('openai:gpt-5.2', output_type=CityLocation)
result = agent.run_sync('Where were the olympics held in 2012?')
print(result.output)  # CityLocation(city='London', country='United Kingdom')
```

## Three output modes

### 1. `ToolOutput` (default) — most reliable

```python
from pydantic_ai import Agent, ToolOutput

agent = Agent(
    'openai:gpt-5.2',
    output_type=[
        ToolOutput(Fruit, name='return_fruit'),
        ToolOutput(Vehicle, name='return_vehicle'),
    ],
)
```

The model "returns" the output by calling a synthetic tool. Works on every provider.

### 2. `NativeOutput` — uses provider's JSON-mode

```python
from pydantic_ai import Agent, NativeOutput
agent = Agent('openai:gpt-5.2', output_type=NativeOutput([Fruit, Vehicle]))
```

OpenAI Structured Outputs, Gemini structured output, etc. Cheaper and faster but provider-specific.

### 3. `PromptedOutput` — injects schema into the prompt

```python
from pydantic_ai import Agent, PromptedOutput
agent = Agent('openai:gpt-5.2', output_type=PromptedOutput([Fruit, Vehicle]))
```

Works on all models; least reliable.

## Recommendation for finisher

For a `FinisherResult` Pydantic model returned by `complete_apply()`, the best fit is:

- **Default ToolOutput** — but our `complete_apply` tool already IS a tool, so returning the
  `FinisherResult` directly from that tool body is the cleanest pattern (no separate output
  type). The agent declares `output_type=FinisherResult` and the tool returns a
  `FinisherResult` instance; Pydantic AI handles the coercion.

- Avoid `NativeOutput` if we want to keep provider portability across the audit / tailor /
  finisher trio.
