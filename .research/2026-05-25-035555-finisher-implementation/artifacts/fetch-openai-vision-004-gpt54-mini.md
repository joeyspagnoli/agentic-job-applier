# Fetch 004 — gpt-5.4-mini model page

**URL:** https://developers.openai.com/api/docs/models/gpt-5.4-mini
**Date fetched:** 2026-05-25
**Note:** This page exists, contradicting the parent-prompt claim that "There is no `gpt-5.4-mini`."

## Full extracted content

**Model ID:** `gpt-5.4-mini`
**Snapshot variant:** `gpt-5.4-mini-2026-03-17`
**Knowledge cutoff:** August 31, 2025
**Tagline:** "Our strongest mini model yet for coding, computer use, and subagents"
**Positioning:** "Brings the strengths of GPT-5.4 to a faster, more efficient model designed for high-volume workloads."

### Modalities
- Text: Input and output
- **Image: Input only** (vision-capable)
- Audio and Video: NOT supported

### Context / output
- 400,000 context window
- 128,000 max output tokens

### Pricing (per 1M tokens)
| Direction | Price |
|---|---|
| Input | $0.75 |
| Cached input | $0.075 |
| Output | $4.50 |

### Deprecation
None indicated.

## Implications for vision fallback

`gpt-5.4-mini` is the **sweet spot** for the finisher's vision fallback:
- Vision: yes
- Tool calling: yes (inherited from GPT-5.4 family; "subagents" use-case implies function calling)
- Computer use: explicitly mentioned in tagline as a target use-case
- 400K context — plenty for AX-tree + screenshot + form schema
- $0.75 input vs $0.25 for gpt-5-mini — 3x more expensive but per the earlier research (fetch-011-gpt5-mini-toolcalling.md): τ2-bench jumps 74.1% → 93.4% (a +19.3 point reliability gain) and MCP Atlas 47.6% → 57.7% (+10.1).

Per the parent's locked decision #11 ("Vision fallback = build in v1, screenshot → same OpenAI model"), it makes sense to use `gpt-5.4-mini` as the **single** model for both AX-tree and screenshot turns rather than maintain two model paths.
