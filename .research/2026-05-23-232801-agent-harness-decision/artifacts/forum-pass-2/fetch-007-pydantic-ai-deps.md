# Source URL: https://ai.pydantic.dev/models/

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
- OpenAI-compatible Providers
- Models and Providers
- HTTP Client Lifecycle
- Custom Models
- HTTP Request Concurrency Shared Concurrency Limits

- Fallback Model Per-Model Settings
- Exception Handling
- Response-Based Fallback Finish Reason Example
- Native Tool Failure Example
- Combining Handlers

- Exception Handling in Middleware and Decorators






## On this page

- Overview
- OpenAI-compatible Providers
- Models and Providers
- HTTP Client Lifecycle
- Custom Models
- HTTP Request Concurrency Shared Concurrency Limits

- Fallback Model Per-Model Settings
- Exception Handling
- Response-Based Fallback Finish Reason Example
- Native Tool Failure Example
- Combining Handlers

- Exception Handling in Middleware and Decorators






# Overview





Pydantic AI is model-agnostic and has built-in support for multiple model providers:


- OpenAI

- Anthropic

- Gemini (via two different APIs: Gemini API and Google Cloud, formerly known as Vertex AI)

- xAI

- Bedrock

- Cerebras

- Cohere

- Groq

- Hugging Face

- Mistral

- OpenRouter

- Outlines (deprecated, will be removed in v2)



## OpenAI-compatible Providers

In addition, many providers are compatible with the OpenAI API, and can be used with OpenAIChatModel in Pydantic AI:


- Alibaba Cloud Model Studio (DashScope)

- Azure AI Foundry

- DeepSeek

- Fireworks AI

- GitHub Models

- Heroku

- LiteLLM

- Nebius AI Studio

- Ollama

- OVHcloud AI Endpoints

- Perplexity

- SambaNova

- Together AI

- Vercel AI Gateway


Pydantic AI also comes with TestModel and FunctionModel
for testing and development.

To use each model provider, you need to configure your local environment and make sure you have the right
packages installed. If you try to use the model without having done so, you’ll be told what to install.


## Models and Providers

Pydantic AI uses a few key terms to describe how it interacts with different LLMs:


- Model : This refers to the Pydantic AI class used to make requests following a specific LLM API
(generally by wrapping a vendor-provided SDK, like the openai python SDK). These classes implement a
vendor-SDK-agnostic API, ensuring a single Pydantic AI agent is portable to different LLM vendors without
any other code changes just by swapping out the Model it uses. Model classes are named
roughly in the format Model , for example, we have OpenAIChatModel , AnthropicModel , GoogleModel ,
etc. When using a Model class, you specify the actual LLM model name (e.g., gpt-5 ,
claude-sonnet-4-5 , gemini-3-flash-preview ) as a parameter.

- Provider : This refers to provider-specific classes which handle the authentication and connections
to an LLM vendor. Passing a non-default Provider as a parameter to a Model is how you can ensure
that your agent will make requests to a specific endpoint, or make use of a specific approach to
authentication (e.g., you can use Azure auth with the OpenAIChatModel by way of the AzureProvider ).
In particular, this is how you can make use of an AI gateway, or an LLM vendor that offers API compatibility
with the vendor SDK used by an existing Model (such as OpenAIChatModel ).

- Profile : This refers to a description of how requests to a specific model or family of models need to be
constructed to get the best results, independent of the model and provider classes used.
For example, different models have different restrictions on the JSON schemas that can be used for tools,
and the same schema transformer needs to be used for Gemini models whether you’re using GoogleModel
with model name gemini-3-pro-preview , or OpenAIChatModel with OpenRouterProvider and model name google/gemini-3-pro-preview .


When you instantiate an Agent with just a name formatted as : , e.g. openai:gpt-5.2 or openrouter:google/gemini-3-pro-preview ,
Pydantic AI will automatically select the appropriate model class, provider, and profile.
If you want to use a different provider or profile, you can instantiate a model class directly and pass in provider and/or profile arguments.


## HTTP Client Lifecycle

When a Provider creates its own HTTP client (i.e. you don’t pass a custom http_client ), it owns that client’s lifecycle. Using the Agent as an async context manager ensures the HTTP client is closed cleanly on exit:

