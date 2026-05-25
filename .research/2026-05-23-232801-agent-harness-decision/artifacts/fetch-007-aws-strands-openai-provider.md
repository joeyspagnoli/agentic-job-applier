# AWS Strands OpenAI Provider — https://strandsagents.com/docs/user-guide/concepts/model-providers/openai/

Fetched: 2026-05-24

## Installation

OpenAI support is an optional extra dependency (not included in the base `strands-agents` package):

```bash
pip install 'strands-agents[openai]'
```

## Basic Usage

```python
from strands import Agent
from strands.models.openai import OpenAIModel
from strands_tools import calculator

model = OpenAIModel(
    client_args={"api_key": "sk-..."},
    model_id="gpt-4o",
    params={"max_tokens": 1000, "temperature": 0.7}
)

agent = Agent(model=model, tools=[calculator])
response = agent("What is 2+2")
```

## Configuration Parameters

| Parameter | Type | Purpose |
|-----------|------|---------|
| `client_args` | dict | Passed to `AsyncOpenAI(...)` — includes `api_key`, `base_url`, `timeout`, etc. |
| `model_id` | str | Model identifier (e.g., "gpt-4o", "gpt-4o-mini") |
| `params` | dict | Per-call model parameters (`max_tokens`, `temperature`, `top_p`, etc.) |

## OpenAI-Compatible Endpoints (LiteLLM proxy, local models)

The `base_url` in `client_args` enables any OpenAI-compatible server:

```python
# LiteLLM proxy
model = OpenAIModel(
    client_args={
        "api_key": "placeholder",
        "base_url": "http://localhost:4000"
    },
    model_id="gpt-4o"
)

# Local vLLM
model = OpenAIModel(
    client_args={
        "api_key": "not-needed",
        "base_url": "http://localhost:8000/v1"
    },
    model_id="meta-llama/Meta-Llama-3-8B-Instruct"
)
```

This is critical for self-hosted deployments where no cloud API key is available.

## Custom Client Instance

Pass a pre-configured `AsyncOpenAI` client directly:

```python
from openai import AsyncOpenAI

custom_client = AsyncOpenAI(
    api_key="sk-...",
    timeout=30.0,
    max_retries=2,
)

model = OpenAIModel(client=custom_client, model_id="gpt-4o")
```

The application manages the client lifecycle in this case.

## GPT-OSS / Open Source Model Quirk

Some GPT-compatible OSS models emit unexpected stop tokens. Fix:

```python
model = OpenAIModel(
    client_args={"api_key": "...", "base_url": "..."},
    model_id="mistral-7b",
    params={"stop": ["<|call|>", "<|return|>", "<|end|>"]}
)
```

## Integration with Existing openai==2.26.0

The repo already pins `openai==2.26.0`. Strands' OpenAI provider uses the `openai` SDK internally. **Version compatibility must be verified** — `strands-agents[openai]` may require a different `openai` version than the pinned `2.26.0`. This is a real integration risk.

## Relevance to Our Use Case

Our repo already has `openai==2.26.0` and `litellm==1.82.1`. Strands' LiteLLM provider is likely safer than the native OpenAI provider for avoiding version conflicts:

```python
from strands.models.litellm import LiteLLMModel

model = LiteLLMModel(model_id="openai/gpt-4o")  # routes through litellm
```

This lets Strands use our already-pinned `litellm` as the model backend, avoiding direct `openai` version conflicts.
