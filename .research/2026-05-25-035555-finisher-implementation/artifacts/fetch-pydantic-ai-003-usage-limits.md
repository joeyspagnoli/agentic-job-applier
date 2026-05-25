# Pydantic AI — UsageLimits and RunUsage

**URL:** https://pydantic.dev/docs/ai/api/pydantic-ai/usage/ (redirected from https://ai.pydantic.dev/api/usage/)
**Fetched:** 2026-05-25
**Prompt:** Extract full UsageLimits and RunUsage class signatures + cost calculation.

## RunUsage (verbatim)

```python
class RunUsage(UsageBase):
    requests: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    input_audio_tokens: int = 0
    cache_audio_read_tokens: int = 0
    output_tokens: int = 0
    details: dict[str, int] = dataclasses.field(default_factory=dict)
```

## UsageLimits (verbatim)

```python
class UsageLimits:
    request_limit: int | None
    tool_calls_limit: int | None
    input_tokens_limit: int | None
    output_tokens_limit: int | None
    total_tokens_limit: int | None
    count_tokens_before_request: bool
```

### Parameter docs (verbatim from API page)

- **`request_limit`** — "The maximum number of requests allowed to the model"
- **`tool_calls_limit`** — "The maximum number of successful tool calls allowed"
- **`input_tokens_limit`** — "The maximum number of input/prompt tokens allowed"
- **`output_tokens_limit`** — "The maximum number of output/response tokens allowed"
- **`total_tokens_limit`** — "The maximum number of tokens allowed in requests and responses combined"

## Per-call cost capture

`RequestUsage` implements `genai_prices.types.AbstractUsage`. The official `genai-prices` library
(https://github.com/pydantic/genai-prices) converts token counts into USD per model.

The API page does NOT supply a built-in dollar accumulator. The two practical patterns are:

1. **Final-cost pattern:** after `result = await agent.run(...)`, call `result.usage()` and feed into
   `genai_prices`.
2. **Per-iteration pattern:** use `agent.iter(...)` (async iterator over agent nodes). Each
   `ModelRequestNode` / `CallToolsNode` exposes a `request_usage` you can subtract from the prior
   cumulative usage to get per-step token delta, then price it.

`UsageLimits` itself does NOT carry a dollar limit — it's tokens / requests / tool-calls only.
A dollar soft cap must be checked between iterations in user code.
