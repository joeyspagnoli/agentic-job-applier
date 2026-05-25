# Search results: provider-abstracted cost-tracking landscape

Date: 2026-05-25
Mode: design
Queries:
1. `"litellm completion_cost API model_cost dict per-token pricing centralization 2025"`
2. `"langfuse cost tracking observation usage model price LLM trace 2025"`
3. `"OpenLLMetry Traceloop LLM cost span attributes gen_ai usage tokens semantic conventions"`
4. `"OpenRouter API response usage cost per call generation field 'total_cost' 2025"`
5. `"openai python SDK chat completions stream_options include_usage usage object response 2025"`

## Top sources by relevance

| Source | Type | Date | Relevance | Confidence |
|---|---|---|---|---|
| docs.litellm.ai/docs/completion/token_usage | Official docs | 2025-2026 | `completion_cost()`, `cost_per_token()`, `model_cost` dict | High |
| deepwiki.com/BerriAI/litellm/2.6-cost-calculation-and-model-pricing | Code map | 2025 | Internal call graph `_select_model_name_for_cost_calc` → `get_model_info` | High |
| docs.litellm.ai/docs/proxy/custom_pricing | Official | 2025 | Custom-model pricing registration via env URL or `litellm.register_model()` | High |
| langfuse.com/docs/observability/features/token-and-cost-tracking | Official | 2025 | `usage_details`/`cost_details` dicts on `generation` / `embedding` observations | High |
| langfuse.com/changelog/2025-12-02-model-pricing-tiers | Changelog | 2025-12 | Tiered pricing for context-dependent models (Claude/Gemini long-context) | Med |
| traceloop.com/docs/openllmetry/contributing/semantic-conventions | Spec | 2025 | OTEL `gen_ai.usage.prompt_tokens` / `completion_tokens` / `total_tokens` | High |
| openrouter.ai/docs/api/reference/overview | Official | 2025 | `usage.cost` returned in every completion; `/api/v1/generation?id=…` endpoint for after-the-fact lookups | High |
| github.com/ServiceNow/AgentLab `tracking.py` | Production code | 2025 | Mixin-based provider pricing strategy + thread-local hierarchical tracking | High |
| github.com/lotus-data/lotus `pricing.py` | Production code | 2025 | Single `calculate_cost_from_response(response) -> Optional[float]` that delegates to litellm | Med |
| github.com/AgentOps-AI/agentops | Production SDK (5.5k stars) | 2025 | Session-scoped event model, adapter pattern for new providers | Med |

## Headline findings

- **Centralized pricing tables win.** Every serious OSS project either (a) embeds litellm's `model_prices_and_context_window.json` directly (lotus, easyweb, ExtractThinker, agentops) or (b) ships its own JSON-keyed-by-model price map maintained server-side (langfuse). Per-provider math is only used for *cache-discount adjustments* (AgentLab does this for Anthropic prompt-cache and OpenAI cached input).
- **Persist per LLM call, not per pipeline stage.** Langfuse, AgentOps, OpenLLMetry — all three keep one row per `generation` (one LLM call) and attach a `trace_id` / `session_id` / `run_id` for higher-level aggregation. Per-stage rollups are computed at read time, not at write time.
- **Lock the price at ingestion time** (langfuse: "Inferred cost are calculated at the time of ingestion with the model and price information available at that point in time"). Price changes do not retroactively rewrite history.
- **Providers that return cost natively should be trusted first.** OpenRouter returns `usage.cost` per call; precedence is: provider-reported cost > centrally-computed-from-tokens > stage-rate stub. Langfuse encodes this exact precedence.
- **OTEL `gen_ai.*` semantic conventions** are the emerging standard for *tokens* but **cost is intentionally NOT in the spec** (verified: no `gen_ai.usage.cost` attribute documented). Cost is a custom downstream attribute that vendors compute from tokens + their own price map.
