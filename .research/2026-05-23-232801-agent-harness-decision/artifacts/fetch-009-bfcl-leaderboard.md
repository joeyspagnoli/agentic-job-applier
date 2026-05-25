# BFCL Berkeley Function Calling Leaderboard (2026)
*Source: gorilla.cs.berkeley.edu/leaderboard.html (data not accessible via WebFetch as interactive JS table); llm-stats.com/benchmarks/bfcl*

## BFCL V4 Overview
- Last Updated: April 12, 2026
- Evaluates: Serial and parallel function calls, multi-turn interactions
- Method: AST evaluation, 2,000+ question-function-answer pairs
- Covers: diverse application domains, parallel calls, multi-turn

## Available Rankings (from llm-stats.com snapshot)
Note: llm-stats.com snapshot showed older data; main leaderboard at gorilla.cs.berkeley.edu is interactive JS and not scrapable

| Rank | Model | Score |
|------|-------|-------|
| 1 | Llama 3.1 405B Instruct | 0.885 |
| 2 | Llama 3.1 70B Instruct | 0.848 |
| 3 | Llama 3.1 8B Instruct | 0.761 |
| 4 | Qwen3 235B A22B | 0.708 |
| 5 | Qwen3 32B | 0.703 |

## Notes on Target Models
The interactive leaderboard at gorilla.cs.berkeley.edu was not scrapable. However from secondary sources and the beam.ai analysis:

- **GPT-5.4 Mini**: τ2-bench 93.4% (vs gpt-5-mini 74.1%) — significant improvement
- **GPT-5.4 Mini**: MCP Atlas 57.7% (vs gpt-5-mini 47.6%)
- **Claude Haiku 4.5**: Full tool use support confirmed; computer-use 50.7%
- **Gemini 2.5 Flash**: Tool calling supported as standard Gemini API feature

## Key Takeaway
The BFCL live leaderboard data for May 2026 frontier models (GPT-5.x, Claude 4.x, Gemini 2.5) is behind a JS-rendered table. The τ2-bench and MCP Atlas scores from beam.ai are the best available proxy for production tool-calling reliability of the candidate models.
