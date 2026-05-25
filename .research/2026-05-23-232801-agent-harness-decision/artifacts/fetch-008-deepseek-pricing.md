# DeepSeek API Pricing (May 2026)
*Source: api-docs.deepseek.com/quick_start/pricing — successfully fetched*

## Current Models

| Model | Input (Cache Hit) $/MTok | Input (Cache Miss) $/MTok | Output $/MTok | Context Window |
|-------|------------------------|--------------------------|--------------|----------------|
| DeepSeek-V4-Flash | $0.0028 | $0.14 | $0.28 | 1M tokens |
| DeepSeek-V4-Pro | $0.003625* | $0.435* | $0.87* | 1M tokens |

*75% promotional discount through May 31, 2026; regular pricing resumes after

## Capabilities
- Both models support: tool calling, JSON output formatting
- Both support thinking and non-thinking modes
- Max output: 384k tokens
- Context: 1M tokens

## Notes
- Model names `deepseek-chat` and `deepseek-reasoner` to be deprecated
- DeepSeek-V3 is now V4-Flash; V3.x naming no longer used
- Post-discount V4-Pro pricing: ~$1.74/$3.48 estimated (4x from promotional)
- DeepSeek V3.2 as agent backbone: 74.3% on WebArena (specialized framework)
- Cost is exceptional but requires non-OpenAI SDK integration and has China-based infrastructure considerations