from pydantic_ai import Agent agent = Agent( 'openai:gpt-5.2' ) async def main (): async with agent: result = await agent.run( 'What is the capital of France?' ) print (result.output) #> The capital of France is Paris.




Direct Gateway
You can also use a Model or Provider directly as an async context manager for the same effect.

If you provide your own http_client , you are responsible for closing it yourself.


## Custom Models

Note

If a model API is compatible with the OpenAI API, you do not need a custom model class and can provide your own custom provider instead.


To implement support for a model API that’s not already supported, you will need to subclass the Model abstract base class.
For streaming, you’ll also need to implement the StreamedResponse abstract base class.

The best place to start is to review the source code for existing implementations, e.g. OpenAIChatModel .

For details on when we’ll accept contributions adding new models to Pydantic AI, see the contributing guidelines .


## HTTP Request Concurrency

You can limit the number of concurrent HTTP requests to a model using the
ConcurrencyLimitedModel wrapper.
This is useful for respecting rate limits or managing resource usage when running many agents in parallel.

model_concurrency.py import asyncio from pydantic_ai import Agent, ConcurrencyLimitedModel # Wrap a model with concurrency limiting model = ConcurrencyLimitedModel( 'openai:gpt-4o' , limiter= 5 ) # Multiple agents can share this rate-limited model agent = Agent(model) async def main (): # These will be rate-limited to 5 concurrent HTTP requests results = await asyncio.gather( *[agent.run( f'Question {i} ' ) for i in range ( 20 )] ) print ( len (results)) #> 20





The limiter parameter accepts:


- An integer for simple limiting (e.g., limiter=5 )

- A ConcurrencyLimit for advanced configuration with backpressure control

- A ConcurrencyLimiter for sharing limits across multiple models



### Shared Concurrency Limits

To share a concurrency limit across multiple models (e.g., different models from the same provider),
you can create a ConcurrencyLimiter and pass it to
multiple ConcurrencyLimitedModel instances:

shared_concurrency.py import asyncio from pydantic_ai import Agent, ConcurrencyLimitedModel, ConcurrencyLimiter # Create a shared limiter with a descriptive name shared_limiter = ConcurrencyLimiter(max_running= 10 , name= 'openai-pool' ) # Both models share the same concurrency limit model1 = ConcurrencyLimitedModel( 'openai:gpt-4o' , limiter=shared_limiter) model2 = ConcurrencyLimitedModel( 'openai:gpt-4o-mini' , limiter=shared_limiter) agent1 = Agent(model1) agent2 = Agent(model2) async def main (): # Total concurrent requests across both agents limited to 10 results = await asyncio.gather( *[agent1.run( f'Question {i} ' ) for i in range ( 10 )], *[agent2.run( f'Question {i} ' ) for i in range ( 10 )], ) print ( len (results)) #> 20





When instrumentation is enabled, requests waiting for a concurrency slot appear as spans with
attributes showing the queue depth and configured limits. The name parameter on
ConcurrencyLimiter helps identify shared limiters in traces.


## Fallback Model

You can use FallbackModel to attempt multiple models
in sequence until one succeeds. Pydantic AI can switch to the next model when the current model
raises an exception (like a 4xx/5xx API error) or when the response content indicates a semantic
failure (like a truncated response or a failed native tool call).

By default, fallback triggers on ModelAPIError (4xx/5xx API errors),
so you don’t need to configure anything for the most common use case.

This behavior is controlled by the fallback_on parameter (see
FallbackModel ), which accepts exception types,
exception handlers, and response handlers — all of which can be sync or async.

Note

The provider SDKs on which Models are based (like OpenAI, Anthropic, etc.) often have built-in retry logic that can delay the FallbackModel from activating.

When using FallbackModel , it’s recommended to disable provider SDK retries to ensure immediate fallback, for example by setting max_retries=0 on a custom OpenAI client .


In the following example, the agent first makes a request to the OpenAI model (which fails due to an invalid API key),
and then falls back to the Anthropic model.

