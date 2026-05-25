URL: https://ai.pydantic.dev/dependencies/

Dependencies | Pydantic Docs - Skip to content Pydantic Docs

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
- Defining Dependencies
- Accessing Dependencies Asynchronous vs. Synchronous dependencies

- Full Example
- Overriding Dependencies
- Examples





## On this page

- Overview
- Defining Dependencies
- Accessing Dependencies Asynchronous vs. Synchronous dependencies

- Full Example
- Overriding Dependencies
- Examples





# Dependencies





Pydantic AI uses a dependency injection system to provide data and services to your agent’s system prompts , tools and output validators .

Matching Pydantic AI’s design philosophy, our dependency system tries to use existing best practice in Python development rather than inventing esoteric “magic”, this should make dependencies type-safe, understandable, easier to test, and ultimately easier to deploy in production.


## Defining Dependencies

Dependencies can be any python type. While in simple cases you might be able to pass a single object as a dependency (e.g. an HTTP connection), dataclasses are generally a convenient container when your dependencies included multiple objects.

Here’s an example of defining an agent that requires dependencies.

( Note: dependencies aren’t actually used in this example, see Accessing Dependencies below)

unused_dependencies.py Direct Gateway from dataclasses import dataclass import httpx from pydantic_ai import Agent @dataclass class MyDeps : api_key: str http_client: httpx.AsyncClient agent = Agent( 'openai:gpt-5.2' , deps_type=MyDeps, ) async def main (): async with httpx.AsyncClient() as client: deps = MyDeps( 'foobar' , client) result = await agent.run( 'Tell me a joke.' , deps=deps, ) print (result.output) #> Did you hear about the toothpaste scandal? They called it Colgate.




Define a dataclass to hold dependencies.



Pass the dataclass type to the deps_type argument of the Agent constructor . Note : we're passing the type here, NOT an instance, this parameter is not actually used at runtime, it's here so we can get full type checking of the agent.



When running the agent, pass an instance of the dataclass to the deps parameter.






(This example is complete, it can be run “as is” — you’ll need to add asyncio.run(main()) to run main )


## Accessing Dependencies

Dependencies are accessed through the RunContext type, this should be the first parameter of system prompt functions etc.

system_prompt_dependencies.py Direct Gateway from dataclasses import dataclass import httpx from pydantic_ai import Agent, RunContext @dataclass class MyDeps : api_key: str http_client: httpx.AsyncClient agent = Agent( 'openai:gpt-5.2' , deps_type=MyDeps, ) @agent.system_prompt async def get_system_prompt ( ctx: RunContext[MyDeps] ) -> str : response = await ctx.deps.http_client.get( 'https://example.com' , headers={ 'Authorization' : f'Bearer {ctx.deps.api_key} ' }, ) response.raise_for_status() return f'Prompt: {response.text} ' async def main (): async with httpx.AsyncClient() as client: deps = MyDeps( 'foobar' , client) result = await agent.run( 'Tell me a joke.' , deps=deps) print (result.output) #> Did you hear about the toothpaste scandal? They called it Colgate.




RunContext may optionally be passed to a system_prompt function as the only argument.



RunContext is parameterized with the type of the dependencies, if this type is incorrect, static type checkers will raise an error.



Access dependencies through the .deps attribute.



Access dependencies through the .deps attribute.






(This example is complete, it can be run “as is” — you’ll need to add asyncio.run(main()) to run main )

In addition to .deps , RunContext provides access to the running agent via .agent , which is useful when tools , hooks , or capabilities need to read agent properties like name or output_type .

Dependency fields can also be referenced in instructions and descriptions via template strings — for example, TemplateStr('Hello {{name}}') renders name from the deps object at runtime. This is especially useful in agent specs where callables aren’t available.


### Asynchronous vs. Synchronous dependencies

System prompt functions , function tools and output validators are all run in the async context of an agent run.

If these functions are not coroutines (e.g. async def ) they are called with
run_in_executor in a thread pool. It’s therefore marginally preferable
to use async methods where dependencies perform IO, although synchronous dependencies should work fine too.

run vs. run_sync and Asynchronous vs. Synchronous dependencies

Whether you use synchronous or asynchronous dependencies is completely independent of whether you use run or run_sync — run_sync is just a wrapper around run and agents are always run in an async context.


Here’s the same example as above, but with a synchronous dependency:

sync_dependencies.py Direct Gateway from dataclasses import dataclass import httpx from pydantic_ai import Agent, RunContext @dataclass class MyDeps : api_key: str http_client: httpx.Client agent = Agent( 'openai:gpt-5.2' , deps_type=MyDeps, ) @agent.system_prompt def get_system_prompt ( ctx: RunContext[MyDeps] ) -> str : response = ctx.deps.http_client.get( 'https://example.com' , headers={ 'Authorization' : f'Bearer {ctx.deps.api_key} ' } ) response.raise_for_status() return f'Prompt: {response.text} ' async def main (): deps = MyDeps( 'foobar' , httpx.Client()) result = await agent.run( 'Tell me a joke.' , deps=deps, ) print (result.output) #> Did you hear about the toothpaste scandal? They called it Colgate.




