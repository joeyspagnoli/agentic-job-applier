# Claude Haiku 4.5 Tool Use Benchmarks (2026)
*Source: anthropic.com/news/claude-haiku-4-5; benchlm.ai; datacamp.com*

## Core Capabilities
- Full tool use, function calling, computer use, and all Claude API features
- No capability restrictions vs larger models — only reasoning depth differences
- Extended thinking: YES
- Supports: coding, bash, web search, computer-use tools

## Performance Benchmarks
- **Computer-use benchmark**: 50.7% (vs Claude Sonnet 4's 42.2% — 20% better at 3x lower cost)
- **SWE-bench Verified**: 73.3%
- **SWE-bench Pro (SEAL)**: 39.5%
- **Augment agentic coding eval**: 90% of Sonnet 4.5 performance
- **Arena Elo**: 1407

## BenchLM.ai Scores (57/100 overall, rank #54/117)
| Category | Score |
|----------|-------|
| Multimodal & Grounded | 72.8/100 |
| Instruction Following | 69.6/100 |
| Multilingual | 63.4/100 |
| Reasoning | 59.1/100 |
| Math | 55.0/100 |
| Coding | 53.8/100 |
| Knowledge | 48.1/100 |
| Agentic | 46.2/100 |

## Key Strength
"Particular strength is agentic workflows — multi-step tasks where the model needs to use tools, navigate codebases, and make sequential decisions"

## Pricing
- $1.00/$5.00 per MTok (4x more expensive on input than gpt-5-mini)
- 200k context window

## WebArena
- Not in top 10 raw model rankings (those require frontier-tier models like Sonnet/Opus)
- Haiku designed for fast executor role, not multi-step browser navigation strategy