fallback_model.py from pydantic_ai import Agent from pydantic_ai.models.anthropic import AnthropicModel from pydantic_ai.models.fallback import FallbackModel from pydantic_ai.models.openai import OpenAIChatModel openai_model = OpenAIChatModel( 'gpt-5.2' ) anthropic_model = AnthropicModel( 'claude-sonnet-4-5' ) fallback_model = FallbackModel(openai_model, anthropic_model) agent = Agent(fallback_model) response = agent.run_sync( 'What is the capital of France?' ) print (response.data) #> Paris print (response.all_messages()) """ [ ModelRequest( parts=[ UserPromptPart( content='What is the capital of France?', timestamp=datetime.datetime(...), part_kind='user-prompt', ) ], kind='request', ), ModelResponse( parts=[TextPart(content='Paris', part_kind='text')], model_name='claude-sonnet-4-5', timestamp=datetime.datetime(...), kind='response', provider_response_id=None, ), ] """





The ModelResponse message above indicates in the model_name field that the output was returned by the Anthropic model, which is the second model specified in the FallbackModel .

Note

Each model’s options should be configured individually. For example, base_url , api_key , and custom clients should be set on each model itself, not on the FallbackModel .



### Per-Model Settings

You can configure different ModelSettings for each model in a fallback chain by passing the settings parameter when creating each model. This is particularly useful when different providers have different optimal configurations:

fallback_model_per_settings.py from pydantic_ai import Agent, ModelSettings from pydantic_ai.models.anthropic import AnthropicModel from pydantic_ai.models.fallback import FallbackModel from pydantic_ai.models.openai import OpenAIChatModel # Configure each model with provider-specific optimal settings openai_model = OpenAIChatModel( 'gpt-5.2' , settings=ModelSettings(temperature= 0.7 , max_tokens= 1000 ) # Higher creativity for OpenAI ) anthropic_model = AnthropicModel( 'claude-sonnet-4-5' , settings=ModelSettings(temperature= 0.2 , max_tokens= 1000 ) # Lower temperature for consistency ) fallback_model = FallbackModel(openai_model, anthropic_model) agent = Agent(fallback_model) result = agent.run_sync( 'Write a creative story about space exploration' ) print (result.output) """ In the year 2157, Captain Maya Chen piloted her spacecraft through the vast expanse of the Andromeda Galaxy. As she discovered a planet with crystalline mountains that sang in harmony with the cosmic winds, she realized that space exploration was not just about finding new worlds, but about finding new ways to understand the universe and our place within it. """





In this example, if the OpenAI model fails, the agent will automatically fall back to the Anthropic model with its own configured settings. The FallbackModel itself doesn’t have settings - it uses the individual settings of whichever model successfully handles the request.


### Exception Handling

The next example demonstrates the exception-handling capabilities of FallbackModel .
If all models fail, a FallbackExceptionGroup is raised, which
contains all the exceptions encountered during the run execution.

- Python >=3.11
- Python

fallback_model_failure.py from pydantic_ai import Agent, ModelAPIError from pydantic_ai.models.anthropic import AnthropicModel from pydantic_ai.models.fallback import FallbackModel from pydantic_ai.models.openai import OpenAIChatModel openai_model = OpenAIChatModel( 'gpt-5.2' ) anthropic_model = AnthropicModel( 'claude-sonnet-4-5' ) fallback_model = FallbackModel(openai_model, anthropic_model) agent = Agent(fallback_model) try : response = agent.run_sync( 'What is the capital of France?' ) except * ModelAPIError as exc_group: for exc in exc_group.exceptions: print (exc)






Since except* is only supported
in Python 3.11+, we use the exceptiongroup backport
package for earlier Python versions:

fallback_model_failure.py from exceptiongroup import catch from pydantic_ai import Agent, ModelAPIError from pydantic_ai.models.anthropic import AnthropicModel from pydantic_ai.models.fallback import FallbackModel from pydantic_ai.models.openai import OpenAIChatModel def model_status_error_handler ( exc_group: BaseExceptionGroup ) -> None : for exc in exc_group.exceptions: print (exc) openai_model = OpenAIChatModel( 'gpt-5.2' ) anthropic_model = AnthropicModel( 'claude-sonnet-4-5' ) fallback_model = FallbackModel(openai_model, anthropic_model) agent = Agent(fallback_model) with catch({ModelAPIError: model_status_error_handler}): response = agent.run_sync( 'What is the capital of France?' )







