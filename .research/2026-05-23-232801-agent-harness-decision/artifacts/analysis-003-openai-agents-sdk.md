# OpenAI Agents SDK — Agent Harness Analysis for Layer-3 Browser Finisher

**Sources:** fetch-001 through fetch-006-openai-agents-sdk-*.md, gh-002.
**Verdict preview:** ACCEPTABLE — ergonomically nicer for tool loops, but not
in the repo today and adds a net-new dep.

---

## 1. What It Is — Minimalist Loop + Handoffs + Guardrails

The OpenAI Agents SDK (`openai-agents` on PyPI) is a production-ready framework
described as "a lightweight, easy-to-use package with very few abstractions." It
is the spiritual successor to the Swarm experimentation project, hardened for
production. Three core primitives:

- **Agents** — LLMs equipped with instructions, tools, and optional hooks.
- **Handoffs** — Delegation from one agent to a specialist.
- **Guardrails** — Input, output, and per-tool validation with tripwire semantics.

As of May 2026, `openai-agents` is **not in `pyproject.toml`** for this repo.
Adding it would require a new pinned dep. The existing `openai==2.26.0` package is
present but is the raw OpenAI client, not the agents SDK.

---

## 2. Loop Primitive — Runner.run + @function_tool

The API is intentionally minimal. An agent is declared, tools are decorated, and
a single `await Runner.run(agent, input, session=session)` drives the loop:

```python
from agents import Agent, Runner, function_tool, SQLiteSession

@function_tool
async def fill_field(selector: str, value: str) -> str:
    """Fill an input field on the current page.

    Args:
        selector: CSS selector for the input field.
        value: Text to type.
    """
    await page.fill(selector, value)
    return f"Filled {selector}"

agent = Agent(
    name="browser_finisher",
    instructions="Fill the job application form. Never submit.",
    model="gpt-4.1-mini",
    tools=[fill_field, read_field, click_button, scroll_to, get_page_state, report_done],
)

session = SQLiteSession(f"apply_{job_id}")  # in-memory SQLite per apply

result = await Runner.run(agent, task_prompt, session=session)
print(result.final_output)
```

