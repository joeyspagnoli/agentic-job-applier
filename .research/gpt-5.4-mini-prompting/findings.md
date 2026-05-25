# gpt-5.4-mini prompting research — findings

Research date: 2026-05-25. Target: fixing a Pydantic AI agent on
`gpt-5.4-mini` (released 2026-03-17) that fails deterministic
multi-step browser automation despite the patterns being spelled out
in the system prompt.

## Source quality notes

- **Tier 1 (canonical):** `developers.openai.com/cookbook/examples/gpt-5/*`
  (GPT-5, GPT-5.1, GPT-5.2 prompting guides + troubleshooting guide),
  `developers.openai.com/api/docs/models/gpt-5.4-mini`,
  `pydantic.dev/docs/ai/*`, Pydantic AI GitHub issues/PRs.
- **Tier 2 (corroboration):** `community.openai.com` threads,
  Vellum's GPT-5 18-tip post, Simon Willison's 5.5 notes.
- **Could not retrieve:** `openai.com/index/introducing-gpt-5-4-mini-and-nano/`
  returned 403 (Cloudflare); the GitHub-rendered
  `prompt-optimization-cookbook.ipynb` only yielded partial extraction.
  Pulled gpt-5.4-mini release facts from secondary sources + the API
  model page.
- There is **no dedicated `gpt-5.4-mini` prompting guide** — the mini
  variants inherit from the GPT-5.x family guides.

## OpenAI-official gpt-5.4-mini guidance

- **Model card** (`developers.openai.com/api/docs/models/gpt-5.4-mini`):
  *"Our strongest mini model yet for coding, computer use, and
  subagents."* 400K context, 128K max output, knowledge cutoff
  2025-08-31, reasoning token support, function calling supported.
  Pricing $0.75/$4.50 per M tokens. Use cases: *"high-volume
  workloads"*, *"coding, computer use, and subagents."*
- **Release positioning** (per 9to5Mac/NxCode coverage of the OpenAI
  announcement): *"GPT-5.4 mini significantly improves over GPT-5
  mini across coding, reasoning, multimodal understanding, and tool
  use, while running more than 2× faster."* OpenAI explicitly
  positions the mini as a **narrow-task executor**: *"Larger models
  like GPT-5.4 can handle planning, coordination, and final judgment,
  while delegating to GPT-5.4 mini subagents that handle narrower
  subtasks in parallel."* This is exactly our use case — but it
  presumes the planner already narrowed the task, which is the change
  we need to make.

## Reasoning-effort knob

