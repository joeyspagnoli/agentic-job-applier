# gh-retry-002-openai.md
# Command: gh search issues "retry" --repo openai/openai-agents-python --sort=comments --limit 5
# Date: 2026-05-24

## Results

| Title | URL | State | Comments |
|-------|-----|-------|----------|
| How would I handoff a non-reasoning model with tool calls to a reasoning model? | https://github.com/openai/openai-agents-python/issues/722 | closed | 19 |
| Support passing metadata (_meta) in MCP tool calls | https://github.com/openai/openai-agents-python/issues/2367 | closed | 17 |
| Retry mechanism for ModelBehaviorError | https://github.com/openai/openai-agents-python/issues/325 | open | 14 |
| Resilience mechanism Openai/ LiteLLM | https://github.com/openai/openai-agents-python/issues/2050 | closed | 11 |
| Duplicate item found with id fc_xxxx when using conversation_id with function calling | https://github.com/openai/openai-agents-python/issues/1789 | closed | 10 |

## Key Finding

Issue #325 (Retry mechanism for ModelBehaviorError) is OPEN — meaning the framework still has no native retry for ModelBehaviorError. The top retry issue has 14 comments but no resolution. Users are told `function_tool` "catches errors and attempts to have the LLM run again" but the actual crash scenario (model calls nonexistent tool) is not handled.

Issue #2050 (Resilience mechanism) discusses adding tenacity/retry-decorator integration — community workaround, not a framework feature.
