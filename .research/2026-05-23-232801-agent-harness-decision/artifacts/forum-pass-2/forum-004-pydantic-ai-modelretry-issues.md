pydantic/pydantic-ai	5217	open	MCP isError:true is indiscriminately converted to ModelRetry — non-retryable tool errors should reach the LLM as informational results		2026-04-27T21:20:55Z
pydantic/pydantic-ai	5015	open	[Feature] Allow custom output schema for `judge_input_output` and `judge_output`	feature	2026-04-25T10:54:11Z
pydantic/pydantic-ai	2646	open	Add "modelretry" end strategy	feature	2025-08-26T00:22:02Z
pydantic/pydantic-ai	4767	open	Feature Request: `end_strategy` that defers output tool result when sibling function tools fail	feature	2026-03-21T19:29:21Z
pydantic/pydantic-ai	4891	open	Retry logic incorrectly depends on tool-call protocol, causing failures on non-tool backends	bug	2026-03-31T22:28:22Z
pydantic/pydantic-ai	2586	open	More flexible tool exception handling	feature	2026-05-20T01:19:25Z
pydantic/pydantic-ai	5551	open	Fail-fast option for sequential tool execution (abort downstream tools on upstream failure)		2026-05-21T15:22:02Z
pydantic/pydantic-ai	5034	open	`judge_output() reason field can be polluted by visible reasoning/thinking text`	bug	2026-05-13T01:26:27Z
pydantic/pydantic-ai	4908	open	Support retry mechanism sending minimal correction context instead of full conversation history	feature, capability-solveable	2026-04-12T15:37:18Z
pydantic/pydantic-ai	3566	open	Allow customization of all prompts sent by the framework to the model	feature, meta	2026-04-15T09:03:20Z
pydantic/pydantic-ai	5238	open	Output validator `ctx.last_attempt` can be inaccurate when `ToolOutput.max_retries` exceeds `output_retries`		2026-05-04T05:41:09Z
pydantic/pydantic-ai	5145	closed	Tools can't fail without failing the turn	feature	2026-04-29T11:10:21Z
pydantic/pydantic-ai	3352	open	Add per-tool usage limits	feature, capability-solveable	2026-05-04T07:38:24Z
pydantic/pydantic-ai	5601	closed	[aw] Pydantic AI Streaming Resilience Sweep failed	meta, pydanty:meta, agentic-workflows	2026-05-23T16:54:57Z
pydantic/pydantic-ai	2793	open	Allow structured output and text for all ModelResponses except the last one	feature	2025-12-05T21:59:20Z
pydantic/pydantic-ai	4941	closed	Image output validators not called and `wrap_validation_errors` bug		2026-04-02T23:41:55Z
pydantic/pydantic-ai	2600	open	Anthropic `stop_reason` `pause_turn` is not handled correctly, resulting in errors with long-running built-in tools	bug	2026-04-15T09:03:15Z
pydantic/pydantic-ai	4518	open	`args_validator` from `FunctionToolset` wrapped in `DynamicToolset` is silently dropped with `TemporalAgent`	bug, temporal	2026-03-05T00:27:08Z
pydantic/pydantic-ai	4744	closed	`Agent(retries=...)` not propagated to user-provided toolsets	bug	2026-04-30T18:02:38Z
pydantic/pydantic-ai	5517	open	v2: Output functions should be called once on final output during `run_stream()`, not on every partial	feature	2026-05-22T22:21:37Z
