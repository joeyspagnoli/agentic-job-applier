# Project Deep Dive — microsoft/magentic-ui

URL: https://github.com/microsoft/magentic-ui
Stars: 9,852 (as of 2026-05-24)
Last commit: 2026-05-24 (active)
Language: Python
Version: pyproject.toml dynamic

## Agent Harness

**CUSTOM PROTOCOL — not AutoGen, not LangGraph.**

Despite the name "magentic" (suggesting AutoGen/agentic roots), the implementation is a clean-room custom async Python protocol:

```python
@runtime_checkable
class SubAgentProtocol(Protocol):
    def run_stream(self, task: str, **kwargs: Any) -> AsyncIterator[StreamUpdate | InputRequest]:
        ...
```

Key observation: The `agents/base.py` defines a `SubAgentProtocol` using Python's `typing.Protocol` — this is pure Python structural typing, no framework dependency. The orchestrator (`OmniAgent`) dispatches to sub-agents via this protocol.

Sub-agents include:
- `web_surfer` — Playwright-based browser agent
- `fara` — integrates FARA-7B model for computer use

## Browser Layer

Playwright (`playwright>=1.58,<1.61`) used directly in the web_surfer agent, not through browser-use.

## Dependencies Analysis (pyproject.toml)

```
openai>=1.0.0          # direct model calls
playwright>=1.58,<1.61  # browser
pydantic               # data validation
quick-sandbox[qemu,cua]~=0.11.14  # sandboxed CUA
quicksand-cua>=0.3.10  # computer use abstraction
```

NO LangChain, NO OpenAI Agents SDK, NO Google ADK, NO Pydantic AI, NO browser-use in core.

## What This Means

Microsoft, with all their resources and the AutoGen team in-house, chose to **write a custom protocol** for their shipped browser agent product rather than use AutoGen (their own framework) or any other harness. This is a powerful signal: even the team that built a major agent framework chose NOT to use it for their production browser agent.

## Recent Activity

Commits from 2026-05-24:
- Security: resolve CodeQL py/path-injection alert
- Document verified Foundry deployment settings
- README demo video updates

The project is actively maintained and used in research deployments.
