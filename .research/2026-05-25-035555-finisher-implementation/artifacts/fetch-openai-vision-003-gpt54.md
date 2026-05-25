# Fetch 003 — gpt-5.4 model page

**URL:** https://developers.openai.com/api/docs/models/gpt-5.4
**Date fetched:** 2026-05-25

## Full extracted content

**Model ID:** `gpt-5.4`
**Snapshot alias:** `gpt-5.4-2026-03-05`
**Knowledge cutoff:** August 31, 2025
**Release window:** Announced March 5, 2026 (per `openai.com/index/introducing-gpt-5-4/`)
**Tagline:** "Our frontier model for complex professional work"

### Modalities
- Input: Text and image
- Output: Text only
- Audio and video: NOT supported

### Context / output
- 1,050,000 context window (1.05M)
- 128,000 max output tokens
- Reasoning level: "Highest"

### Pricing (per 1M tokens)
| Direction | Price |
|---|---|
| Input | $2.50 |
| Cached input | $0.25 |
| Output | $15.00 |

**Long-context surcharge:** "For models with a 1.05M context window (GPT-5.4 and GPT-5.4 pro), prompts with >272K input tokens are priced at 2x input and 1.5x output."

### Capabilities
- **Vision (image input)** — yes
- **Function calling** — yes ("Function calling is supported")
- Works with web search, file search, image generation, code interpreter, hosted shell via Responses API
- Reasoning: highest

### Notes
"The model emphasizes reasoning capabilities (Highest reasoning level) with medium speed performance."

## Implications for vision fallback

`gpt-5.4` is vision-capable and tool-call capable, but at $2.50 input it is **10x more expensive than gpt-5-mini ($0.25)** and **3.3x more expensive than gpt-5.4-mini ($0.75)** for the same vision capability. For a JD form-filler fallback where the model just needs to read a screenshot and emit a click/type tool call, the smaller variants are far more cost-appropriate.

`gpt-5.4` is overkill for finisher fallback — it's the model you'd use when reasoning quality matters more than cost. Reserve for hard cases / human-review escalation, not for every screenshot fallback fire.
