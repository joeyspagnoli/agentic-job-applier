# FULL fetch — LiteLLM completion_cost / model_cost / cost_per_token

URL: https://docs.litellm.ai/docs/completion/token_usage
Fetched: 2026-05-25
Prompt: API surface for completion_cost, cost_per_token, model_cost; pricing JSON location; cost-from-response example.

---

## 1. `completion_cost()`

**Input options:**
- A `litellm.completion()` response object via `completion_response` parameter.
- OR `model`, `prompt`, `completion` string parameters.

**Returns:** `float` (USD cost).

```python
from litellm import completion_cost

# Option A: pass response object
response = completion(model="bedrock/anthropic.claude-v2", messages=messages)
cost = completion_cost(completion_response=response)

# Option B: pass strings directly
cost = completion_cost(
    model="bedrock/anthropic.claude-v2",
    prompt="Hey!",
    completion="How's it going?"
)
```

## 2. `cost_per_token()`

**Input:** model name, prompt-token count, completion-token count.

**Returns:** `(prompt_cost_usd: float, completion_cost_usd: float)`.

```python
from litellm import cost_per_token

prompt_tokens = 5
completion_tokens = 10
prompt_cost, completion_cost = cost_per_token(
    model="gpt-3.5-turbo",
    prompt_tokens=prompt_tokens,
    completion_tokens=completion_tokens,
)
```

## 3. `model_cost` dict schema

```python
{
    "gpt-3.5-turbo": {
        "max_tokens": 4000,
        "input_cost_per_token": 1.5e-06,
        "output_cost_per_token": 2e-06,
    },
    # … one entry per supported model
}
```

Keys: `max_tokens`, `input_cost_per_token`, `output_cost_per_token`. The community list also includes per-provider variants (e.g. `bedrock/anthropic.claude-v2`, `openai/gpt-5-mini`).

## 4. Pricing JSON location

- Source URL: `https://api.litellm.ai`
- GitHub canonical: `https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.json`
- Override env: `LITELLM_MODEL_COST_MAP_URL=<url>`
- Force local-only (no network): `export LITELLM_LOCAL_MODEL_COST_MAP="True"`

## 5. Cost on the response object

After `litellm.completion(...)`, the cost is attached to the response via:

```python
cost = response._hidden_params["response_cost"]
```

LiteLLM also supports a `completion_cost(...)` call against a non-litellm response (e.g. raw OpenAI response) if you pass `model=` explicitly.

---

## Internal call graph (from DeepWiki source map)

`completion_cost()` → `_select_model_name_for_cost_calc()` → `get_model_info()` → token extraction from `response.usage` → per-component cost (cached, reasoning, standard) → returns `(total_cost, cost_currency)`.

## Custom pricing override

Two methods:
1. Mutate `litellm.model_cost` directly (the proxy uses `_invalidate_model_cost_lowercase_map()` after writes).
2. Point `LITELLM_MODEL_COST_MAP_URL` to a hosted JSON blob; LiteLLM validates against the bundled backup file before swapping.

## Unknown-model behavior

`get_model_info()` raises `litellm.exceptions.NotFoundError` when the model is not in the table. The `lotus/pricing.py` pattern catches this and returns `None`; the `litellm.completion()` integrated path attaches `response_cost=None`. The caller decides whether to fall through to a default rate.

---

## Why this matters for this repo

We already have `litellm==1.82.1` pinned in `pyproject.toml:21`. The pricing table for every OpenAI model (including `gpt-5-mini`, `gpt-5.4`, `gpt-5.4-mini`) ships in that package. Calling `litellm.completion_cost(...)` with `(model, prompt_tokens, completion_tokens)` would eliminate the entire `COST_RATE_<MODEL>_IN_USD` / `_OUT_USD` env-var protocol we currently rely on (and which is unset everywhere).
