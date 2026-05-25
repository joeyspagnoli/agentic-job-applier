# Source: https://adk.dev/get-started/quickstart/ + `gh repo view google/adk-python`

Fetched 2026-05-23. The live `/get-started/quickstart/` page just returns a redirect notice in WebFetch — most actionable quickstart code comes from the GitHub README itself.

## Repo metadata (`gh api repos/google/adk-python`)

```json
{
  "stargazers_count": 19823,
  "open_issues_count": 845,
  "forks_count": 3450,
  "default_branch": "main",
  "license": "Apache-2.0",
  "created_at": "2025-04-01T20:44:40Z",
  "pushed_at": "2026-05-23T00:25:40Z",
  "archived": false
}
```

Released April 2025. ~19.8K stars in 13 months. Pushed today. Apache 2.0.

## Recent releases (every ~1-2 weeks)

```
v2.1.0      2026-05-23
v1.34.1     2026-05-23
v2.0.0      2026-05-19   <-- breaking change to v2
v1.34.0     2026-05-18
v1.33.0     2026-05-08
v1.32.0     2026-05-01
v2.0.0b1    2026-04-22
v1.31.1     2026-04-21
```

Roughly bi-weekly cadence. v2 just shipped (5 days ago) with breaking changes vs 1.x. **Our repo pins `google-adk==1.23.0`** — solidly on 1.x. Sessions written by 2.0 are readable by 1.28+ (extra fields ignored) but **NOT** readable by older 1.x; so we're on the older-incompatible side of the line, but that's only a concern if we cared about cross-version session interop, which we don't (each apply gets a fresh in-memory session).

## README v2.0 highlights

> "An open-source, code-first Python framework for building, evaluating, and deploying sophisticated AI agents with flexibility and control."

What's new in 2.0:
- **Workflow Runtime**: graph-based execution engine with routing, fan-out/fan-in, loops, retry, state management, dynamic nodes, human-in-the-loop, nested workflows.
- **Task API**: structured agent-to-agent delegation with multi-turn task mode, single-turn controlled output, mixed delegation patterns, HITL, and task agents as workflow nodes.

```bash
pip install google-adk
# or
pip install "google-adk[extensions]"
```

Python 3.11+ for v2 (PyPI page says 3.10+ supported for the v2.1.0 wheel).

## Agent + Workflow examples from README

```python
from google.adk import Agent

root_agent = Agent(
    name="greeting_agent",
    model="gemini-2.5-flash",
    instruction="You are a helpful assistant. Greet the user warmly.",
)
```

```python
from google.adk import Agent, Workflow

generate_fruit_agent = Agent(
    name="generate_fruit_agent",
    instruction="Return the name of a random fruit. Return only the name.",
)

generate_benefit_agent = Agent(
    name="generate_benefit_agent",
    instruction="Tell me a health benefit about the specified fruit.",
)

root_agent = Workflow(
    name="root_agent",
    edges=[("START", generate_fruit_agent, generate_benefit_agent)],
)
```

## Real production usage (`gh search code "from google.adk.agents import Agent"`)

```
amitkmaraj/course-creation-ai-agent-architecture
ajayagrawalgit/Apex
anxiong2025/5-Day-AI-Agents-Intensive-Course-with-Google
aryadoshii/newsletter-agent
rabimba/GDE-ML-Artifacts (uses Agent, SequentialAgent, LoopAgent, ParallelAgent)
jageenshukla/ADK-Agent
afsara-ben/Obsidian_agent
AbiramiSukumaran/scm-memory-agent
ohboyftw/herdFlow
RAKASH2003/Architectural_Guardrail
atakamizawa/gemini-research-tools-mcp
Chiru-Dey/relief_project
Venkat5674/Google_Ai_Agents_course
c1r5/learning-google-adk (MCP integration)
gabrielpreda/adk-a2a-travel-assistant
```

Mostly tutorial/demo repos, plus a few real integrations (gemini-research-tools-mcp uses ADK with MCP; adk-a2a-travel-assistant exercises agent-to-agent). Real production usage is still maturing.
