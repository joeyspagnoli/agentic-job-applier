# gh search — production repos using LLM cost tracking

Date: 2026-05-25
Queries:
- `gh search repos "llm cost tracking" --language=python --sort=stars`
- `gh search code "from litellm import completion_cost"`

---

## Repos found (sorted by stars)

| Repo | Stars | Description | Approach |
|---|---|---|---|
| [AgentOps-AI/agentops](https://github.com/AgentOps-AI/agentops) | 5,576 | Multi-framework agent monitoring SDK | Session-scoped events; adapter per framework (CrewAI/AG2/OpenAI/Anthropic/Langchain). Costs computed via integration callbacks. |
| [he-yufeng/TokenTracker](https://github.com/he-yufeng/TokenTracker) | 38 | "Drop-in LLM cost tracker" | Monkey-patches the OpenAI client; computes cost from token table at log time |
| [AbYousef739/clawcache-free](https://github.com/AbYousef739/clawcache-free) | 19 | Local cost tracker + cache | Token-counter + per-model price JSON |
| [shivamshinde123/LLM-Cost-Tracking-Using-Helicone-or-LiteLLM](https://github.com/shivamshinde123/LLM-Cost-Tracking-Using-Helicone-or-LiteLLM) | 0 | Reference repo | Demonstrates LiteLLM + Helicone, with explicit "use `completion_cost`" pattern |

## Code-search hits for `from litellm import completion_cost`

| Repo | Path | Note |
|---|---|---|
| [BerriAI/litellm](https://github.com/BerriAI/litellm) | `litellm/proxy/spend_tracking/spend_management_endpoints.py` | The reference impl — proxy server's spend endpoints |
| [camel-ai/camel](https://github.com/camel-ai/camel) | `camel/utils/token_counting.py` | Inside their utils — LiteLLM is the cost oracle |
| [huggingface/ml-intern](https://github.com/huggingface/ml-intern) | `agent/core/telemetry.py` | Cost emitted from a `telemetry.py` shim, mirroring the pattern we want |
| [enoch3712/ExtractThinker](https://github.com/enoch3712/ExtractThinker) | `extract_thinker/eval/evaluator.py` | Eval harness calling LiteLLM cost per response |
| [lotus-data/lotus](https://github.com/lotus-data/lotus) | `lotus/pricing.py` | One-liner wrapper around `completion_cost` |
| [aws-solutions-library-samples/guidance-for-multi-provider-generative-ai-gateway-on-aws](https://github.com/aws-solutions-library-samples/guidance-for-multi-provider-generative-ai-gateway-on-aws) | `scripts/benchmark.py` | AWS gateway sample uses LiteLLM for cost |
| [maitrix-org/easyweb](https://github.com/maitrix-org/easyweb) | `easyweb/llm/llm.py` | Browser-agent (closest to our domain) uses LiteLLM cost |
| [ServiceNow/AgentLab](https://github.com/ServiceNow/AgentLab) | `src/agentlab/llm/tracking.py` | Mixin-based provider pricing with cache-discount overrides |

## Pattern frequency

- **Delegate to `litellm.completion_cost(...)`**: 6 of 8 repos.
- **Hand-rolled per-provider table**: 1 (AgentLab — the most sophisticated, handles cache discounts).
- **Provider-returned cost passthrough**: 1 (OpenRouter consumers use `usage.cost` directly).

## Verdict for our codebase

LiteLLM `completion_cost(...)` is the de-facto industry default for multi-provider cost computation in Python. We already have `litellm==1.82.1` pinned. Use it.

Reserve hand-rolled per-provider math for *only* the cache-discount edge cases (Anthropic prompt cache, OpenAI cached-input) — and put that math in the provider adapter, not in the central layer.