By default, the FallbackModel only moves on to the next model if the current model raises a
ModelAPIError , which includes
ModelHTTPError . You can customize this behavior by
passing a custom fallback_on argument to the FallbackModel constructor.

Note

Validation errors (from structured output or tool parameters ) do not trigger fallback. These errors use the retry mechanism instead, which re-prompts the same model to try again. This is intentional: validation errors stem from the non-deterministic nature of LLMs and may succeed on retry, whereas API errors (4xx/5xx) generally indicate issues that won’t resolve by retrying the same request.



### Response-Based Fallback

In addition to exception-based fallback, you can also trigger fallback based on the content of a model’s response. This is useful when a model returns a successful HTTP response (no exception), but the response content indicates a semantic failure — for example, an unexpected finish reason or a native tool reporting failure.

Non-streaming only

Response-based fallback currently only works with non-streaming requests ( agent.run() and agent.run_sync() ).
For streaming requests ( agent.run_stream() ), only exception-based fallback is supported.


The fallback_on parameter accepts:


- A tuple of exception types: (ModelAPIError, ModelHTTPError)

- An exception handler (sync or async): lambda exc: isinstance(exc, MyError)

- A response handler (sync or async): def check(r: ModelResponse) -> bool

- A list mixing all of the above: [ModelAPIError, exc_handler, response_handler]


Handler type is auto-detected by inspecting type hints on the first parameter. If the first parameter is hinted as ModelResponse , it’s a response handler. Otherwise (including untyped handlers and lambdas), it’s an exception handler.


#### Finish Reason Example

A simple use case is checking the model’s finish reason — for example, falling back if the response was truncated due to length limits:

fallback_on_finish_reason.py from pydantic_ai import Agent from pydantic_ai.messages import FinishReason, ModelResponse from pydantic_ai.models.fallback import FallbackModel def bad_finish_reason ( response: ModelResponse ) -> bool : """Fallback if the model stopped due to length limit, content filter, or error.""" reason: FinishReason | None = response.finish_reason # Trigger fallback for problematic finish reasons return reason in ( 'length' , 'content_filter' , 'error' ) fallback_model = FallbackModel( 'openai:gpt-5.2' , 'anthropic:claude-sonnet-4-5' , fallback_on=bad_finish_reason, ) agent = Agent(fallback_model) result = agent.run_sync( 'What is the capital of France?' ) print (result.output) #> The capital of France is Paris.





Solo response handlers replace default exception fallback

When you pass a single response handler as fallback_on (as above), it replaces the default (ModelAPIError,) exception fallback entirely. This means API errors (4xx/5xx) will propagate as exceptions instead of triggering fallback to the next model.

To keep exception-based fallback alongside a response handler, pass them together as a list — see the mixed example below .


Note

Note that Pydantic AI already handles some finish reasons automatically in the agent loop :
responses with a 'length' or 'content_filter' finish reason raise exceptions (which FallbackModel
catches by default), and empty responses are retried. A response handler is useful for custom
checks beyond these built-in behaviors.



#### Native Tool Failure Example

A more complex use case is when using native tools like web search or URL fetching. For example, Google’s WebFetchTool may return a successful response with a status indicating the URL fetch failed:

fallback_on_native_tool.py from pydantic_ai import Agent from pydantic_ai.messages import ModelResponse from pydantic_ai.models.anthropic import AnthropicModel from pydantic_ai.models.fallback import FallbackModel from pydantic_ai.models.google import GoogleModel def web_fetch_failed ( response: ModelResponse ) -> bool : """Check if a web_fetch native tool failed to retrieve content.""" for call, result in response.native_tool_calls: if call.tool_name != 'web_fetch' : continue if not isinstance (result.content, list ): continue for item in result.content: if isinstance (item, dict ): status = item.get( 'url_retrieval_status' , '' ) if status and status != 'URL_RETRIEVAL_STATUS_SUCCESS' : return True return False google_model = GoogleModel( 'gemini-2.5-flash' ) anthropic_model = AnthropicModel( 'claude-sonnet-4-5' ) # Auto-detected as response handler via type hint fallback_model = FallbackModel( google_model, anthropic_model, fallback_on=web_fetch_failed, ) agent = Agent(fallback_model) # If Google's web_fetch fails, automatically falls back to Anthropic result = agent.run_sync( 'Summarize https://ai.pydantic.dev' ) print (result.output) """ Pydantic AI is a Python agent framework for building production-grade LLM applications. """





