# forum-retry-002-openai.md
# Source: GitHub Issues + forum search
# Date: 2026-05-24

## GitHub Issue #325 — "Retry mechanism for ModelBehaviorError"
URL: https://github.com/openai/openai-agents-python/issues/325
Comments: 14 (open)

**Issue opener:**
"While using the framework for extensive agent runs, in rare circumstances the LLM will attempt to call a nonexistent tool, which crashed a whole 10-minute agent run." They requested a retry mechanism allowing re-execution of the errored LLM call.

**OpenAI collaborator (@rm-openai) initial response:**
"Hmm can you share some code? `function_tool` already catches errors and attempts to have the LLM run again. Would be useful to know where it crashed so that I can debug."

[User showed the real crash — ModelBehaviorError when model calls tool by slightly wrong name]

**@timdoctronic:**
"having the same question regarding retries and also want to know the proper way of using tenacity.retry with Runner.run_streamed (if possible)"

**@jackien1:**
"also curious about retries with Runner.run_streamed or what is the proper mechanism"

**Key takeaway:** No native retry mechanism. Users reach for tenacity (external library). ModelBehaviorError (model calls nonexistent tool) crashes entire run instead of re-asking model.

---

## Community Forum — "Errors received with Agents SDK"
URL: https://community.openai.com/t/errors-received-with-agents-sdk/1356932

Users reporting: "The model did not produce a final response!" and MaxTurns() exceeded errors when using orchestrator agents with subagents and tools.

---

## Production failure (from search): Schema drift pattern
Schema drift was breaking tool calls across every OpenAI and Anthropic integration simultaneously — tool schemas losing type keys or missing required fields. The SDK raises ModelBehaviorError in these cases with no retry path.