- **Supported values** (per GPT-5.2 guide, "Prompt Migration Guide to
  GPT 5.2"): `none | minimal | low | medium | high | xhigh`. Critical
  quote: *"default reasoning level for GPT-5 is medium, and for
  GPT-5.1 and GPT-5.2 is none."* By inheritance, **`gpt-5.4-mini`
  almost certainly defaults to `none`** (low-deliberation) — this is
  the most likely single root cause of our pattern-collapse and
  verification-skip failures.
- From the GPT-5 guide ("Reasoning effort" section): *"we provide a
  `reasoning_effort` parameter to control how hard the model thinks
  **and how willingly it calls tools**; the default is `medium`, but
  you should scale up or down depending on the difficulty of your
  task."* The knob directly affects tool-calling discipline, not just
  CoT depth.
- From the GPT-5 troubleshooting guide:
  *"Laziness/Underthinking … increase `reasoning_effort` … 'asking
  the model to construct an internal rubric and applying it to the
  solution before responding has been surprisingly effective on coding
  tasks.'"*
- **Pydantic AI exposure**
  (`pydantic.dev/docs/ai/api/models/openai/`):
  `OpenAIChatModelSettings.openai_reasoning_effort` — documented
  accepted values are *"low, medium, high"* only. `none/minimal/xhigh`
  may be API-accepted but not Pydantic-validated. Use `'high'` to
  stay inside the documented range.
- Per `pydantic.dev/docs/ai/advanced-features/thinking/`:
  *"Provider-specific settings … take precedence when both are set."*
  So prefer `openai_reasoning_effort='high'` over the unified
  `thinking` field.

## Tool calling / parallel calls

- **OpenAI API** `parallel_tool_calls: bool` (default `True`).
  Setting `False` forces ≤1 tool call per assistant turn.
- **Pydantic AI** `ModelSettings.parallel_tool_calls` — *"Whether to
  allow parallel tool calls."* Supported by OpenAI (non-o1), Groq,
  Anthropic, xAI (`pydantic.dev/docs/ai/api/pydantic-ai/settings/`).
- **Pydantic AI sequential execution mode** (PR #2718 / issue #2628,
  merged Aug 2025):
  ```python
  with agent.parallel_tool_call_execution_mode('sequential'):
      result = await agent.run(...)
  ```
  Issue #2628 explicitly notes: *"disabling parallel_tool_calls on
  the model … forces the model to do one tool call per turn which
  significantly inflates the turn count and cost."*
- **Two distinct mechanisms** — pick deliberately:
  1. `ModelSettings(parallel_tool_calls=False)` — model returns ≤1
     tool call per turn. More turns, more tokens, **strongest
     determinism guarantee.**
  2. `agent.parallel_tool_call_execution_mode('sequential')` — model
     may *propose* multiple calls; Pydantic AI executes them serially
     in proposal order instead of with `asyncio.gather`. Cheaper, but
     doesn't stop the model from planning the next 5 calls against a
     snapshot that the first call invalidates.

  For our failure #4 (DOM mutates between calls), **use option 1.**
  This is a correctness problem, not a perf problem.
- From GPT-5 troubleshooting on excessive tool calling: *"Select one
  tool or none; prefer answering from context when possible. Cap tool
  calls at 2 per user request unless new information makes more
  strictly necessary."*
- From OpenAI forum: *"Force tool selection: Use the parameter
  `tool_choice: 'required'` to bias the model toward calling tools
  before generating visible text output."*

## Structured output for tool calls

- Forum guidance
  (`community.openai.com/t/more-consistent-tool-calling-for-gpt-5/1361155`):
  *"structured outputs that are enforced as the final no-return
  destination of the AI's job"* — use Pydantic models as the
  **final** `output_type`, forcing the model to terminate by emitting
  a validated structured object. Pydantic AI's `output_type=MyModel`
  does exactly this.
- Same thread: *"Just have a function called `web_crawl` with the
  query parameter `page_url` might be more reliable"* — explicit
  narrow tools beat generic ones; *"Avoid few-shot examples that
  might confuse the model."*
- Vellum tip #9: use `allowed_tools` parameter for *"higher safety,
  predictability and prompt caching"* — restrict the tool subset per
  step.

## Anti-pattern mitigations (mapped to our failure modes)

### 1. Placeholder substitution (`<FIELD_ID_HERE>` copied verbatim)

- GPT-5 troubleshooting: *"Mode collapse (repeating garbage) stems
  from prompt contradictions."*
- GPT-5 guide on backticks: *"Use backticks to format file, directory,
  function, and class names."* By extension: never write
  angle-bracket placeholders inside the prompt — the model treats
  backticked content as literal.
- Cookbook prompt-optimization principle (verified excerpt): replace
  soft template language with hard concrete examples.
- **Fix:** stop putting placeholders in the static system prompt. Use
  Pydantic AI dynamic `instructions=` (or `@agent.system_prompt`) to
  interpolate real values per run; in examples, show only
  fully-substituted concrete forms.

### 2. Pattern collapse (3-step combobox flow → single `click`)

- Cursor's GPT-5 prompt tuning (cited in the GPT-5 guide): *"Using
  structured XML specs like `<[instruction]_spec>` improved
  instruction adherence."*
- GPT-5.1 guide: *"When selecting a replacement variant, verify it
  meets all user constraints (cheapest, brand, spec, etc.). Quote the
  item-id and price back for confirmation before executing."* —
  pattern: make the model echo the rule before acting.
- **Fix:** define **one named tool per step** instead of a generic
  `browser_action`. The model collapses general patterns; it does not
  collapse explicit tool catalogs.

### 3. Tool selection drift (picks `Female` for a Python/SQL question)

- GPT-5.2 guide: *"Prefer tools over internal knowledge whenever: You
  need fresh or user-specific data … You reference specific IDs,
  URLs, or document titles."*
- Forum: *"a single-purpose AI with one job"* with *"strong input
  containerization."*
- **Fix:** bind `(field_id, expected_value)` together as typed tool
  args. Executor sees `select_combobox_option(field_id="question_X",
  option_text="Yes")` — zero opportunity to grab the wrong snapshot
  row.

### 4. Parallel tool calls when sequencing matters

- See "Tool calling / parallel calls" — use
  `ModelSettings(parallel_tool_calls=False)`.
- Reinforce in prompt with `<execution_contract>`: "Emit exactly one
  tool call per assistant turn. Wait for its return value before
  proposing the next call. The DOM mutates after every interaction;
  any plan based on the prior snapshot is invalid."

### 5. Verification skipping

- GPT-5.2 guide: *"Before finalizing an answer … Briefly re-scan your
  own answer for: Unstated assumptions, Specific numbers or claims
  not grounded in context, Overly strong language."*
- GPT-5 guide ("Terminal-Bench prompt"): *"Once you finish coding,
  you must Check `git status` to sanity check your changes."* —
  direct analogue: must re-read accessibility tree before declaring
  complete.
- **Structural fix:** make verification a **separate tool**
  (`verify_combobox_filled(field_id) -> str`) and have the
  procedure require it before claiming `all_required_filled=True`.
- **Reasoning-effort fix:** this is the canonical "laziness" symptom
  — goes away with `openai_reasoning_effort='high'`.

## Recommended prompt structure (synthesis)

XML-tagged sections — confirmed by GPT-5 guide (Cursor section),
GPT-5.2 guide (uses `<output_verbosity_spec>`, `<tool_usage_rules>`,
`<extraction_spec>` throughout), and Anthropic's prompting docs
(cross-vendor convergence):

1. `<role>` — one-sentence persona
2. `<objective>` — outcome, not process
3. `<execution_contract>` — ONE tool call per turn; wait for return;
   re-read snapshot before next plan
4. `<tool_catalog>` — narrow, single-purpose tools with explicit arg
   names
5. `<step_patterns>` — one block per multi-step pattern (combobox,
   radio, file upload), each with `<step_1>...<step_n>` children
6. `<verification_contract>` — must verify before terminating
7. `<stop_conditions>` — explicit done definition
8. `<examples>` — at most 2 **fully-substituted** examples (no
   placeholders). Per Vellum #13 and GPT-5.1 guide: *"few-shot
   prompts can reduce performance when the task requires heavy
   reasoning."*

Plus a **persistence preamble** (troubleshooting guide): *"You are an
agent - please keep going until the user's query is completely
resolved, before ending your turn."* Counters the "report success and
exit early" failure.

## Recommended Pydantic AI Agent config changes

```python
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModelSettings

settings = OpenAIChatModelSettings(
    # Counters laziness / verification skipping / pattern collapse.
    # gpt-5.4-mini almost certainly inherits gpt-5.2's `none` default,
    # which is wrong for deterministic multi-step browser automation.
    openai_reasoning_effort='high',
    parallel_tool_calls=False,               # ONE tool call per turn
)

agent = Agent(
    'openai:gpt-5.4-mini',
    model_settings=settings,
    output_type=FinisherReport,              # forces structured termination
    system_prompt=build_xml_prompt(...),
)
```

Non-config (code) changes that the prompt alone cannot fix:

- Narrow the tool catalog with explicit one-step tools (e.g.
  `open_combobox`, `type_combobox_filter`, `select_combobox_option`,
  `verify_combobox_filled`) — each wraps exactly one CLI invocation.
- Bind `(field_id, expected_value)` at the planner and pass as typed
  args — eliminates failure #3 entirely.
- Strip every `<PLACEHOLDER>` token from the static system prompt;
  interpolate at runtime if needed.

## 5-bullet impact summary

1. **`openai_reasoning_effort='high'` is almost certainly the single
   biggest win.** `gpt-5.4-mini` inherits the GPT-5.2 default of
   `none` (zero deliberation), which explains the verification-skip
   and pattern-collapse failures — OpenAI's own troubleshooting guide
   names "laziness" the canonical fix.
2. **Set `parallel_tool_calls=False` at the model layer, not just the
   executor.** Our DOM-mutates-between-calls problem is a correctness
   issue; the Pydantic AI sequential execution context manager is the
   wrong tool because it still lets the model plan against a stale
   snapshot. The cost increase is acceptable.
3. **Stop putting `<PLACEHOLDER>` tokens in the static system
   prompt.** Show only fully-substituted examples. Backticked
   angle-bracket placeholders are treated literally by GPT-5 (per the
   markdown-formatting guidance in the GPT-5 guide).
4. **Replace generic tools with one named tool per step.**
   `open_combobox` / `type_combobox_filter` / `select_combobox_option`
   / `verify_combobox_filled` cannot collapse to a single click the
   way "agent_browser(args)" can.
5. **Migrate the prompt to XML-tagged sections**
   (`<execution_contract>`, `<step_patterns>`,
   `<verification_contract>`, `<examples>`) — confirmed by Cursor's
   GPT-5 tuning results cited in OpenAI's own guide, by GPT-5.2's own
   structure, and by Anthropic's docs (cross-vendor convergence).

## Sources

- [GPT-5 Prompting Guide](https://developers.openai.com/cookbook/examples/gpt-5/gpt-5_prompting_guide)
- [GPT-5.2 Prompting Guide](https://developers.openai.com/cookbook/examples/gpt-5/gpt-5-2_prompting_guide)
- [GPT-5 Troubleshooting Guide](https://developers.openai.com/cookbook/examples/gpt-5/gpt-5_troubleshooting_guide)
- [GPT-5.4 mini model page](https://developers.openai.com/api/docs/models/gpt-5.4-mini)
- [Pydantic AI OpenAI models](https://pydantic.dev/docs/ai/api/models/openai/)
- [Pydantic AI thinking/reasoning](https://pydantic.dev/docs/ai/advanced-features/thinking/)
- [Pydantic AI advanced tools (sequential mode)](https://pydantic.dev/docs/ai/tools-toolsets/tools-advanced/)
- [Pydantic AI issue #2628 — sequential tool execution](https://github.com/pydantic/pydantic-ai/issues/2628)
- [Forum — more consistent tool calling for GPT-5](https://community.openai.com/t/more-consistent-tool-calling-for-gpt-5/1361155)
- [Vellum — 18 GPT-5 prompting tips](https://www.vellum.ai/blog/gpt-5-prompting-guide)
