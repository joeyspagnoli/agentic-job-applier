# Source URL: https://ai.pydantic.dev/tools/

Function Tools | Pydantic Docs - Skip to content Pydantic Docs

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
- Registering via Decorator
- Registering via Agent Argument
- Tool Output
- Tool Schema
- Injecting Follow-up Messages from a Tool
- See Also





## On this page

- Overview
- Registering via Decorator
- Registering via Agent Argument
- Tool Output
- Tool Schema
- Injecting Follow-up Messages from a Tool
- See Also





# Function Tools





Function tools provide a mechanism for models to perform actions and retrieve extra information to help them generate a response.

They’re useful when you want to enable the model to take some action and use the result, when it is impractical or impossible to put all the context an agent might need into the instructions, or when you want to make agents’ behavior more deterministic or reliable by deferring some of the logic required to generate a response to another (not necessarily AI-powered) tool.

If you want a model to be able to call a function as its final action, without the result being sent back to the model, you can use an output function instead.

There are a number of ways to register tools with an agent:


- via the @agent.tool decorator — for tools that need access to the agent context

- via the @agent.tool_plain decorator — for tools that do not need access to the agent context

- via the tools keyword argument to Agent which can take either plain functions, or instances of Tool


For more advanced use cases, the toolsets feature lets you manage collections of tools (built by you or provided by an MCP server or other third party ) and register them with an agent in one go via the toolsets keyword argument to Agent . Internally, all tools and toolsets are gathered into a single combined toolset that’s made available to the model.

Function tools vs. RAG

Function tools are basically the “R” of RAG (Retrieval-Augmented Generation) — they augment what the model can do by letting it request extra information.

The main semantic difference between Pydantic AI Tools and RAG is RAG is synonymous with vector search, while Pydantic AI tools are more general-purpose. For vector search, you can use our embeddings support to generate embeddings across multiple providers.


Function Tools vs. Structured Outputs

As the name suggests, function tools use the model’s “tools” or “functions” API to let the model know what is available to call. Tools or functions are also used to define the schema(s) for structured output when using the default tool output mode , thus a model might have access to many tools, some of which call function tools while others end the run and produce a final output.



## Registering via Decorator

@agent.tool is considered the default decorator since in the majority of cases tools will need access to the agent context .

Here’s an example using both:

dice_game.py import random from pydantic_ai import Agent, RunContext agent = Agent( 'google:gemini-3-flash-preview' , deps_type= str , instructions=( "You're a dice game, you should roll the die and see if the number " "you get back matches the user's guess. If so, tell them they're a winner. " "Use the player's name in the response." ), ) @agent.tool_plain def roll_dice () -> str : """Roll a six-sided die and return the result.""" return str (random.randint( 1 , 6 )) @agent.tool def get_player_name ( ctx: RunContext[ str ] ) -> str : """Get the player's name.""" return ctx.deps dice_result = agent.run_sync( 'My guess is 4' , deps= 'Anne' ) print (dice_result.output) #> Congratulations Anne, you guessed correctly! You're a winner!




This is a pretty simple task, so we can use the fast and cheap Gemini flash model.



We pass the user's name as the dependency, to keep things simple we use just the name as a string as the dependency.



This tool doesn't need any context, it just returns a random number. You could probably use dynamic instructions in this case.



This tool needs the player's name, so it uses RunContext to access dependencies which are just the player's name in this case.



Run the agent, passing the player's name as the dependency.






(This example is complete, it can be run “as is”)

Let’s print the messages from that game to see what happened:

