# Source URL: https://ai.pydantic.dev/

Pydantic AI | Pydantic Docs - Skip to content Pydantic Docs

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
- Why use Pydantic AI
- Hello World Example
- Tools & Dependency Injection Example
- Instrumentation with Pydantic Logfire
- llms.txt
- Next Steps





## On this page

- Overview
- Why use Pydantic AI
- Hello World Example
- Tools & Dependency Injection Example
- Instrumentation with Pydantic Logfire
- llms.txt
- Next Steps





# Pydantic AI









GenAI Agent Framework, the Pydantic way

Pydantic AI is a Python agent framework designed to help you
quickly, confidently, and painlessly build production grade applications and workflows with Generative AI.

FastAPI revolutionized web development by offering an innovative and ergonomic design, built on the foundation of Pydantic Validation and modern Python features like type hints.

Yet despite virtually every Python agent framework and LLM library using Pydantic Validation, when we began to use LLMs in Pydantic Logfire , we couldn’t find anything that gave us the same feeling.

We built Pydantic AI with one simple aim: to bring that FastAPI feeling to GenAI app and agent development.


## Why use Pydantic AI

- Built by the Pydantic Team :
Pydantic Validation is the validation layer of the OpenAI SDK, the Google ADK, the Anthropic SDK, LangChain, LlamaIndex, AutoGPT, Transformers, CrewAI, Instructor and many more. Why use the derivative when you can go straight to the source? 😃

- Model-agnostic :
Supports virtually every model and provider: OpenAI, Anthropic, Gemini, DeepSeek, Grok, Cohere, Mistral, and Perplexity; Azure AI Foundry, Amazon Bedrock, Google Cloud, Ollama, LiteLLM, Groq, OpenRouter, Together AI, Fireworks AI, Cerebras, Hugging Face, GitHub, Heroku, Vercel, Nebius, OVHcloud, Alibaba Cloud, and SambaNova. If your favorite model or provider is not listed, you can easily implement a custom model .

- Seamless Observability :
Tightly integrates with Pydantic Logfire , our general-purpose OpenTelemetry observability platform, for real-time debugging, evals-based performance monitoring, and behavior, tracing, and cost tracking. If you already have an observability platform that supports OTel, you can use that too .

- Fully Type-safe :
Designed to give your IDE or AI coding agent as much context as possible for auto-completion and type checking , moving entire classes of errors from runtime to write-time for a bit of that Rust “if it compiles, it works” feel.

- Powerful Evals :
Enables you to systematically test and evaluate the performance and accuracy of the agentic systems you build, and monitor the performance over time in Pydantic Logfire.

- Extensible by Design :
Build agents from composable capabilities that bundle tools, hooks, instructions, and model settings into reusable units. Use built-in capabilities for web search , thinking , and MCP , pick from the Pydantic AI Harness capability library, build your own, or install third-party capability packages . Define agents entirely in YAML/JSON — no code required.

- MCP, A2A, and UI :
Integrates the Model Context Protocol , Agent2Agent , and various UI event stream standards to give your agent access to external tools and data, let it interoperate with other agents, and build interactive applications with streaming event-based communication.

- Human-in-the-Loop Tool Approval :
Easily lets you flag that certain tool calls require approval before they can proceed, possibly depending on tool call arguments, conversation history, or user preferences.

- Durable Execution :
Enables you to build durable agents that can preserve their progress across transient API failures and application errors or restarts, and handle long-running, asynchronous, and human-in-the-loop workflows with production-grade reliability.

- Streamed Outputs :
Provides the ability to stream structured output continuously, with immediate validation, ensuring real time access to generated data.

- Graph Support :
Provides a powerful way to define graphs using type hints, for use in complex applications where standard control flow can degrade to spaghetti code.


Realistically though, no list is going to be as convincing as giving it a try and seeing how it makes you feel!

Sign up for our newsletter, The Pydantic Stack , with updates & tutorials on Pydantic AI, Logfire, and Pydantic:

