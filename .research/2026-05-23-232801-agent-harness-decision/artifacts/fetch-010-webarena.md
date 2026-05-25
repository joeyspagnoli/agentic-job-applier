# WebArena / Browser Agent Benchmarks (2026)
*Source: awesomeagents.ai/leaderboards/web-agent-benchmarks-leaderboard/ (April 2026)*

## WebArena Leaderboard — Raw Models (April 2026)

| Rank | Model | Provider | Score |
|------|-------|----------|-------|
| 1 | Claude Mythos Preview | Anthropic | 68.7% |
| 2 | GPT-5.4 Pro | OpenAI | 65.8% |
| 3 | Claude Opus 4.6 | Anthropic | 64.5% |
| 4 | GPT-5.4 | OpenAI | 62.3% |
| 5 | Claude Sonnet 4.6 | Anthropic | 59.2% |
| 6 | Gemini 3.1 Pro | Google | 58.4% |
| 7 | Qwen3.6 Plus | Alibaba | 57.2% |
| 8 | Qwen3.5 397B | Alibaba | 55.8% |
| 9 | Grok 4.1 | xAI | 53.7% |
| 10 | Gemini 3 Pro | Google | 52.1% |

## Notes
- Human baseline: ~78%
- Specialized agentic frameworks significantly outperform raw model calls:
  - OpAgent (CodeFuse AI): 71.6% (Planner-Grounder-Reflector-Summarizer + RL)
  - DeepSeek V3.2 as agent backbone: 74.3% (Steel.dev; end-to-end agent systems)
- Claude Haiku 4.5, gpt-5-mini, gemini-2.5-flash not in top 10 raw model rankings

## WebVoyager (Commercial Agent Systems)
- Alumnium: 98.5%
- Surfer 2: 97.1%
- Browser Use framework: 89.1%
- OpenAI Operator: 87%

## BrowseComp (Hardest Benchmark)
- Claude Mythos Preview: 0.869
- Gemini 3.1 Pro: 0.859
- Claude Opus 4.6: 0.840
- GPT-5.4: 0.827

## Key Insight
The browser-fill use case (form filling with AX-tree snapshots) differs from WebArena's multi-step research/navigation tasks. The critical capability for this repo is tool-calling reliability (well-formed JSON), not high-level web reasoning. Smaller/cheaper models can excel at the executor role even if they don't top WebArena.
