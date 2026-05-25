# FULL fetch — Langfuse token & cost data model

URL: https://langfuse.com/docs/observability/features/token-and-cost-tracking
Fetched: 2026-05-25
Prompt: granularity (per-call/per-trace), field names, ingestion architecture, price drift handling, model entity schema.

---

## Granularity: per-observation

Cost is tracked on observations of type **`generation`** and **`embedding`**. Each LLM call is one observation. Observations belong to a `trace`; multiple traces can share a `session_id`. Cost is computed and stored at the leaf (generation) level; rollups are queries.

## Persisted fields

- `usage_details`: `dict[str, int]` — usage-type → unit count. Examples:
  - `input`, `output`, `cache_read_input_tokens`, `cache_write_input_tokens`, `audio_tokens`, `image_tokens`.
  - OpenAI's `prompt_tokens` is normalized to `input`; `completion_tokens` → `output`.
- `cost_details`: `dict[str, float]` — usage-type → USD cost.
- `model`: string; resolved at ingestion to a Model entity for pricing lookup.

## Ingestion architecture

Two sources, plus inference:

1. **Provider-supplied cost passthrough.** "Some model providers return the cost and tokens as part of the response payload which you can pass back to Langfuse." (e.g. OpenRouter)
2. **Explicit ingestion.** SDK callers send `usage_details` and/or `cost_details` directly via `generation.update(...)`.
3. **Server-side inference.** If usage_details or cost_details are missing, Langfuse infers from the `model` field at the time of ingestion.

## Price-drift handling

Quote (verbatim): *"Inferred cost are calculated at the time of ingestion with the model and price information available at that point in time. If model definitions change, the updated costs will only be applied to new generations logged to Langfuse."*

→ **Lock-at-write semantics.** Old rows keep old prices forever.

## Model entity / regex matcher

```json
{
  "match_pattern": "(?i)^(gpt-4-0125-preview)$",
  "tokenizerModel": "gpt-3.5-turbo",
  "tokensPerName": -1,
  "tokensPerMessage": 4
}
```

Pricing tiers (added 2025-12) allow context-dependent prices:

```json
{
  "usageDetailPattern": "input",
  "operator": ">=",
  "value": 200000,
  "caseSensitive": false,
  "price": 0.000015
}
```

This is how Claude Sonnet 4.5 and Gemini 2.5 / 3 Pro Preview get their "long-context surcharge" tiers represented.

## Correlation to higher-level runs

- `trace_id` — one trace = one logical user/job action. Set via `langfuse.trace(...)` or via the wrapping decorator.
- `session_id` — string supplied by caller, links N traces.
- `parent_observation_id` — for nested spans inside a trace.

The dashboard/aggregations query `cost_details` SUM grouped by `trace_id`, `session_id`, `model`, `user_id`, etc.

---

## Mapping to this repo's vocabulary

| Langfuse concept | Our analogue |
|---|---|
| `generation` observation | one row per individual LLM call (currently we collapse this into one `cost_events` row per *stage*) |
| `trace_id` | `tailor_run_id` / `apply_run_id` / `gate_run_id` / `review_run_id` |
| `session_id` | `job_hash` |
| `usage_details` dict | currently flattened into `metadata_json` |
| `cost_details` dict | currently a single `cost_usd` column |
| Model entity table | currently the loose `COST_RATE_<MODEL>_*` env-var convention |
