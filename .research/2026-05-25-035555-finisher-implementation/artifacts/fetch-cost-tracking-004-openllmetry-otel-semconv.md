# FULL fetch — OpenLLMetry / OTel GenAI semantic conventions

URL: https://www.traceloop.com/docs/openllmetry/contributing/semantic-conventions
Fetched: 2026-05-25
Prompt: list every gen_ai.* attribute related to cost / token usage; instrumentation guidance for cost.

---

## Token & usage attributes (documented)

- `gen_ai.usage.prompt_tokens` — input token count
- `gen_ai.usage.completion_tokens` — completion token count
- `gen_ai.usage.total_tokens` — sum
- `gen_ai.usage.reasoning_tokens` — OpenAI o-series reasoning tokens

## Model / system attributes

- `gen_ai.system` — vendor (`openai`, `anthropic`, `bedrock`, …)
- `gen_ai.request.model` — requested model string
- `gen_ai.response.model` — model actually used (provider may downgrade)

## Cost attribute

**No standard cost attribute exists** in the OpenTelemetry GenAI semconv. The spec stops at tokens. Cost is treated as a downstream / vendor-specific concern.

Quote (paraphrased): *"Many teams extend OpenTelemetry by adding a custom span attribute for cost, calculated from token counts and the model's pricing schema."*

## Instrumentation guidance for cost

Not specified. The vendor consensus is:
- Instrument tokens at the call site (cheap, deterministic, no external lookup).
- Compute cost downstream — either at ingest (Langfuse, Datadog APM) or at query time (Grafana dashboard math) — using a centrally-maintained price map.

This decouples the instrumentation library from the pricing churn.

## 2025 updates

The newer revision consolidated prompt/output text into `gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.system_instructions` (replacing the older experimental `gen_ai.prompt` / `gen_ai.completion` event fields).

---

## Implication for this repo

We don't need to adopt OTel today — but if/when we do, the cost computation does NOT move into the OTel layer. We compute cost ourselves (via litellm) and attach it as a non-spec attribute like `agentic_job_applier.cost.usd` or a `cost_details` dict. The token half is already exactly what we're storing in `metadata_json`.