dice_game_messages.py from dice_game import dice_result print (dice_result.all_messages()) """ [ ModelRequest( parts=[ UserPromptPart( content='My guess is 4', timestamp=datetime.datetime(...), ) ], timestamp=datetime.datetime(...), instructions="You're a dice game, you should roll the die and see if the number you get back matches the user's guess. If so, tell them they're a winner. Use the player's name in the response.", run_id='...', conversation_id='...', ), ModelResponse( parts=[ ToolCallPart( tool_name='roll_dice', args={}, tool_call_id='pyd_ai_tool_call_id' ) ], usage=RequestUsage(input_tokens=54, output_tokens=2), model_name='gemini-3-flash-preview', timestamp=datetime.datetime(...), run_id='...', conversation_id='...', ), ModelRequest( parts=[ ToolReturnPart( tool_name='roll_dice', content='4', tool_call_id='pyd_ai_tool_call_id', timestamp=datetime.datetime(...), ) ], timestamp=datetime.datetime(...), instructions="You're a dice game, you should roll the die and see if the number you get back matches the user's guess. If so, tell them they're a winner. Use the player's name in the response.", run_id='...', conversation_id='...', ), ModelResponse( parts=[ ToolCallPart( tool_name='get_player_name', args={}, tool_call_id='pyd_ai_tool_call_id' ) ], usage=RequestUsage(input_tokens=55, output_tokens=4), model_name='gemini-3-flash-preview', timestamp=datetime.datetime(...), run_id='...', conversation_id='...', ), ModelRequest( parts=[ ToolReturnPart( tool_name='get_player_name', content='Anne', tool_call_id='pyd_ai_tool_call_id', timestamp=datetime.datetime(...), ) ], timestamp=datetime.datetime(...), instructions="You're a dice game, you should roll the die and see if the number you get back matches the user's guess. If so, tell them they're a winner. Use the player's name in the response.", run_id='...', conversation_id='...', ), ModelResponse( parts=[ TextPart( content="Congratulations Anne, you guessed correctly! You're a winner!" ) ], usage=RequestUsage(input_tokens=56, output_tokens=12), model_name='gemini-3-flash-preview', timestamp=datetime.datetime(...), run_id='...', conversation_id='...', ), ] """





We can represent this with a diagram:

sequenceDiagram
participant Agent
participant LLM

Note over Agent: Send prompts
Agent ->> LLM: System: "You're a dice game..."
User: "My guess is 4"
activate LLM
Note over LLM: LLM decides to use
a tool

LLM ->> Agent: Call tool
roll_dice()
deactivate LLM
activate Agent
Note over Agent: Rolls a six-sided die

Agent -->> LLM: ToolReturn
"4"
deactivate Agent
activate LLM
Note over LLM: LLM decides to use
another tool

LLM ->> Agent: Call tool
get_player_name()
deactivate LLM
activate Agent
Note over Agent: Retrieves player name
Agent -->> LLM: ToolReturn
"Anne"
deactivate Agent
activate LLM
Note over LLM: LLM constructs final response

LLM ->> Agent: ModelResponse
"Congratulations Anne, ..."
deactivate LLM
Note over Agent: Game session complete
LLM Agent - LLM Agent Send prompts LLM decides to use a tool Rolls a six-sided die LLM decides to use another tool Retrieves player name LLM constructs final response Game session complete System: "You're a dice game..." User: "My guess is 4" Call tool roll_dice() ToolReturn "4" Call tool get_player_name() ToolReturn "Anne" ModelResponse "Congratulations Anne, ..."


## Registering via Agent Argument



As well as using the decorators, we can register tools via the tools argument to the Agent constructor . This is useful when you want to reuse tools, and can also give more fine-grained control over the tools.

dice_game_tool_kwarg.py import random from pydantic_ai import Agent, RunContext, Tool instructions = """You're a dice game, you should roll the die and see if the number you get back matches the user's guess. If so, tell them they're a winner. Use the player's name in the response. """ def roll_dice () -> str : """Roll a six-sided die and return the result.""" return str (random.randint( 1 , 6 )) def get_player_name ( ctx: RunContext[ str ] ) -> str : """Get the player's name.""" return ctx.deps agent_a = Agent( 'google:gemini-3-flash-preview' , deps_type= str , tools=[roll_dice, get_player_name], instructions=instructions, ) agent_b = Agent( 'google:gemini-3-flash-preview' , deps_type= str , tools=[ Tool(roll_dice, takes_ctx= False ), Tool(get_player_name, takes_ctx= True ), ], instructions=instructions, ) dice_result = {} dice_result[ 'a' ] = agent_a.run_sync( 'My guess is 6' , deps= 'Yashar' ) dice_result[ 'b' ] = agent_b.run_sync( 'My guess is 4' , deps= 'Anne' ) print (dice_result[ 'a' ].output) #> Tough luck, Yashar, you rolled a 4. Better luck next time. print (dice_result[ 'b' ].output) #> Congratulations Anne, you guessed correctly! You're a winner!




The simplest way to register tools via the Agent constructor is to pass a list of functions, the function signature is inspected to determine if the tool takes RunContext .



agent_a and agent_b are identical — but we can use Tool to reuse tool definitions and give more fine-grained control over how tools are defined, e.g. setting their name or description, or using a custom prepare method.