Subscribe

## Hello World Example

Here’s a minimal example of Pydantic AI:

hello_world.py Direct Gateway from pydantic_ai import Agent agent = Agent( 'anthropic:claude-sonnet-4-6' , instructions= 'Be concise, reply with one sentence.' , ) result = agent.run_sync( 'Where does "hello world" come from?' ) print (result.output) """ The first known use of "hello, world" was in a 1974 textbook about the C programming language. """




We configure the agent to use Anthropic's Claude Sonnet 4.6 model, but you can also set the model when running the agent.



Register static instructions using a keyword argument to the agent.



Run the agent synchronously, starting a conversation with the LLM.






(This example is complete, it can be run “as is”, assuming you’ve installed the pydantic_ai package )

The exchange will be very short: Pydantic AI will send the instructions and the user prompt to the LLM, and the model will return a text response.

Not very interesting yet, but we can easily add tools , dynamic instructions , structured outputs , or composable capabilities to build more powerful agents.

Here’s the same agent with thinking and web search capabilities:

hello_world_capabilities.py Direct Gateway from pydantic_ai import Agent from pydantic_ai.capabilities import Thinking, WebSearch agent = Agent( 'anthropic:claude-sonnet-4-6' , instructions= 'Be concise, reply with one sentence.' , capabilities=[Thinking(), WebSearch(local= 'duckduckgo' )], ) result = agent.run_sync( 'What was the mass of the largest meteorite found this year?' ) print (result.output) """ The largest meteorite recovered this year weighed approximately 7.6 kg, found in the Sahara Desert in January. """






## Tools & Dependency Injection Example



Here is a concise example using Pydantic AI to build a support agent for a bank:

bank_support.py Direct Gateway from dataclasses import dataclass from pydantic import BaseModel, Field from pydantic_ai import Agent, RunContext from bank_database import DatabaseConn @dataclass class SupportDependencies : customer_id: int db: DatabaseConn class SupportOutput ( BaseModel ): support_advice: str = Field(description= 'Advice returned to the customer' ) block_card: bool = Field(description= "Whether to block the customer's card" ) risk: int = Field(description= 'Risk level of query' , ge= 0 , le= 10 ) support_agent = Agent( 'openai:gpt-5.2' , deps_type=SupportDependencies, output_type=SupportOutput, instructions=( 'You are a support agent in our bank, give the ' 'customer support and judge the risk level of their query.' ), ) @support_agent.instructions async def add_customer_name ( ctx: RunContext[SupportDependencies] ) -> str : customer_name = await ctx.deps.db.customer_name( id =ctx.deps.customer_id) return f"The customer's name is {customer_name!r} " @support_agent.tool async def customer_balance ( ctx: RunContext[SupportDependencies], include_pending: bool ) -> float : """Returns the customer's current account balance.""" return await ctx.deps.db.customer_balance( id =ctx.deps.customer_id, include_pending=include_pending, ) ... async def main (): deps = SupportDependencies(customer_id= 123 , db=DatabaseConn()) result = await support_agent.run( 'What is my balance?' , deps=deps) print (result.output) """ support_advice='Hello John, your current account balance, including pending transactions, is $123.45.' block_card=False risk=1 """ result = await support_agent.run( 'I just lost my card!' , deps=deps) print (result.output) """ support_advice="I'm sorry to hear that, John. We are temporarily blocking your card to prevent unauthorized transactions." block_card=True risk=8 """




This agent will act as first-tier support in a bank. Agents are generic in the type of dependencies they accept and the type of output they return. In this case, the support agent has type Agent[SupportDependencies, SupportOutput] .



Here we configure the agent to use OpenAI's GPT-5 model , you can also set the model when running the agent.



The SupportDependencies dataclass is used to pass data, connections, and logic into the model that will be needed when running instructions and tool functions. Pydantic AI's system of dependency injection provides a type-safe way to customise the behavior of your agents, and can be especially useful when running unit tests and evals.



