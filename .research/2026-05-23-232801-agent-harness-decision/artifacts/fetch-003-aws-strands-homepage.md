# Source: https://strandsagents.com/

## Strands Agents SDK Overview

### What It Is
"The open source agent harness SDK" — enables developers to "Build an agent harness. Control it end-to-end."
Open-source SDK for building production-ready AI agents in Python and TypeScript.

### Design Philosophy
A **model-driven agentic loop** approach:
- "Any model, any cloud" flexibility
- Built-in context management, execution limits, and observability
- Progressive complexity with "Zero lock-in"

Key architecture: hooks for intercepting agent decisions, conversation management
(including summarization), and tracing with custom attributes.

### Supported Model Providers (homepage)
- Amazon Bedrock (with Claude models)
- Model-agnostic by design (any provider)

### Maintenance & License
- **Maintainer**: AWS / Amazon ("from production systems inside Amazon")
- **License**: Open Source (Apache 2.0 confirmed via GitHub README)
- **Repositories**: strands-agents/sdk-python, strands-agents/sdk-typescript
- **Community**: 6,500+ GitHub stars

### Key Features
**Core Capabilities:**
- Tool definition and execution
- Pre/post-tool call hooks for monitoring and control
- Structured output models
- Conversation management (sliding window, summarization)
- Model Context Protocol (MCP) integration
- Interrupts for human approval workflows

**Observability:**
- Built-in tracing with custom attributes
- Hook-based logging and debugging

**Safety:**
- Guardrails via hooks
- Steering handlers for guided corrections
- Read-only access controls

**Patterns Supported:**
- Single agents with tool composition
- Multi-agent orchestration (Agent-as-Tool, Swarm patterns)
- Research and analysis workflows
- Customer support assistants
