# Fetch 008 — Pydantic AI OpenAI provider classes

**URL:** https://pydantic.dev/docs/ai/models/openai/ (redirected from https://ai.pydantic.dev/models/openai/)
**Date fetched:** 2026-05-25

## OpenAI wrapper classes (current as of 2026-05)

| Class | API used | Notes |
|---|---|---|
| `OpenAIChatModel` | Chat Completions | Stable, backward-compatible. Settings via `OpenAIChatModelSettings`. |
| `OpenAIResponsesModel` | **Responses API** (current preferred) | In Pydantic AI v2, `'openai:'` string prefix resolves to this by default. |

Verbatim:
> "In Pydantic AI v2, the bare `'openai:'` prefix will resolve to `OpenAIResponsesModel` instead of `OpenAIChatModel`."

This matters: passing `model='openai:gpt-5.4-mini'` on Pydantic AI v2 gives you the Responses-API path, which is also the path OpenAI's own docs say to use for new code. Use the explicit class names if you need to pin behavior.

## Code example — Agent + tool + image

Adapted from the docs and confirmed by real-world repos:

```python
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.models.openai import OpenAIChatModel  # or OpenAIResponsesModel

model = OpenAIChatModel('gpt-5.4-mini')
agent = Agent(model)

@agent.tool
def analyze_image(description: str) -> str:
    """Process image analysis requests."""
    return f"Analyzed: {description}"

result = agent.run_sync([
    'Describe this image',
    BinaryContent(data=image_bytes, media_type='image/png'),
])
```

## Model settings (where to put `detail="original"`, service_tier, etc.)

```python
from pydantic_ai.models.openai import OpenAIChatModelSettings

settings = OpenAIChatModelSettings(temperature=0.2, service_tier='flex')
agent = Agent(model, model_settings=settings)
```

The docs do NOT explicitly expose a per-image `detail` parameter on `BinaryContent` itself. Two options for setting `detail="original"`:
1. Use `OpenAIResponsesModel` and pass detail via a custom extra-body or settings hook — needs verification by reading the source.
2. Drop down to the raw OpenAI client for the vision turn and skip Pydantic AI on that turn.

This is an open implementation question to validate against `pydantic-ai/pydantic_ai_slim/pydantic_ai/models/openai.py` when implementing.

## Implication for the finisher

- Use `model='openai:gpt-5.4-mini'` as the model string. On v2 this gives you Responses API.
- The same Agent can carry `@agent.tool` browser-action tools AND `BinaryContent` screenshot messages on the same turn — confirmed by `gh-openai-vision-001-real-pydantic-ai-image-tool-repos.md`.
- For dense small-button localization, may need to drop to raw OpenAI client for the vision-fallback turn so we can set `detail="original"`. Alternative: scale screenshots to 1024px on the long side so default detail works fine.