Static instructions can be registered with the instructions keyword argument to the agent.



Dynamic instructions can be registered with the @agent.instructions decorator, and can make use of dependency injection. Dependencies are carried via the RunContext argument, which is parameterized with the deps_type from above. If the type annotation here is wrong, static type checkers will catch it.



The @agent.tool decorator let you register functions which the LLM may call while responding to a user. Again, dependencies are carried via RunContext , any other arguments become the tool schema passed to the LLM. Pydantic is used to validate these arguments, and errors are passed back to the LLM so it can retry.



The docstring of a tool is also passed to the LLM as the description of the tool. Parameter descriptions are extracted from the docstring and added to the parameter schema sent to the LLM.



Run the agent asynchronously, conducting a conversation with the LLM until a final response is reached. Even in this fairly simple case, the agent will exchange multiple messages with the LLM as tools are called to retrieve an output.



The response from the agent will be guaranteed to be a SupportOutput . If validation fails reflection , the agent is prompted to try again.



The output will be validated with Pydantic to guarantee it is a SupportOutput , since the agent is generic, it'll also be typed as a SupportOutput to aid with static type checking.



In a real use case, you'd add more tools and longer instructions to the agent to extend the context it's equipped with and support it can provide.



This is a simple sketch of a database connection, used to keep the example short and readable. In reality, you'd be connecting to an external database (e.g. PostgreSQL) to get information about customers.



This Pydantic model is used to constrain the structured data returned by the agent. From this simple definition, Pydantic builds the JSON Schema that tells the LLM how to return the data, and performs validation to guarantee the data is correct at the end of the run.






Complete bank_support.py example

The code included here is incomplete for the sake of brevity (the definition of DatabaseConn is missing); you can find the complete bank_support.py example here .



## Instrumentation with Pydantic Logfire

Even a simple agent with just a handful of tools can result in a lot of back-and-forth with the LLM, making it nearly impossible to be confident of what’s going on just from reading the code.
To understand the flow of the above runs, we can watch the agent in action using Pydantic Logfire.

To do this, we need to set up Logfire , and add the following to our code:

bank_support_with_logfire.py Direct Gateway ... from pydantic_ai import Agent, RunContext from bank_database import DatabaseConn import logfire logfire.configure() logfire.instrument_pydantic_ai() logfire.instrument_sqlite3() ... support_agent = Agent( 'openai:gpt-5.2' , deps_type=SupportDependencies, output_type=SupportOutput, instructions=( 'You are a support agent in our bank, give the ' 'customer support and judge the risk level of their query.' ), )




Configure the Logfire SDK, this will fail if project is not set up.



This will instrument all Pydantic AI agents used from here on out. To instrument only a specific agent, add an Instrumentation entry to the agent's capabilities=[...] .



In our demo, DatabaseConn uses sqlite3 to connect to a PostgreSQL database, so logfire.instrument_sqlite3()
is used to log the database queries.






That’s enough to get the following view of your agent in action:

Logfire instrumentation for the bank agent —
View in Logfire - See Monitoring and Performance to learn more.


## llms.txt



The Pydantic AI documentation is available in the llms.txt format.
This format is defined in Markdown and suited for LLMs and AI coding assistants and agents.

Two formats are available:


llms.txt : a file containing a brief description
of the project, along with links to the different sections of the documentation. The structure
of this file is described in details here .

- llms-full.txt : Similar to the llms.txt file,
but every link content is included. Note that this file may be too large for some LLMs.


As of today, these files are not automatically leveraged by IDEs or coding agents, but they will use it if you provide a link or the full text.


## Next Steps

To try Pydantic AI for yourself, install it and follow the instructions in the examples .

Read the docs to learn more about building applications with Pydantic AI.

Read the API Reference to understand Pydantic AI’s interface.

Join Slack or file an issue on GitHub if you have any questions.



Was this page helpful?

Thanks for your feedback!



Previous Visual studio code Next Installation













© Pydantic Services Inc. 2025 to present