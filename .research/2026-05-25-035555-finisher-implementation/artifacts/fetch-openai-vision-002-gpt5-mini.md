# Fetch 002 — gpt-5-mini model page

**URL:** https://developers.openai.com/api/docs/models/gpt-5-mini
**Date fetched:** 2026-05-25

## Full extracted content

**Model ID:** `gpt-5-mini`
**Latest snapshot:** `gpt-5-mini-2025-08-07`
**Release / knowledge cutoff:** May 31, 2024

**Tagline:** "Near-frontier intelligence for cost sensitive, low latency, high volume workloads."

### Modalities
- Text: Input and output supported
- **Image: Input ONLY supported** (vision-capable)
- Audio & Video: Not supported

### Context / output
- 400,000 token context window
- 128,000 maximum output tokens
- Reasoning token support enabled

### Pricing (per 1M tokens)
| Direction | Price |
|---|---|
| Input | $0.25 |
| Cached input | $0.025 |
| Output | $2.00 |

### Capabilities
- Streaming
- **Function calling** (tool use)
- Structured outputs
- **Vision** (image input)
- Tools: web search, file search, code interpreter, MCP
- Fine-tuning: not supported
- Computer use: not supported

### Rate limits (Tier 1)
- 500 requests/minute
- 500,000 tokens/minute

## Implications for vision fallback

- `gpt-5-mini` IS vision-capable.
- `gpt-5-mini` IS tool-call capable.
- Cheapest of the vision-capable mainline models ($0.25 input).
- "Computer use" capability is marked NOT supported — this is a distinct capability separate from raw image input. For a screenshot-based finisher that returns tool calls (not literal computer-use actions), this restriction does not apply; the model can still see an image and call functions.
