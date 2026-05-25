# Fetch 009 — Latency benchmarks for gpt-5-mini and gpt-5.4-mini

**Sources:**
- https://artificialanalysis.ai/models/gpt-5-4-mini-non-reasoning/providers
- https://artificialanalysis.ai/models/gpt-5-4-mini/providers
- Adam Holter blog (https://adam.holter.com/gpt-5-4-mini-and-nano-benchmarks-pricing-and-what-theyre-actually-good-for/)
- TokenMix/GlobalGPT/302.AI reviews

**Date fetched:** 2026-05-25

## Headline numbers (median, OpenAI as provider, 72-hour rolling window)

| Model | Variant | P50 TTFT | Output speed | Notes |
|---|---|---|---|---|
| `gpt-5.4-mini` | non-reasoning | **0.59 s** | 173.6 t/s | Fast TTFT; ideal for click decisions |
| `gpt-5.4-mini` | reasoning ("xhigh") | **7.16 s** | 175.7 t/s | Reasoning thinking time dominates |
| `gpt-5.4-mini` (general) | — | — | — | "Runs more than 2x faster than gpt-5 mini" (per Adam Holter, 302.AI Medium) |
| OSWorld-Verified (screenshot computer-use bench) | — | — | — | gpt-5.4-mini hits **72.1%**, vs `gpt-5-mini` at **42.0%** (per Adam Holter) |

## Image-input-specific latency

No public benchmark publishes a separate TTFT for image-input requests. Reasonable extrapolation:
- Image tokens (a 1024×1024 PNG ≈ 2,000 image tokens at default detail) add to prompt processing.
- For a single screenshot + small text prompt, expect TTFT ~0.7–1.2 s on `gpt-5.4-mini` non-reasoning, with full response in ~1–2 s for a short tool-call output.
- If reasoning is engaged, expect P50 ~7 s for the first token.

For the finisher fallback, **set `reasoning_effort='low'` or use the non-reasoning variant** to keep TTFT under 1 s. The use-case is "look at one screenshot and emit one tool call" — this does NOT need deep reasoning.

## P95 / tail latency

Artificial Analysis does not publish P95 directly on the model-page UI as of 2026-05; only P50 over a 72-hour rolling window. The blog at digitalapplied.com mentions a Q2 2026 benchmark suite that "captures tail-latency reality" with P50 + P95 but specific gpt-5.4-mini P95 numbers weren't surfaced.

**Practical guidance:** budget P95 at ~3× P50 for production planning. For non-reasoning gpt-5.4-mini that's ~1.8 s TTFT P95, ~3–5 s P95 total-time-to-completion for short outputs.

## OSWorld-Verified — proxy for screenshot reliability

OSWorld-Verified measures a model's ability to complete computer-use tasks via screenshot interpretation. The 72.1% gpt-5.4-mini vs 42.0% gpt-5-mini gap is the strongest single data point for choosing gpt-5.4-mini for the screenshot-fallback turn.

For raw "see a form, emit a click" reliability, gpt-5.4-mini is ~1.7x as reliable as gpt-5-mini.
