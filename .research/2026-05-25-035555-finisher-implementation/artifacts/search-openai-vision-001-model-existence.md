# Search 001 — Model existence (gpt-5-mini, gpt-5.4, gpt-5.4-mini, gpt-5.5)

**Date fetched:** 2026-05-25
**Sources:** WebSearch + WebFetch on `developers.openai.com/api/docs/models/*`
**Purpose:** Verify which model IDs exist as of 2026-05-25.

## Headline finding — user claim contradicted by live docs

The parent agent / user prompt states:

> "the real model names are `gpt-5-mini` and `gpt-5.4`. There is no `gpt-5.4-mini`."

**The live OpenAI docs (`developers.openai.com/api/docs/models/*`) show this is incorrect.** As of 2026-05-25, OpenAI publishes a dedicated model page for `gpt-5.4-mini`. The model index page also lists it as a "Frontier" model with text+image input.

Per the user's standing memory rule ("Never dismiss a user's model/API/version claim from training memory alone; web-search first"), the web search has been performed and the evidence is unambiguous: `gpt-5.4-mini` is a real, documented OpenAI production model.

## Confirmed model IDs (2026-05-25)

| Model ID | Page exists? | Text in | Image in | Context | Input $/Mtok | Output $/Mtok | Cached input $/Mtok |
|---|---|---|---|---|---|---|---|
| `gpt-5-mini` | Yes | Yes | **Yes** | 400K | $0.25 | $2.00 | $0.025 |
| `gpt-5.4` | Yes | Yes | **Yes** | 1.05M | $2.50 | $15.00 | $0.25 |
| `gpt-5.4-mini` | **Yes (contra user claim)** | Yes | **Yes** | 400K | $0.75 | $4.50 | $0.075 |
| `gpt-5.5` | Yes | Yes | Yes | 1M | $5.00 | $30.00 | n/a from this page |

Snapshot aliases observed:
- `gpt-5-mini` → `gpt-5-mini-2025-08-07`
- `gpt-5.4` → `gpt-5.4-2026-03-05`
- `gpt-5.4-mini` → `gpt-5.4-mini-2026-03-17`

## WebSearch result lists (verbatim)

### Query 1: `OpenAI gpt-5.4 model release 2026 API vision image input` (domain-filtered to openai.com)
- https://openai.com/index/introducing-gpt-5-4/ — Introducing GPT-5.4
- https://developers.openai.com/cookbook/examples/multimodal/document_and_multimodal_understanding_tips — Cookbook: Getting the Most out of GPT-5.4 for Vision and Document Understanding
- https://openai.com/gpt-5/ — GPT-5 landing
- https://developers.openai.com/api/docs/models/all — All models index
- https://developers.openai.com/api/docs/models/gpt-5.4 — gpt-5.4 page
- https://developers.openai.com/api/docs/models/gpt-5.4-mini — gpt-5.4-mini page (exists)
- https://openai.com/index/introducing-gpt-5-5/ — Introducing GPT-5.5
- https://developers.openai.com/api/docs/guides/images-vision — Images and vision guide
- https://developers.openai.com/api/docs/models/gpt-5.5 — gpt-5.5 page

### Query 2: `OpenAI gpt-5-mini vision image input API 2026` (domain-filtered)
- https://developers.openai.com/api/docs/models — models index
- https://developers.openai.com/api/docs/models/gpt-5-mini — gpt-5-mini page (exists)
- https://developers.openai.com/api/docs/models/gpt-5.4-mini — gpt-5.4-mini page (exists)
- https://developers.openai.com/api/docs/guides/images-vision — vision guide
- https://platform.openai.com/docs/guides/latest-model — latest-model guide
- https://community.openai.com/t/gpt-5-mini-image-input-token-calculation-discrepancy-with-official-faq-formula/1344040 — community thread on image token counting for gpt-5-mini

### Query 3: `"gpt-5.4" OR "gpt-5-mini" vision API image input 2026 pricing` (broad)
- https://pricepertoken.com/pricing-page/model/openai-gpt-5.4-mini — third-party pricing aggregator confirms gpt-5.4-mini exists
- https://openrouter.ai/openai/gpt-5.4-mini — OpenRouter also routes to gpt-5.4-mini
- https://www.glbgpt.com/hub/how-much-is-gpt-5-4-mini-nano/ — blog confirms gpt-5.4-mini and a gpt-5.4-nano variant
- https://pricepertoken.com/pricing-page/model/openai-gpt-5.4 — gpt-5.4 base
- https://pricepertoken.com/pricing-page/model/openai-gpt-5-mini — gpt-5-mini base

## What this means for the project

The parent pass README locks the claim `gpt-5.4-mini does NOT exist`. That lock is wrong. Three independent sources (OpenAI's own model index page, OpenAI's per-model page for `gpt-5.4-mini`, and third-party pricing aggregators like OpenRouter / pricepertoken / glbgpt) all show `gpt-5.4-mini` as a live production model with text+image input, 400K context, $0.75/$4.50 per Mtok.

The earlier research doc `.research/2026-05-23-232801-agent-harness-decision/artifacts/fetch-011-gpt5-mini-toolcalling.md` referencing `gpt-5.4-mini` appears to be correct, not wrong.

I will continue the rest of this research pass assuming all four models exist, and call out the implication for vision-fallback model choice in the recommendation artifact.
