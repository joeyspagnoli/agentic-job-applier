Upsonic/Upsonic:src/upsonic/utils/package/exception.py: class ModelRetry(Exception):
aispiritlabs/aispiritlab-agentic:packages/agentic/src/agentic/exceptions.py: class ModelRetry(AgenticError):
EpistemonLex/dt-contracts:src/dt_contracts/tutoring.py: class ModelRetry(DeepthoughtBaseModel):
hurtener/penguiflow:penguiflow/llm/retry.py: class ModelRetry(Exception):
pydantic/pydantic-ai:pydantic_ai_slim/pydantic_ai/mcp.py: ModelRetry: If the tool call fails.
pydantic/pydantic-ai:pydantic_ai_slim/pydantic_ai/mcp.py: raise exceptions.ModelRetry(e.error.message)
tencentmusic/page-eyes-agent:src/page_eyes/tools/_base.py: from pydantic_ai import ModelRetry, RunContext, ToolReturn, ImageUrl, Tool
tencentmusic/page-eyes-agent:src/page_eyes/tools/_base.py: raise ModelRetry('only use one tool at a time')
Canner/WrenAI:sdk/wren-pydantic/src/wren_pydantic/_errors.py: """WrenError → ModelRetry mapping for Pydantic AI tools.
Canner/WrenAI:sdk/wren-pydantic/src/wren_pydantic/_errors.py: raise ``ModelRetry(msg)`` from inside a tool — the framework forwards the
GoogleCloudPlatform/generative-ai:gemini/sample-apps/swot-agent/agent.py: from pydantic_ai import Agent, ModelRetry, RunContext
GoogleCloudPlatform/generative-ai:gemini/sample-apps/swot-agent/agent.py: raise ModelRetry("\n".join(issues))
PrefectHQ/marvin:src/marvin/utilities/tools.py: Pydantic AI doesn't catch errors except for ModelRetry, so we need to make
PrefectHQ/marvin:src/marvin/utilities/tools.py: sure we catch them ourselves and raise a ModelRetry instead.
oornnery/harness-lab:apps/tooled/src/core/agents.py: class ModelRetry(Exception):
langchain-ai/chat-langchain:src/middleware/__init__.py: from src.middleware.retry_middleware import ModelRetryMiddleware
langchain-ai/chat-langchain:src/middleware/__init__.py: __all__ = ["ModelRetryMiddleware", "ToolRetryMiddleware", "GuardrailsMiddleware"]
Repello-AI/Agent-Wiz:examples/code/pydantic/weather/weather_agent.py: from pydantic_ai import Agent, ModelRetry, RunContext
Repello-AI/Agent-Wiz:examples/code/pydantic/weather/weather_agent.py: raise ModelRetry('Could not find the location')
openai/openai-agents-python:src/agents/models/openai_chatcompletions.py: from ..retry import ModelRetryAdvice, ModelRetryAdviceRequest
fctr-id/okta-ai-agent:src/core/agents/synthesis_agent.py: from pydantic_ai import RunContext, FunctionToolset, ModelRetry, UsageLimits
fctr-id/okta-ai-agent:src/core/agents/synthesis_agent.py: raise ModelRetry("Successful synthesis output cannot include an error")
ossature/ossature:src/ossature/audit/fixer.py: from pydantic_ai import Agent, ModelRetry, RunContext
ossature/ossature:src/ossature/audit/fixer.py: raise ModelRetry(
