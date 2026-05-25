# FULL fetch — OpenRouter usage / cost in API response

URL: https://openrouter.ai/docs/api/reference/overview
Fetched: 2026-05-25
Prompt: shape of `usage`, whether `cost` is default, the `/api/v1/generation` lookup endpoint, `stream_options`.

---

## ResponseUsage TypeScript shape (verbatim)

```typescript
type ResponseUsage = {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  prompt_tokens_details?: {
    cached_tokens: number;
    cache_write_tokens?: number;
    audio_tokens?: number;
    video_tokens?: number;
  };
  completion_tokens_details?: {
    reasoning_tokens?: number;
    audio_tokens?: number;
    image_tokens?: number;
  };
  cost?: number;
  is_byok?: boolean;
  cost_details?: {
    upstream_inference_cost?: number;
    upstream_inference_prompt_cost: number;
    upstream_inference_completions_cost: number;
  };
  server_tool_use?: {
    web_search_requests?: number;
  };
};
```

Field of interest: **`usage.cost`** (singular `cost`, not `total_cost`). Returned in USD. Granularity is the single completion call.

## When is usage returned?

- Non-streaming: **always** present in the response.
- Streaming: returned **exactly once in the final chunk** before the `[DONE]` sentinel, with `choices = []`.
- No special header or parameter required. (OpenAI's native chat-completions endpoint, by contrast, requires `stream_options: {"include_usage": true}` for streaming usage to be returned.)

## Post-hoc lookup endpoint

`GET /api/v1/generation?id=$GENERATION_ID` — returns token counts and cost for a completed generation. Useful when the original request didn't capture `usage` (e.g. interrupted stream).

## Implication for our provider abstraction

If we add an OpenRouter provider to the abstraction, its `CompletionResponse` builder should:
1. Read `response.usage.cost` if present → emit as the authoritative `cost_usd`.
2. Read `response.usage.prompt_tokens` / `completion_tokens` regardless.
3. Set a `cost_source` flag (`"provider"` vs `"computed"`) so downstream readers know which fidelity they have.

This mirrors Langfuse's precedence model: provider-reported wins over centrally-computed-from-tokens.
