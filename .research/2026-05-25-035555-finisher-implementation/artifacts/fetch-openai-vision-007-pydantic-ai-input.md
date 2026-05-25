# Fetch 007 — Pydantic AI image/multimodal input docs

**URL:** https://pydantic.dev/docs/ai/advanced-features/input/ (redirected from https://ai.pydantic.dev/input/)
**Date fetched:** 2026-05-25

## Image content types (Pydantic AI)

Pydantic AI ships two content types for image input on agent runs:

1. **`ImageUrl`** — for remote URLs the model can fetch
2. **`BinaryContent`** — for local/binary image bytes with a `media_type`

The full `MultiModalContent` union: `ImageUrl | AudioUrl | DocumentUrl | VideoUrl | BinaryContent | UploadedFile`.

## Example — URL-based image

```python
from pydantic_ai import Agent, ImageUrl

agent = Agent(model='openai:gpt-5.2')
result = agent.run_sync([
    'What company is this logo from?',
    ImageUrl(url='https://iili.io/3Hs4FMg.png'),
])
```

## Example — local-file BinaryContent

```python
from pydantic_ai import Agent, BinaryContent
import httpx

image_response = httpx.get('https://example.com/image.png')
agent = Agent(model='openai:gpt-5.2')
result = agent.run_sync([
    'What company is this logo from?',
    BinaryContent(data=image_response.content, media_type='image/png'),
])
```

`BinaryContent(data=Path('screenshot.png').read_bytes(), media_type='image/png')` is the standard pattern for screenshots.

## Tool calling on the same turn — documented status

The official input/ page does NOT explicitly state that images can ride alongside `@agent.tool` calls on the same turn. However, the OpenAI underlying API absolutely supports this (confirmed in cookbook fetch-006), and real-world Pydantic AI code does combine both — see `gh-openai-vision-001-real-pydantic-ai-image-tool-repos.md` for live repos doing exactly this.
