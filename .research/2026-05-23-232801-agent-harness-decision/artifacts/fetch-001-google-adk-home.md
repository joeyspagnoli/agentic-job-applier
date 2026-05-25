# Source: https://adk.dev/ (formerly https://google.github.io/adk-docs/)

Fetched 2026-05-23. The old `google.github.io/adk-docs/` URLs now 301 redirect to `adk.dev/` — Google appears to have promoted ADK to its own dedicated domain in 2026.

## Overview

The Agent Development Kit is an open-source framework for building production-grade AI agents. Tagline on the homepage: "Build production agents, not prototypes."

## Supported Languages

ADK ships in five languages:
- Python
- TypeScript
- Go
- Java
- Kotlin

## Key Features (2026)

- **Graph Workflows** (ADK 2.0): graph-based architectures combining "deterministic code with adaptive AI reasoning" for structured task orchestration.
- **Multi-Agent Systems**: collaborative workflows and multi-agent orchestration patterns including sequential, loop, and parallel configurations.
- **Context Management**: filtering irrelevant events, summarizing conversations, and tracking token usage.

## AI Model Support

Native integration with Gemini, plus model connectors for:
- Anthropic Claude (via direct registry / adapter)
- OpenAI (via LiteLLM)
- Locally-running models (Ollama, vLLM)
- Enterprise-hosted options (Apigee gateway)

## Deployment Options

- Containerized deployment on custom infrastructure
- Google Cloud Agent Runtime / Vertex AI Agent Engine
- Cloud Run
- GKE

## Development Philosophy

The framework lets developers start with simple prompts and tools, then progressively adopt advanced features like multi-agent orchestration and performance evaluation.

## Top-of-doc Quick code

From the GitHub README v2.0:

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

Run locally:

```bash
adk run path/to/my_agent
adk web path/to/agents_dir
```
