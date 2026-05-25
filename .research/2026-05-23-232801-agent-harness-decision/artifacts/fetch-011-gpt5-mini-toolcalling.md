# GPT-5-Mini Tool Calling Reliability (Production 2026)
*Source: WebSearch results; beam.ai/agentic-insights; mindstudio.ai; codersera.com*

## GPT-5-Mini (Aug 2025 Original)
- τ2-bench: **74.1%**
- MCP Atlas: **47.6%**
- Context: 400k tokens
- Pricing: $0.25/$2.00 per MTok

## GPT-5.4 Mini (Mar 2026 Successor)
- τ2-bench: **93.4%** (+19.3 points over gpt-5-mini)
- MCP Atlas: **57.7%** (+10.1 points)
- SWE-Bench Pro: 54.4% (near GPT-5.4's 57.7%)
- OSWorld (computer use): 72.1% (vs GPT-5.4's 75.0%)
- Pricing: $0.75/$4.50 per MTok (3x more expensive on input)
- Architecture: Uses "30% of the GPT-5.4 quota"

## Production Assessment (from MindStudio/Codersera analysis)
- "gpt-5-mini models are optimized specifically for the executor role: fast, tool-reliable, capable enough for well-defined subtasks"
- GPT-5.5 "one of the most reliable models available for long-horizon tasks that require multiple tool calls"
- "For production agentic workflows in 2026, both Claude and Gemini still hold measurable edges for tool-calling reliability at scale"
- "gpt-5-mini models... not the reasoning center of a system" but well-suited for structured executor tasks

## Key Comparison
The original gpt-5-mini (which the repo currently uses) has a 74.1% τ2-bench score. The newer gpt-5.4-mini at $0.75 input jumps to 93.4%. This is a significant quality-of-life improvement at 3x the input cost but still within budget ($0.06/apply typical).
