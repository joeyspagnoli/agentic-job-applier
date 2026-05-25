# OpenAI API Pricing (May 2026)
*Source: openai.com/api/pricing/ returned HTTP 403; supplemented via WebSearch and pricepertoken.com*

## GPT-5 Family (released Aug 7, 2025)

| Model | Input $/MTok | Output $/MTok | Cached Input $/MTok | Context Window |
|-------|-------------|--------------|--------------------|--------------------|
| gpt-5-nano | $0.050 | $0.400 | $0.005 | 400k tokens |
| gpt-5-mini | $0.250 | $2.00 | $0.025 | 400k tokens |

## GPT-5.4 Family (released Mar 5–17, 2026)

| Model | Input $/MTok | Output $/MTok | Context Window |
|-------|-------------|--------------|----------------|
| gpt-5.4-nano | $0.20 | $1.25 | Not confirmed |
| gpt-5.4-mini | $0.75 | $4.50 | Not confirmed |

## Notes
- The repo currently uses `openai/gpt-5-mini` (Aug 2025 release, $0.25/$2.00)
- The newer gpt-5.4-mini ($0.75/$4.50) has significantly higher τ2-bench scores (93.4% vs 74.1% for gpt-5-mini)
- All GPT-5 family models support vision, tool calling, reasoning, and caching
- openai.com/api/pricing returned HTTP 403; prices confirmed via secondary sources
