# Source: https://openai.github.io/openai-agents-python/guardrails/
# Fetched: 2026-05-24

## Overview

Guardrails are validation/checking mechanisms for user input and agent output.
The SDK supports three guardrail categories:

1. **Input guardrails** — validate/block the initial user input before the agent runs.
2. **Output guardrails** — validate the agent's final output.
3. **Tool guardrails** — intercept individual function-tool calls.

## Tripwire Mechanism

When `tripwire_triggered=True` is returned from any guardrail, the SDK immediately
raises either `InputGuardrailTripwireTriggered` or `OutputGuardrailTripwireTriggered`,
halting agent execution. This is a hard stop — no further LLM calls or tool calls
execute after a tripwire fires.

## Input Guardrail

```python
from agents import (
    Agent, Runner, input_guardrail, GuardrailFunctionOutput,
    RunContextWrapper, TResponseInputItem
)

@input_guardrail
async def math_guardrail(
    ctx: RunContextWrapper[None],
    agent: Agent,
    input: str | list[TResponseInputItem],
) -> GuardrailFunctionOutput:
    result = await Runner.run(guardrail_agent, input, context=ctx.context)
    return GuardrailFunctionOutput(
        output_info=result.final_output,
        tripwire_triggered=result.final_output.is_math_homework,
    )

agent = Agent(
    name="Customer support agent",
    instructions="You are a customer support agent.",
    input_guardrails=[math_guardrail],
    output_type=MessageOutput,
)
```

### Parallel vs. Blocking Execution

- **Parallel** (default): guardrail runs concurrently with agent — optimizes
  latency but the agent may consume tokens before the guardrail fires.
- **Blocking**: guardrail completes before agent starts — prevents token
  consumption. Ideal for cost optimization.

## Output Guardrail

```python
from agents import output_guardrail

@output_guardrail
async def sensitive_output_guardrail(
    ctx: RunContextWrapper,
    agent: Agent,
    output: MessageOutput,
) -> GuardrailFunctionOutput:
    result = await Runner.run(guardrail_agent, output.response, context=ctx.context)
    return GuardrailFunctionOutput(
        output_info=result.final_output,
        tripwire_triggered=result.final_output.is_sensitive,
    )
```

Output guardrails always run after agent completion. They do not support parallel
execution.

## Tool Guardrails — Most Relevant for "Never Submit"

Tool guardrails wrap individual `@function_tool` decorated functions. They can
prevent the tool from executing at all and replace the output with a message.

```python
from agents import function_tool, tool_input_guardrail, tool_output_guardrail
from agents.guardrails import ToolGuardrailFunctionOutput
import json

@tool_input_guardrail
def block_submit_tool(data) -> ToolGuardrailFunctionOutput:
    """Block any tool call whose name contains 'submit'."""
    tool_name = data.context.tool_name or ""
    if "submit" in tool_name.lower():
        return ToolGuardrailFunctionOutput.reject_content(
            "SUBMIT_BLOCKED: submitting forms is disabled by policy."
        )
    return ToolGuardrailFunctionOutput.allow()

@function_tool(tool_input_guardrails=[block_submit_tool])
def click_submit(button_selector: str) -> str:
    """Click the submit button on a form."""
    # This body never executes when the guardrail fires.
    ...
```

`ToolGuardrailFunctionOutput.reject_content(msg)` — skip execution, return `msg`
as the tool result visible to the LLM.
`ToolGuardrailFunctionOutput.allow()` — let execution proceed.

**Limitation**: Tool guardrails apply only to `@function_tool` decorated functions,
NOT to handoffs or hosted tools.

## Attaching Guardrails to an Agent

```python
agent = Agent(
    name="Browser finisher",
    instructions="Fill the application form.",
    input_guardrails=[input_level_guardrail],
    output_guardrails=[output_level_guardrail],
    tools=[fill_field, click_button, read_page],  # tool-level guardrails attach at @function_tool
)
```

## Exception Handling

```python
from agents import InputGuardrailTripwireTriggered, OutputGuardrailTripwireTriggered

try:
    result = await Runner.run(agent, user_input)
except InputGuardrailTripwireTriggered:
    print("Input guardrail fired — request blocked.")
except OutputGuardrailTripwireTriggered:
    print("Output guardrail fired — response blocked.")
```

## Summary for "Never Click Submit" Use Case

The tool-guardrail approach (`@tool_input_guardrail` on the submit tool) is the
cleanest implementation: the guardrail fires before the tool body executes and
returns a rejection message the LLM sees as the tool result. No actual click occurs.
Alternatively, an `@input_guardrail` with blocking mode can screen the agent's
initial task description for any hint of a submit-triggering instruction.