Response handlers receive the ModelResponse returned by the model and should return True to trigger fallback to the next model, or False to accept the response.


#### Combining Handlers

You can combine exception types, exception handlers, and response handlers in a single list:

fallback_on_mixed.py from pydantic_ai.exceptions import ModelAPIError from pydantic_ai.models.fallback import FallbackModel from fallback_on_native_tool import anthropic_model, google_model, web_fetch_failed fallback_model = FallbackModel( google_model, anthropic_model, fallback_on=[ ModelAPIError, # Exception type lambda exc: 'rate limit' in str (exc).lower(), # Exception handler (untyped lambda) web_fetch_failed, # Response handler (auto-detected via type hint) ], )






### Exception Handling in Middleware and Decorators



When using FallbackModel , it’s important to understand that FallbackExceptionGroup
inherits from Python’s ExceptionGroup . This means
that existing exception handling code that catches specific exceptions (like ModelAPIError ) won’t automatically catch
the individual exceptions wrapped inside the group.

For example, if you have middleware or a decorator that catches ModelAPIError :

middleware_without_fallback.py from collections.abc import Callable from functools import wraps from typing import TypeVar from pydantic_ai import ModelAPIError T = TypeVar( 'T' ) # This handler will NOT catch ModelAPIError when using FallbackModel! def handle_api_errors ( func: Callable [..., T] ) -> Callable [..., T]: @wraps( func ) def wrapper ( *args, **kwargs ) -> T: try : return func(*args, **kwargs) except ModelAPIError as e: # Won't catch FallbackExceptionGroup print ( f'API error: {e} ' ) raise return wrapper





This decorator will miss ModelAPIError exceptions when using FallbackModel , because they’re wrapped in a
FallbackExceptionGroup containing one exception per failed model, in the order the models were tried.

To handle both cases, you can use Python 3.11+ except* syntax, which catches matching exceptions from
exception groups as well as bare exceptions. Note that except* always delivers the caught exceptions as an
ExceptionGroup (even if the original was a bare exception), so re-raising will propagate an ExceptionGroup
rather than the original exception type:

- Python >=3.11
- Python

middleware_with_fallback.py from collections.abc import Callable from functools import wraps from typing import TypeVar from pydantic_ai import ModelAPIError T = TypeVar( 'T' ) def handle_api_errors ( func: Callable [..., T] ) -> Callable [..., T]: @wraps( func ) def wrapper ( *args, **kwargs ) -> T: try : return func(*args, **kwargs) except * ModelAPIError as exc_group: for exc in exc_group.exceptions: print ( f'API error: {exc} ' ) raise return wrapper






middleware_with_fallback.py from collections.abc import Callable from functools import wraps from typing import TypeVar from pydantic_ai import FallbackExceptionGroup, ModelAPIError T = TypeVar( 'T' ) def handle_api_errors ( func: Callable [..., T] ) -> Callable [..., T]: @wraps( func ) def wrapper ( *args, **kwargs ) -> T: try : return func(*args, **kwargs) except FallbackExceptionGroup as exc_group: for exc in exc_group.exceptions: if isinstance (exc, ModelAPIError): print ( f'API error from fallback: {exc} ' ) raise except ModelAPIError as e: print ( f'API error: {e} ' ) raise return wrapper







You can also catch FallbackExceptionGroup directly if you want to handle it specifically:

catch_fallback_exception_group.py Direct Gateway from pydantic_ai import Agent, FallbackExceptionGroup from pydantic_ai.models.fallback import FallbackModel agent = Agent(FallbackModel( 'openai:gpt-5-mini' , 'anthropic:claude-sonnet-4-6' )) try : response = agent.run_sync( 'What is the capital of France?' ) except FallbackExceptionGroup as exc_group: print ( f'All { len (exc_group.exceptions)} models failed:' ) for exc in exc_group.exceptions: print ( f' - {exc} ' )






Was this page helpful?

Thanks for your feedback!



Previous Direct Model Requests Next OpenAI













© Pydantic Services Inc. 2025 to present