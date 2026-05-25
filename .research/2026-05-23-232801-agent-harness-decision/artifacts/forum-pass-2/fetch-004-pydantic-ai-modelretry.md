# Source URL: https://ai.pydantic.dev/mcp/

Overview | Pydantic Docs - Skip to content Pydantic Docs

Pydantic Validation Pydantic AI Pydantic Logfire Search ⌘ K












Pydantic Validation Pydantic AI Pydantic Logfire Pydantic AI
- Installation
- Getting Help
- Troubleshooting
- Coding Agent Skills
- Pydantic AI Gateway
- Core Concepts Agents
- Dependencies
- Output
- Capabilities
- Hooks
- Agent Specs
- Messages and chat history
- Direct Model Requests

- Models & Providers Overview
- OpenAI
- Anthropic
- Google
- xAI
- Bedrock
- Cerebras
- Cohere
- Groq
- Hugging Face
- Mistral
- Ollama
- OpenRouter
- Outlines

- Tools & Toolsets Function Tools
- Advanced Tool Features
- Toolsets
- Deferred Tools
- Native Tools
- Common Tools
- Third-Party Tools

- Advanced Features Image, Audio, Video & Document Input
- Thinking
- HTTP Request Retries

- Extensibility
- Multi-Agent Patterns
- Web Chat UI
- Embeddings
- Testing
- MCP Overview
- Client
- FastMCP Client
- Server

- Pydantic AI Harness Overview
- Code Mode

- Pydantic Evals Overview
- Getting Started Quick Start
- Core Concepts

- Evaluators Overview
- Built-in Evaluators
- LLM Judge
- Third-Party Integrations
- Custom Evaluators
- Report Evaluators
- Span-Based

- Online Evaluation
- How-To Guides Logfire Integration
- Dataset Management
- Dataset Serialization
- Concurrency & Performance
- Multi-Run Evaluation
- Retry Strategies
- Metrics & Attributes
- Case Lifecycle Hooks

- Simple Validation

- Pydantic Graph Overview
- Graph Builder Getting Started
- Steps
- Joins & Reducers
- Decisions
- Parallel Execution


- Integrations Debugging & Monitoring with Pydantic Logfire
- Durable Execution Overview
- Temporal
- DBOS
- Prefect
- Restate

- UI Event Streams Overview
- AG-UI
- Vercel AI

- Agent2Agent (A2A)
- Command Line Interface (CLI)

- Examples Setup
- Getting Started Pydantic Model
- Weather Agent

- Conversational Agents Chat App with FastAPI
- Bank Support

- Data & Analytics SQL Generation
- Data Analyst
- RAG

- Streaming Stream Markdown
- Stream Whales

- Complex Workflows Flight Booking
- Question Graph

- Business Applications
- UI Examples

- API Reference pydantic_ai ag_ui
- agent
- native_tools
- capabilities
- common_tools
- concurrency
- direct
- durable_exec
- embeddings
- exceptions
- ext
- format_prompt
- function_signature
- mcp
- messages
- models anthropic
- base
- bedrock
- cerebras
- cohere
- fallback
- function
- google
- xai
- groq
- huggingface
- instrumented
- mcp-sampling
- mistral
- ollama
- openai
- openrouter
- outlines
- test
- wrapper

- output
- profiles
- providers
- result
- retries
- run
- settings
- tools
- toolsets
- ui ag_ui
- base
- vercel_ai

- usage

- pydantic_evals pydantic_evals.dataset
- pydantic_evals.evaluators
- pydantic_evals.lifecycle
- pydantic_evals.online
- pydantic_evals.online_capability
- pydantic_evals.reporting
- pydantic_evals.otel
- pydantic_evals.generation

- pydantic_graph graph
- nodes
- persistence
- mermaid
- exceptions
- Graph Builder graph_builder
- graph_builder_graph
- graph_builder_graph_builder
- graph_builder_step
- graph_builder_join
- graph_builder_decision
- graph_builder_node


- fasta2a

- Project Contributing
- Upgrade Guide
- Version Policy



On this page Overview - Overview
- What is MCP?





## On this page

- Overview
- What is MCP?





# Overview





Pydantic AI supports Model Context Protocol (MCP) in multiple ways:


- Agents can connect to MCP servers and use their tools using three different methods:

Pydantic AI can act as an MCP client and connect directly to local and remote MCP servers. Learn more about MCPServer .

- Pydantic AI can use the FastMCP Client to connect to local and remote MCP servers, whether or not they’re built using FastMCP Server . Learn more about FastMCPToolset .

- Some model providers can themselves connect to remote MCP servers using a “native tool”. Learn more about MCPServerTool .



- Agents can be used within MCP servers. Learn more



## What is MCP?

The Model Context Protocol is a standardized protocol that allow AI applications (including programmatic agents like Pydantic AI, coding agents like cursor , and desktop applications like Claude Desktop ) to connect to external tools and services using a common interface.

As with other protocols, the dream of MCP is that a wide range of applications can speak to each other without the need for specific integrations.

There is a great list of MCP servers at github.com/modelcontextprotocol/servers .

Some examples of what this means:


- Pydantic AI could use a web search service implemented as an MCP server to implement a deep research agent

- Cursor could connect to the Pydantic Logfire MCP server to search logs, traces and metrics to gain context while fixing a bug

- Pydantic AI, or any other MCP client could connect to our Run Python MCP server to run arbitrary Python code in a sandboxed environment



Was this page helpful?

Thanks for your feedback!



Previous Testing Next Client













© Pydantic Services Inc. 2025 to present