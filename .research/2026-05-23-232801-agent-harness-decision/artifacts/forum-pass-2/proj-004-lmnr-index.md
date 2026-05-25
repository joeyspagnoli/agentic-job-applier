# Project Deep Dive — lmnr-ai/index

URL: https://github.com/lmnr-ai/index
Stars: 2,348 (as of 2026-05-24)
Last commit: 2026-05-22 (active)
Language: Python
Description: "SOTA Open-Source Browser Agent for autonomously performing complex tasks on the web"

## Agent Harness

**BYO CUSTOM ASYNC LOOP — no framework.**

`index/agent/agent.py` implements a clean `Agent` class:

```python
class Agent:
    def __init__(self, llm: BaseLLMProvider, browser_config: BrowserConfig | None = None):
        self.llm = llm
        self.controller = Controller()
        self.browser = Browser(config=browser_config)
        self.message_manager = MessageManager(action_descriptions=...)
        self.state = AgentState(messages=[])

    async def step(self, step: int, previous_result: ActionResult | None = None, ...) -> tuple:
        state = await self.browser.update_state()
        self.message_manager.add_current_state_message(state, previous_result)
        input_messages = self.message_manager.get_messages()
        model_output = await self._generate_action(input_messages)
        ...
```

This is essentially the same **observe→plan→act** pattern as browser-use but implemented independently. No framework imports.

## Browser Layer

Custom `Browser` class wrapping Playwright. Custom `Controller` for action execution.

## Dependencies (pyproject.toml)

```
anthropic[bedrock]>=0.52.0  # direct
openai>=1.65.2               # direct
playwright>=1.50.0            # browser
google-genai>=1.11.0          # direct
groq>=0.24.0                  # direct
lmnr[anthropic,openai,groq]>=0.6.2  # Laminar observability
```

NO LangChain, NO OpenAI Agents SDK, NO Google ADK, NO Pydantic AI.

## Observability Choice

Uses `lmnr` (Laminar) for tracing with `@observe` decorator and `use_span` context manager. The team (lmnr-ai) builds Laminar, so this is both dogfooding and practical — they use OpenTelemetry-compatible spans to track every LLM call and browser action.

## What This Means

A well-engineered, 2.3k-star project that claims SOTA on browser agent benchmarks built from scratch without any agent framework. The pattern: model calls go through direct SDK, browser actions through Playwright, the loop is ~200 lines of pure Python. The team cares about observability and wired in Laminar for that, but explicitly didn't use a framework for the agent loop itself.
