# Source: https://openai.github.io/openai-agents-python/agents/
# Fetched: 2026-05-23

## Agents Concept

An Agent is the foundational building block. "An agent is a large language model (LLM) configured with instructions, tools, and optional runtime behavior such as handoffs, guardrails, and structured outputs."

### Properties

| Property | Required | Purpose |
|----------|----------|---------|
| `name` | Yes | Human-readable identifier |
| `instructions` | No | System prompt (strongly recommended) |
| `model` | No | Which LLM to use |
| `tools` | No | Capabilities the agent can call |
| `handoffs` | No | Specialist agents to delegate to |
| `output_type` | No | Structured output format |
| `model_settings` | No | Tuning parameters like temperature |
| `hooks` | No | Lifecycle callbacks |

### Basic example

```python
from agents import Agent, function_tool

@function_tool
def get_weather(city: str) -> str:
    """returns weather info for the specified city."""
    return f"The weather in {city} is sunny"

agent = Agent(
    name="Haiku agent",
    instructions="Always respond in haiku form",
    model="gpt-5-nano",
    tools=[get_weather],
)
```

### Dynamic instructions

```python
def dynamic_instructions(
    context: RunContextWrapper[UserContext], agent: Agent[UserContext]
) -> str:
    return f"The user's name is {context.context.name}. Help them with their questions."

agent = Agent[UserContext](
    name="Triage agent",
    instructions=dynamic_instructions,
)
```

### Agents as Tools

```python
booking_agent = Agent(...)
refund_agent = Agent(...)

customer_facing_agent = Agent(
    name="Customer-facing agent",
    instructions=(
        "Handle all direct user communication. "
        "Call the relevant tools when specialized expertise is needed."
    ),
    tools=[
        booking_agent.as_tool(
            tool_name="booking_expert",
            tool_description="Handles booking questions and requests.",
        ),
        refund_agent.as_tool(
            tool_name="refund_expert",
            tool_description="Handles refund questions and requests.",
        )
    ],
)
```

### Handoffs

```python
triage_agent = Agent(
    name="Triage agent",
    instructions=(
        "Help the user with their questions. "
        "If they ask about booking, hand off to the booking agent. "
        "If they ask about refunds, hand off to the refund agent."
    ),
    handoffs=[booking_agent, refund_agent],
)
```

### Output types (structured)

```python
from pydantic import BaseModel
from agents import Agent

class CalendarEvent(BaseModel):
    name: str
    date: str
    participants: list[str]

agent = Agent(
    name="Calendar extractor",
    instructions="Extract calendar events from text",
    output_type=CalendarEvent,
)
```

### Cloning

```python
pirate_agent = Agent(name="Pirate", instructions="Write like a pirate", model="gpt-5.5")
robot_agent = pirate_agent.clone(name="Robot", instructions="Write like a robot")
```

### ModelSettings — force tool usage

```python
from agents import Agent, Runner, function_tool, ModelSettings

@function_tool
def get_weather(city: str) -> str:
    """Returns weather info for the specified city."""
    return f"The weather in {city} is sunny"

agent = Agent(
    name="Weather Agent",
    instructions="Retrieve weather details.",
    tools=[get_weather],
    model_settings=ModelSettings(tool_choice="get_weather")
)
```

`tool_choice` values: `auto`, `required`, `none`, or a tool name.

### Lifecycle hooks

```python
from agents import Agent, RunHooks, Runner

class LoggingHooks(RunHooks):
    async def on_agent_start(self, context, agent):
        print(f"Starting {agent.name}")

    async def on_llm_end(self, context, agent, response):
        print(f"{agent.name} produced {len(response.output)} output items")

    async def on_agent_end(self, context, agent, output):
        print(f"{agent.name} finished with usage: {context.usage}")

agent = Agent(name="Assistant", instructions="Be concise.")
result = await Runner.run(agent, "Explain quines", hooks=LoggingHooks())
print(result.final_output)
```

### Tool use behavior

```python
agent = Agent(
    name="Weather Agent",
    instructions="Retrieve weather details.",
    tools=[get_weather],
    tool_use_behavior="stop_on_first_tool"
)
```

Options: `"run_llm_again"` (default), `"stop_on_first_tool"`, `StopAtTools(stop_at_tool_names=[...])`, or custom `ToolsToFinalOutputFunction`.
