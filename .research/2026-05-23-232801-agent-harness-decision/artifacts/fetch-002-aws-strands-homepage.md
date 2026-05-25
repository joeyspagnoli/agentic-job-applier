# Strands Agents SDK Homepage — https://strandsagents.com/

Fetched: 2026-05-23

## What It Is
Strands Agents is an "open source AI agent SDK for Python & TypeScript" built by Amazon. The framework enables developers to construct agent systems with built-in observability, execution controls, and conversation management.

## Core Concept
The SDK operates around an agent loop that executes tool calls with full traceability. Developers define tools as functions, and the agent autonomously decides which to invoke based on user prompts. The loop includes hooks for intercepting and modifying behavior at each step.

## Supported Model Providers
While the homepage doesn't exhaustively list all integrations, it emphasizes compatibility with "any model, any cloud." The documentation references Amazon Bedrock and demonstrates framework-agnostic design allowing backend swapping without code changes.

## Key Features
- **Tool Definition**: Simple decorator pattern (`@tool`) for Python; schema-based for TypeScript
- **Hooks System**: Intercept events like `BeforeToolCallEvent` and `AfterToolCallEvent` for logging, validation, and guardrails
- **Conversation Management**: Built-in options including `SummarizingConversationManager` and `SlidingWindowConversationManager`
- **Structured Output**: Type-safe results using Pydantic models (Python) or Zod schemas (TypeScript)
- **MCP Integration**: Native support for Model Context Protocol clients for knowledge base grounding
- **Human Interrupts**: Pause agent execution pending approval before sensitive actions
- **Observability**: Default tracing with customizable attributes

## Deployment Options
"Deploy anywhere" on AgentCore, Lambda, Fargate, EKS, Docker, or Terraform.

## Origin & Status
Built "from production systems inside Amazon" with 6,500+ GitHub stars. The project launched through AWS's open-source initiative and maintains active community engagement via Discord.
