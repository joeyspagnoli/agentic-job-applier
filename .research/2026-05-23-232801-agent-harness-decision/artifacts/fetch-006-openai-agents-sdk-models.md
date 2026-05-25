# Source: https://openai.github.io/openai-agents-python/models/
# Fetched: 2026-05-24

## Overview

The SDK natively supports two OpenAI model backends:
- `OpenAIResponsesModel` (default) — uses the Responses API.
- `OpenAIChatCompletionsModel` — uses the Chat Completions API.

## Non-OpenAI Models

Three integration points:

### 1. Global Default via `set_default_openai_client`

```python
from agents import Agent, AsyncOpenAI, OpenAIChatCompletionsModel

client = AsyncOpenAI(api_key="your_key", base_url="https://your-endpoint.com")
model = OpenAIChatCompletionsModel(model="model-name", openai_client=client)
agent = Agent(name="Agent", instructions="...", model=model)
```

Use when one OpenAI-compatible endpoint serves all agents.

### 2. Per-Run via `ModelProvider`

Apply a custom provider to all agents in a single `Runner.run(...)` call.

### 3. Per-Agent via `Agent.model`

```python
agent = Agent(name="Agent", model=OpenAIChatCompletionsModel(...))
```

## Disabling Tracing for Non-OpenAI Providers

```python
from agents import set_tracing_disabled
set_tracing_disabled(disabled=True)
```

Without this, the SDK will attempt to POST traces to OpenAI's tracing endpoint and
get 401 errors if `OPENAI_API_KEY` is not set.

## LiteLLM Integration (Third-Party Adapter)

```bash
pip install openai-agents[litellm]
```

```python
from agents import Agent
from agents.extensions.models import LiteLLMModel

agent = Agent(
    name="Agent",
    model=LiteLLMModel(model="litellm/claude-3-5-sonnet"),
)
```

Or use `"litellm/..."` prefixes directly as the model string.

**Note:** `openai-agents[litellm]` is a separate optional install; it is not
currently in this repo's `pyproject.toml`.

## Mixing Models Within Workflows

```python
triage_agent = Agent(
    name="Triage",
    instructions="Route requests...",
    model="gpt-5.5",
    handoffs=[spanish_agent, english_agent],
)

spanish_agent = Agent(
    name="Spanish Agent",
    instructions="Respond in Spanish",
    model="gpt-5-mini",
)

english_agent = Agent(
    name="English Agent",
    instructions="Respond in English",
    model=OpenAIChatCompletionsModel(model="gpt-5-nano", openai_client=AsyncOpenAI()),
)
```

## ModelSettings

```python
from agents import Agent, ModelSettings

agent = Agent(
    name="Agent",
    model="gpt-4.1",
    model_settings=ModelSettings(
        temperature=0.1,
        parallel_tool_calls=False,
        truncation="auto",
        store=True,
    ),
)
```

## Runner-Managed Retries

```python
from agents import ModelRetrySettings, ModelSettings, retry_policies

agent = Agent(
    name="Assistant",
    model="gpt-5.5",
    model_settings=ModelSettings(
        retry=ModelRetrySettings(
            max_retries=4,
            backoff={"initial_delay": 0.5, "max_delay": 5.0, "multiplier": 2.0, "jitter": True},
            policy=retry_policies.any(
                retry_policies.provider_suggested(),
                retry_policies.network_error(),
                retry_policies.http_status([408, 429, 500, 502, 503, 504]),
            ),
        )
    ),
)
```

## Key Constraint for This Repo

The `openai-agents` package is **not** currently in `pyproject.toml`. Adding it
would require:
1. `openai-agents==<pin>` in `pyproject.toml`.
2. `openai-agents[litellm]` for non-OpenAI providers (or stick to
   `OpenAIChatCompletionsModel` with the existing `openai==2.26.0` client).
3. Disabling tracing unless an OpenAI key is always present.

The `LiteLLMModel` from `openai-agents` is conceptually identical to ADK's
`LiteLlm(model=...)` but from a different package namespace.
