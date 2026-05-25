# Source: https://adk.dev/agents/models/ + https://adk.dev/agents/models/litellm/
# Fetched: 2026-05-24

## Model Integration Options in ADK

ADK supports three mechanisms for attaching a model to an `LlmAgent`:

1. **Direct string** — Gemini model IDs only (e.g. `"gemini-2.5-flash"`). ADK
   resolves these internally via the Google GenAI SDK.
2. **Model connectors** — Wrapper classes for non-Gemini providers:
   `LiteLlm(...)`, `ApigeeLlm(...)`. Passed as the `model=` parameter.
3. **Model routing** — Dynamic selection across multiple models at runtime
   (advanced; not needed for our use case).

## LiteLlm — The Non-Gemini Path

`google.adk.models.lite_llm.LiteLlm` wraps LiteLLM to proxy any provider that
LiteLLM supports.

### Import

```python
from google.adk.models.lite_llm import LiteLlm
```

### Model String Format

LiteLLM uses `"provider/model-name"` strings. The prefix routes to the right
credentials and endpoint:

| Provider | Model string example | Env var needed |
|---|---|---|
| OpenAI | `"openai/gpt-4o"` | `OPENAI_API_KEY` |
| OpenAI | `"openai/gpt-5-mini"` | `OPENAI_API_KEY` |
| Anthropic | `"anthropic/claude-3-5-sonnet-20241022"` | `ANTHROPIC_API_KEY` |
| Anthropic | `"anthropic/claude-3-haiku-20240307"` | `ANTHROPIC_API_KEY` |
| Ollama | `"ollama/llama3"` | none (local) |
| Azure OpenAI | `"azure/gpt-4o"` | `AZURE_API_KEY` + `AZURE_API_BASE` |

### Complete Usage Example

```python
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

# OpenAI GPT-4o
agent_openai = LlmAgent(
    model=LiteLlm(model="openai/gpt-4o"),
    name="openai_agent",
    instruction="You are a helpful assistant powered by GPT-4o.",
    tools=[...],
)

# Anthropic Claude Haiku
agent_claude = LlmAgent(
    model=LiteLlm(model="anthropic/claude-3-haiku-20240307"),
    name="claude_agent",
    instruction="You are an assistant powered by Claude Haiku.",
    tools=[...],
)
```

## This Repo's Pattern

`src/agents/shared/model.py` centralizes LiteLlm construction:

```python
from google.adk.models.lite_llm import LiteLlm

def build_openai_litellm_model(*, model_name: str) -> Any:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set for the decider model.")
    return LiteLlm(model=model_name)
```

`root_apply_decider` calls this with `model_name="openai/gpt-5-mini"`. The
same helper can be called with any LiteLLM provider string for the browser-finisher
(e.g. `"openai/gpt-4.1-mini"` for low cost, or `"anthropic/claude-haiku-4-5"` for
vision tasks).

## Provider Switching for the Browser-Finisher

Because `LiteLlm(model=...)` accepts any provider string, switching between
providers is a one-line config change. The `build_openai_litellm_model` helper
would need a minor rename / generalization, but the ADK-LiteLLM wiring is identical.

Candidate model strings for the apply-worker cost target ($0.01–0.10/apply):

| Model | Approx. cost @ 20 turns | Notes |
|---|---|---|
| `openai/gpt-4.1-mini` | ~$0.02–0.05 | Good instruction following |
| `openai/gpt-5-mini` | ~$0.01–0.03 | Cheapest; already in use |
| `anthropic/claude-haiku-4-5` | ~$0.02–0.04 | Strong form-fill reasoning |
| `openai/gpt-4.1` | ~$0.08–0.15 | Exceeds budget at 25 turns |

## Setup

```bash
pip install litellm  # already pinned at litellm==1.82.1 in pyproject.toml
```

`google-adk[extensions]` also pulls in litellm, but the repo already has
`litellm==1.82.1` as a direct dep so no additional installation is needed.
