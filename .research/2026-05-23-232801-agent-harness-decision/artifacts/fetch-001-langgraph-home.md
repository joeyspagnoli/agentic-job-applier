# LangGraph Home — https://docs.langchain.com/oss/python/langgraph/overview

Fetched: 2026-05-24 (original URL redirected from langchain-ai.github.io/langgraph/)

## What It Is

LangGraph is a "low-level orchestration framework and runtime for building, managing, and deploying long-running, stateful agents." It is built by LangChain Inc. and operates at the **infrastructure level** — it does not abstract prompts or LLM calls, it orchestrates them. It is distinct from the `langchain` package, which is an LLM abstraction / integration library. LangGraph is the loop/state-machine runtime that runs on top of LangChain (or without it).

Companies cited as users: Klarna, Uber, J.P. Morgan.

## Core Value Proposition

- **Durable execution**: agents persist through failures and resume from interruption points
- **Human-in-the-loop**: inspect and modify agent state at any execution step
- **Memory**: both short-term working memory and long-term session persistence via checkpointers
- **Production-ready**: designed for stateful, long-running multi-agent workflows
- **Observability**: LangSmith integration for tracing and debugging

## Architecture

The fundamental primitive is a **directed graph** of nodes (processing steps) and edges (transitions). State flows through the graph as nodes execute.

```python
from langgraph.graph import StateGraph, MessagesState, START, END

graph = StateGraph(MessagesState)
graph.add_node("llm", llm_node)
graph.add_edge(START, "llm")
graph.add_edge("llm", END)
compiled = graph.compile()
```

## Installation

```
pip install -U langgraph
```

LangGraph itself has minimal direct dependencies (langgraph-core). Provider integration requires separate packages (e.g., `langchain-openai`, `langchain-anthropic`).

## Ecosystem Role

- `langchain`: LLM abstraction, integrations, prompt templates, retrievers
- `langgraph`: stateful graph runtime, agent loop
- `langgraph-cli`: local dev server + deployment tooling
- `LangSmith`: observability platform (optional, hosted)
- `LangGraph Platform`: hosted deployment (paid, cloud-only)

## Status

LangGraph 1.x is the current stable release (1.1.6 as of April 2026). Apache 2.0 licensed. 40,000+ GitHub stars on the core repo.
