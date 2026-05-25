# Fetch 001 — OpenAI Models index page

**URL:** https://developers.openai.com/api/docs/models
**Date fetched:** 2026-05-25
**Extraction prompt:** "List ALL OpenAI model IDs available as of 2026-05-25..."

## Full extracted content

### Production "Frontier" models confirmed on the index page

**gpt-5.5** — exists
- Model ID: `gpt-5.5`
- Context: 1M tokens
- Modalities: Text and image input, text output
- Input: $5/MTok | Output: $30/MTok

**gpt-5.4** — exists
- Model ID: `gpt-5.4`
- Context: 1M tokens
- Modalities: Text and image input, text output
- Input: $2.50/MTok | Output: $15/MTok

**gpt-5.4-mini** — exists
- Model ID: `gpt-5.4-mini`
- Context: 400K tokens
- Modalities: Text and image input, text output
- Input: $0.75/MTok | Output: $4.50/MTok

**gpt-5-mini** — NOT listed on the current "Frontier" section of the models index page (but the dedicated page `developers.openai.com/api/docs/models/gpt-5-mini` does still exist — see fetch 002). This suggests it's been demoted from "frontier" but is still callable.

### Additional models listed
- gpt-4o-mini-tts
- gpt-realtime-2, gpt-realtime-1.5, gpt-realtime-mini, gpt-realtime-translate, gpt-realtime-whisper
- gpt-4o-transcribe, gpt-4o-mini-transcribe
- gpt-image-2

### Verbatim guidance from the page
> "Start with gpt-5.5 for complex reasoning and coding, or choose gpt-5.4-mini and gpt-5.4-nano for lower-latency, lower-cost workloads."

## Interpretation

OpenAI's recommended ladder in 2026-05 is **gpt-5.5 → gpt-5.4-mini → gpt-5.4-nano** for cost/latency tradeoffs. The base `gpt-5-mini` (released 2025-08) is still callable but has been superseded by `gpt-5.4-mini` for new workloads — confirmed by the per-model page for `gpt-5.4-mini` which says "designed for high-volume workloads."
