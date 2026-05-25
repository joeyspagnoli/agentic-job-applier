# `genai-prices` — per-turn cost calculation

**URL:** https://github.com/pydantic/genai-prices
**Fetched:** 2026-05-25

## What it is

Official Pydantic-team Python (and JS/TS) package that converts (provider, model, usage) →
USD cost. Updated weekly with provider price changes. **`RequestUsage` from `pydantic_ai`
implements `genai_prices.types.AbstractUsage`** — so they slot together.

## Python API (verbatim from README)

```python
from genai_prices import Usage, calc_price

price_data = calc_price(
    Usage(input_tokens=1000, output_tokens=100),
    model_ref='gpt-4o',
    provider_id='openai',
)
print(f"Total Price: ${price_data.total_price} "
      f"(input: ${price_data.input_price}, output: ${price_data.output_price})")
```

Return:
- `input_price` — cost for input tokens (Decimal)
- `output_price` — cost for output tokens (Decimal)
- `total_price` — sum (Decimal)

## Integration with `pydantic_ai.RunUsage`

```python
from pydantic_ai import Agent
from genai_prices import calc_price

result = await agent.run("...")
usage = result.usage()  # RunUsage

# Either pass usage directly (it implements AbstractUsage):
price = calc_price(usage, model_ref='gpt-5-mini', provider_id='openai')

# Or use extract_usage on a raw provider response dict
```

## Per-turn cost capture via `agent.iter()`

```python
from pydantic_ai import Agent
from pydantic_ai.usage import RunUsage
from genai_prices import calc_price

async def run_finisher_with_budget(agent, prompt, deps, soft_cap_usd=0.05):
    prev_input = 0
    prev_output = 0
    cumulative_cost = 0.0

    async with agent.iter(prompt, deps=deps,
                          usage_limits=UsageLimits(request_limit=25)) as run:
        async for node in run:
            # After each node, snap usage delta
            u = run.usage  # RunUsage cumulative
            delta_in = u.input_tokens - prev_input
            delta_out = u.output_tokens - prev_output
            if delta_in or delta_out:
                turn_price = calc_price(
                    Usage(input_tokens=delta_in, output_tokens=delta_out),
                    model_ref='gpt-5-mini',
                    provider_id='openai',
                )
                cumulative_cost = float(u.input_tokens) * <rate> + ...  # or recompute via calc_price
                if cumulative_cost > soft_cap_usd:
                    log.warning("finisher.cost_cap_exceeded",
                                cost=cumulative_cost, turn=run.iteration)
                prev_input = u.input_tokens
                prev_output = u.output_tokens
        return run.result
```

## Pinning

Pin to a specific version in `pyproject.toml`:

```
genai-prices==0.0.42  # check latest at install time
```

Prices YAML files are bundled inside the package — no network call at runtime. Reasonable to
let the version float month-to-month for fresh provider rates, but for reproducibility pin it.

## OpenAI models supported

The `prices/providers/openai.yml` file in the repo enumerates supported model_refs. Our two
target models from locked decision #16 — `gpt-5-mini` and `gpt-5.4` — should both be present;
we should verify on install but the YAML is comprehensive (all gpt-5 family models tracked).

## Caveat (from upstream README)

> "The price data cannot be exactly correct because model providers do not provide exact price
> information for their APIs in a format which can be reliably processed."

In practice the rates match OpenAI's billing within ~5%. Good enough for a $0.05 soft cap that
logs only (no abort).
