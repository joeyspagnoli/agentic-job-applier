# FULL fetch — ServiceNow AgentLab `src/agentlab/llm/tracking.py`

URL: https://raw.githubusercontent.com/ServiceNow/AgentLab/main/src/agentlab/llm/tracking.py
Fetched: 2026-05-25
Prompt: cost-tracking interface, computation mechanism, run-correlation, persistence model.

---

## Provider abstraction style: **mixin + strategy map**

```python
class TrackAPIPricingMixin:
    """Mixin class to handle pricing information for different models."""
```

Mixed into provider classes. Pricing is dispatched via a function map (no OOP polymorphism):

```python
pricing_fn_map = {
    "openai":     get_pricing_openai,
    "anthropic":  get_pricing_anthropic,
    "openrouter": get_pricing_openrouter,
    "litellm":    partial(get_pricing_litellm, self.model_name),
}
```

Each `get_pricing_<provider>` returns the per-model price table for that vendor.

## Generic cost formula

```python
cost = input_tokens * self.input_cost + output_tokens * self.output_cost
```

(`self.input_cost` and `self.output_cost` resolved once per provider/model via the mixin.)

## Provider-specific overrides (for cache discounts)

- `get_effective_cost_from_anthropic_api()` — splits prompt tokens by cache-read vs cache-write status:
  ```python
  ANTHROPIC_CACHE_PRICING_FACTOR = {
      "cache_read_tokens":  0.1,
      "cache_write_tokens": 1.25,
  }
  ```
- `get_effective_cost_from_openai_api()` — discounts cached input tokens.

## Run correlation: thread-local context

```python
TRACKER = threading.local()

@contextmanager
def set_tracker(suffix=""):
    previous_tracker = TRACKER.instance
    TRACKER.instance = LLMTracker(suffix)
    try:
        yield TRACKER.instance
    finally:
        if isinstance(previous_tracker, LLMTracker):
            previous_tracker.add_tracker(TRACKER.instance)
```

`set_tracker(suffix="tailor")` is wrapped around a pipeline phase; the suffix becomes part of the cost row's `phase` label. Parent trackers absorb child trackers' totals on exit (hierarchical aggregation in memory).

The `cost_tracker_decorator` writes into the calling agent's `agent_info` dict:
```python
agent_info.get("stats").update(tracker.stats)
```

## Persistence

In-memory only. The library does not ship a DB writer; the calling research-experiment code is responsible for serializing `Stats` to disk.

```python
@dataclass
class Stats:
    stats_dict: dict = field(default_factory=lambda: defaultdict(float))
    
    def increment_stats_dict(self, stats_dict: dict):
        ...
```

## Lessons for this repo

1. **Mixin/strategy map is the lightweight alternative to formal `Protocol` classes** — but a `Protocol` is a small upgrade for type-checker friendliness and is what we already have in `src/providers/types.py:107` (`AIProvider`). Stick with what we have.
2. **Cache-discount logic lives next to the provider, not in the central cost helper.** Anthropic prompt-caching and OpenAI cached-input both need this when we add Anthropic later. Don't bake the simple `prompt × rate + completion × rate` formula into the central layer — let providers override.
3. **Thread-local hierarchical trackers are overkill for our async/Python pipeline.** We have explicit `tailor_run_id` / `apply_run_id` in scope; pass them as call args. Skip the magic context-manager.
