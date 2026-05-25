# OpenAI Models Overview (May 2026)
*Source: platform.openai.com/docs/models returned HTTP 403; data from secondary sources*

## Current Production Models

### GPT-5 Family (Aug 2025)
- **gpt-5-nano**: 400k context, $0.05/$0.40, vision + tools + reasoning + caching
- **gpt-5-mini**: 400k context, $0.25/$2.00, vision + tools + reasoning + caching

### GPT-5.4 Family (Mar 2026) 
- **gpt-5.4-nano**: ~$0.20/$1.25, improved tool calling
- **gpt-5.4-mini**: ~$0.75/$4.50, τ2-bench 93.4% (vs gpt-5-mini's 74.1%), MCP Atlas 57.7%
- **gpt-5.4**: ~$2+, SWE-bench Pro 57.7%

### Reasoning Models
- **o4-mini**: Cost-efficient reasoning model; pricing not confirmed from official source

## Key Notes for Agentic Use
- GPT-5.4 Mini validated for "executor role in multi-model systems: fast, tool-reliable"
- gpt-5-mini context limit (400k) is adequate for browser-fill task AX-tree snapshots (300 tokens/turn)
- OSWorld computer-use: gpt-5.4-mini 72.1%, gpt-5.4 75.0%