(This example is complete, it can be run “as is”)


## Tool Output



Tools can return anything that Pydantic can serialize to JSON. For advanced output options including multi-modal content and metadata, see Advanced Tool Features .


## Tool Schema



Function parameters are extracted from the function signature, and all parameters except RunContext are used to build the schema for that tool call.

Even better, Pydantic AI extracts the docstring from functions and (thanks to griffe ) extracts parameter descriptions from the docstring and adds them to the schema.

Griffe supports extracting parameter descriptions from google , numpy , and sphinx style docstrings. Pydantic AI will infer the format to use based on the docstring, but you can explicitly set it using docstring_format . You can also enforce parameter requirements by setting require_parameter_descriptions=True . This will raise a UserError if a parameter description is missing.

To demonstrate a tool’s schema, here we use FunctionModel to print the schema a model would receive:

tool_schema.py from pydantic_ai import Agent, ModelMessage, ModelResponse, TextPart from pydantic_ai.models.function import AgentInfo, FunctionModel agent = Agent() @agent.tool_plain( docstring_format= 'google' , require_parameter_descriptions= True ) def foobar ( a: int , b: str , c: dict [ str , list [ float ]] ) -> str : """Get me foobar. Args: a: apple pie b: banana cake c: carrot smoothie """ return f' {a} {b} {c} ' def print_schema ( messages: list [ModelMessage], info: AgentInfo ) -> ModelResponse: tool = info.function_tools[ 0 ] print (tool.description) #> Get me foobar. print (tool.parameters_json_schema) """ { 'additionalProperties': False, 'properties': { 'a': {'description': 'apple pie', 'type': 'integer'}, 'b': {'description': 'banana cake', 'type': 'string'}, 'c': { 'additionalProperties': {'items': {'type': 'number'}, 'type': 'array'}, 'description': 'carrot smoothie', 'type': 'object', }, }, 'required': ['a', 'b', 'c'], 'type': 'object', } """ return ModelResponse(parts=[TextPart( 'foobar' )]) agent.run_sync( 'hello' , model=FunctionModel(print_schema))





(This example is complete, it can be run “as is”)

If a tool has a single parameter that can be represented as an object in JSON schema (e.g. dataclass, TypedDict, pydantic model), the schema for the tool is simplified to be just that object.

Here’s an example where we use TestModel.last_model_request_parameters to inspect the tool schema that would be passed to the model.

single_parameter_tool.py from pydantic import BaseModel from pydantic_ai import Agent from pydantic_ai.models.test import TestModel agent = Agent() class Foobar ( BaseModel ): """This is a Foobar""" x: int y: str z: float = 3.14 @agent.tool_plain def foobar ( f: Foobar ) -> str : return str (f) test_model = TestModel() result = agent.run_sync( 'hello' , model=test_model) print (result.output) #> {"foobar":"x=0 y='a' z=3.14"} print (test_model.last_model_request_parameters.function_tools) """ [ ToolDefinition( name='foobar', parameters_json_schema={ 'properties': { 'x': {'type': 'integer'}, 'y': {'type': 'string'}, 'z': {'default': 3.14, 'type': 'number'}, }, 'required': ['x', 'y'], 'title': 'Foobar', 'type': 'object', }, description='This is a Foobar', ) ] """





(This example is complete, it can be run “as is”)

Debugging Tool Calls

Understanding tool behavior is crucial for agent development. By instrumenting your agent with Logfire , you can see:


What arguments were passed to each tool

- What each tool returned

- How long each tool took to execute

- Any errors that occurred

This visibility helps you understand why an agent made specific decisions and identify issues in tool implementations.



## Injecting Follow-up Messages from a Tool

A tool can push extra messages into the conversation via
RunContext.enqueue — useful when a tool wants
to add follow-up context, redirect the agent’s plan, or surface an event the model
should react to. See Injecting messages mid-run
for the full pattern.


## See Also

For more tool features and integrations, see:


- Advanced Tool Features - Custom schemas, dynamic tools, tool execution and retries

- Toolsets - Managing collections of tools

- Native Tools - Native tools provided by LLM providers

- Common Tools - Ready-to-use tool implementations

- Third-Party Tools - Integrations with MCP, LangChain, ACI.dev and other tool libraries

- Deferred Tools - Tools requiring approval or external execution



Was this page helpful?

Thanks for your feedback!



Previous Outlines Next Advanced Tool Features













© Pydantic Services Inc. 2025 to present