# Source: https://openai.github.io/openai-agents-python/
# Fetched: 2026-05-23

## Overview

The OpenAI Agents SDK is a production-ready framework for building agentic AI applications. According to the documentation, it represents "a lightweight, easy-to-use package with very few abstractions" and serves as an upgrade to their earlier Swarm experimentation project.

## Design Philosophy

The SDK operates on two core principles:

1. Sufficient features for practical use, but minimal primitives to enable quick learning
2. Works effectively out-of-the-box while allowing deep customization

## Primary Primitives

- **Agents**: LLMs equipped with instructions and tools
- **Handoffs**: Enable agents to delegate tasks to other agents
- **Guardrails**: Validate agent inputs and outputs

## Key Features

- Built-in agent loop for tool invocation and task completion
- Python-native orchestration without requiring new abstractions
- Sandbox agents for isolated workspace execution
- Sessions for persistent memory across turns
- Human-in-the-loop capabilities
- Integrated tracing for visualization and debugging
- Realtime agents supporting voice interactions with `gpt-realtime-2`
- MCP server tool integration

## Installation

```
pip install openai-agents
```

## Basic Example

```python
from agents import Agent, Runner

agent = Agent(name="Assistant", instructions="You are a helpful assistant")

result = Runner.run_sync(agent, "Write a haiku about recursion in programming.")
print(result.final_output)

# Code within the code,
# Functions calling themselves,
# Infinite loop's dance.
```

**Note**: Requires `OPENAI_API_KEY` environment variable set.

## When to Use

Choose the Agents SDK when needing managed workflows with tool execution, guardrails, handoffs, or sessions. Use the Responses API directly for short-lived workflows where you prefer owning the loop and state handling.