`Runner.run` handles the entire multi-turn tool loop internally and returns a
`RunResult` with `.final_output` (the agent's last text response). No event-loop
boilerplate required — the framework manages turns, tool dispatch, and history.

Synchronous variant: `Runner.run_sync(agent, input)` — useful for simple scripts.

---

## 3. Guardrails — Blocking "click Submit"

The SDK has three guardrail levels. For the "never submit" use case, **tool
guardrails** are the most precise choice — they wrap individual `@function_tool`
functions and can prevent execution before it occurs.

```python
from agents import function_tool, tool_input_guardrail
from agents.guardrails import ToolGuardrailFunctionOutput

@tool_input_guardrail
def block_submit(data) -> ToolGuardrailFunctionOutput:
    """Hard block on any submit tool."""
    tool_name = data.context.tool_name or ""
    if "submit" in tool_name.lower():
        return ToolGuardrailFunctionOutput.reject_content(
            "SUBMIT_BLOCKED: submitting forms is disabled by policy."
        )
    return ToolGuardrailFunctionOutput.allow()

@function_tool(tool_input_guardrails=[block_submit])
async def click_submit(button_selector: str) -> str:
    """Click the submit button on a form."""
    # This body never executes when the guardrail fires.
    await page.click(button_selector)
    return "submitted"
```

`reject_content(msg)` skips tool execution and returns `msg` as the tool result
visible to the LLM. The actual click never occurs.

For a broader safety net, an **input guardrail** with blocking execution can screen
the task description itself:

```python
from agents import input_guardrail, GuardrailFunctionOutput, RunContextWrapper

@input_guardrail
async def no_submit_in_task(
    ctx: RunContextWrapper[None], agent: Agent, input: str
) -> GuardrailFunctionOutput:
    triggered = "submit" in str(input).lower() and "don't" not in str(input).lower()
    return GuardrailFunctionOutput(
        output_info={"reason": "submit keyword in input"},
        tripwire_triggered=triggered,
    )
```

When a tripwire fires, the SDK raises `InputGuardrailTripwireTriggered` — catch it
in the caller to log and abort the apply cleanly.

---

## 4. Sessions / State

Sessions manage conversation history automatically across turns. For a per-apply
isolated context:

```python
from agents import SQLiteSession

session = SQLiteSession(f"apply_{job_id}")  # no path = in-memory SQLite
result = await Runner.run(agent, task_prompt, session=session)
```

Before each `Runner.run` call the SDK prepends stored history to the new input.
After the run, all items (user input, LLM responses, tool calls) are persisted
automatically. For multi-page forms requiring multiple `Runner.run` calls per apply
(e.g., Next-page navigation), the session carries the full context forward without
manual `.to_input_list()` gymnastics.

`SQLiteSession` without a file path is in-memory — zero disk I/O, zero setup,
equivalent to ADK's `InMemorySessionService`.

---

## 5. Provider Portability — LiteLLM Bridge

The SDK defaults to OpenAI via the Responses API or Chat Completions API. For
non-OpenAI providers:

```bash
pip install openai-agents[litellm]
```

```python
from agents.extensions.models import LiteLLMModel

agent = Agent(
    name="browser_finisher",
    model=LiteLLMModel(model="litellm/anthropic/claude-haiku-4-5"),
)
```

Or use the raw `OpenAIChatCompletionsModel` with a custom `base_url` for any
OpenAI-compatible endpoint:

```python
from agents import AsyncOpenAI, OpenAIChatCompletionsModel

client = AsyncOpenAI(api_key="...", base_url="https://openrouter.ai/api/v1")
model = OpenAIChatCompletionsModel(model="anthropic/claude-haiku-4-5", openai_client=client)
agent = Agent(name="browser_finisher", model=model, ...)
```

**Important:** When using non-OpenAI providers, disable the built-in tracing to
avoid 401 errors:

```python
from agents import set_tracing_disabled
set_tracing_disabled(disabled=True)
```

This is a gotcha not present in the ADK path — ADK's tracing is optional and
provider-agnostic by default.

---

## 6. Browser-Agent Fit

All 6 browser tools register cleanly with `@function_tool`:

```python
@function_tool
async def get_page_state() -> str:
    """Return current URL, title, and visible form fields as JSON."""
    return json.dumps({
        "url": page.url,
        "title": await page.title(),
        "fields": await page.evaluate("() => getFormFields()"),
    })

@function_tool
async def fill_field(selector: str, value: str) -> str:
    """Fill a visible input field using its CSS selector."""
    await page.fill(selector, value)
    return f"ok: filled {selector}"

@function_tool
async def click_button(selector: str) -> str:
    """Click a non-submit button (Next page, section nav, etc.)."""
    await page.click(selector)
    return f"ok: clicked {selector}"

@function_tool
async def report_done(summary: str) -> str:
    """Signal that form filling is complete without submitting."""
    return json.dumps({"status": "DONE", "summary": summary})
```

`page` injection works identically to ADK — via closure or module-level reference
to the `Page` obtained from `playwright.chromium.connect_over_cdp("http://localhost:9222")`.

The `@function_tool` decorator is more readable than ADK's bare-function-in-list
approach, but functionally equivalent. Schema inference uses `inspect` + `griffe`
(supports Google, Sphinx, NumPy docstrings).

One advantage: `tool_use_behavior="stop_on_first_tool"` or
`StopAtTools(stop_at_tool_names=["report_done"])` provides a clean terminal
condition for the loop — when `report_done` is called the runner stops and returns
`final_output` immediately, without needing to check `is_final_response()` events.

---

## 7. Verdict: ACCEPTABLE (but not the right choice here)

**Strengths:**
- Cleaner ergonomics: `await Runner.run(agent, input, session=session)` vs. the
  async-generator event loop dance.
- First-class guardrails as a framework concept (vs. ADK's callbacks which require
  knowing the right hook name).
- `StopAtTools` for a clean `report_done` terminal condition.
- `SQLiteSession` built-in, no schema required.

**Weaknesses for this use case:**
- **Not in the repo.** Adding `openai-agents` is a new pinned dep. With our
  existing `openai==2.26.0`, we'd also need to verify version compatibility.
- **`openai-agents[litellm]` is a second install** for non-OpenAI provider support.
  The repo already has `litellm==1.82.1` but not the `openai-agents` extras.
- **Tracing gotcha.** Must call `set_tracing_disabled(True)` when not using OpenAI
  keys — an operational footgun.
- **Parallel framework concern.** Running two agent frameworks in the same process
  (ADK for the decider, OpenAI Agents SDK for the finisher) increases cognitive
  overhead and import weight.
- **No hard LLM-call cap.** There is no direct equivalent to ADK's
  `RunConfig(max_llm_calls=N)`. Loop termination relies on `report_done` tool
  design and prompt compliance.