Here we use a synchronous httpx.Client instead of an asynchronous httpx.AsyncClient .



To match the synchronous dependency, the system prompt function is now a plain function, not a coroutine.






(This example is complete, it can be run “as is” — you’ll need to add asyncio.run(main()) to run main )


## Full Example

As well as system prompts, dependencies can be used in tools and output validators .

full_example.py Direct Gateway from dataclasses import dataclass import httpx from pydantic_ai import Agent, ModelRetry, RunContext @dataclass class MyDeps : api_key: str http_client: httpx.AsyncClient agent = Agent( 'openai:gpt-5.2' , deps_type=MyDeps, ) @agent.system_prompt async def get_system_prompt ( ctx: RunContext[MyDeps] ) -> str : response = await ctx.deps.http_client.get( 'https://example.com' ) response.raise_for_status() return f'Prompt: {response.text} ' @agent.tool async def get_joke_material ( ctx: RunContext[MyDeps], subject: str ) -> str : response = await ctx.deps.http_client.get( 'https://example.com#jokes' , params={ 'subject' : subject}, headers={ 'Authorization' : f'Bearer {ctx.deps.api_key} ' }, ) response.raise_for_status() return response.text @agent.output_validator async def validate_output ( ctx: RunContext[MyDeps], output: str ) -> str : response = await ctx.deps.http_client.post( 'https://example.com#validate' , headers={ 'Authorization' : f'Bearer {ctx.deps.api_key} ' }, params={ 'query' : output}, ) if response.status_code == 400 : raise ModelRetry( f'invalid response: {response.text} ' ) response.raise_for_status() return output async def main (): async with httpx.AsyncClient() as client: deps = MyDeps( 'foobar' , client) result = await agent.run( 'Tell me a joke.' , deps=deps) print (result.output) #> Did you hear about the toothpaste scandal? They called it Colgate.




To pass RunContext to a tool, use the tool decorator.



RunContext may optionally be passed to a output_validator function as the first argument.






(This example is complete, it can be run “as is” — you’ll need to add asyncio.run(main()) to run main )


## Overriding Dependencies

When testing agents, it’s useful to be able to customise dependencies.

While this can sometimes be done by calling the agent directly within unit tests, we can also override dependencies
while calling application code which in turn calls the agent.

This is done via the override method on the agent.

joke_app.py Direct Gateway from dataclasses import dataclass import httpx from pydantic_ai import Agent, RunContext @dataclass class MyDeps : api_key: str http_client: httpx.AsyncClient async def system_prompt_factory ( self ) -> str : response = await self .http_client.get( 'https://example.com' ) response.raise_for_status() return f'Prompt: {response.text} ' joke_agent = Agent( 'openai:gpt-5.2' , deps_type=MyDeps) @joke_agent.system_prompt async def get_system_prompt ( ctx: RunContext[MyDeps] ) -> str : return await ctx.deps.system_prompt_factory() async def application_code ( prompt: str ) -> str : ... ... # now deep within application code we call our agent async with httpx.AsyncClient() as client: app_deps = MyDeps( 'foobar' , client) result = await joke_agent.run(prompt, deps=app_deps) return result.output




Define a method on the dependency to make the system prompt easier to customise.



Call the system prompt factory from within the system prompt function.



Application code that calls the agent, in a real application this might be an API endpoint.



Call the agent from within the application code, in a real application this call might be deep within a call stack. Note app_deps here will NOT be used when deps are overridden.






(This example is complete, it can be run “as is”)

test_joke_app.py from joke_app import MyDeps, application_code, joke_agent class TestMyDeps ( MyDeps ): async def system_prompt_factory ( self ) -> str : return 'test prompt' async def test_application_code (): test_deps = TestMyDeps( 'test_key' , None ) with joke_agent.override(deps=test_deps): joke = await application_code( 'Tell me a joke.' ) assert joke.startswith( 'Did you hear about the toothpaste scandal?' )




Define a subclass of MyDeps in tests to customise the system prompt factory.



Create an instance of the test dependency, we don't need to pass an http_client here as it's not used.



Override the dependencies of the agent for the duration of the with block, test_deps will be used when the agent is run.



Now we can safely call our application code, the agent will use the overridden dependencies.







## Examples

The following examples demonstrate how to use dependencies in Pydantic AI:


- Weather Agent

- SQL Generation

- RAG



Was this page helpful?

Thanks for your feedback!



Previous Agents Next Output













© Pydantic Services Inc. 2025 to present