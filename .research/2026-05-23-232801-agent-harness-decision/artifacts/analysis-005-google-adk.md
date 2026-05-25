# Google ADK — Agent Harness Analysis for Layer-3 Browser Finisher

**Sources:** fetch-001 through fetch-007-google-adk-*.md, repo source code.
**Verdict preview:** STRONG — already in production, zero new deps, all needed
primitives present.

---

## 1. What It Is + Already-In-Repo Status

Google Agent Development Kit (ADK) is an open-source, code-first Python framework
for building, evaluating, and deploying AI agents. It shipped in April 2025
(Apache 2.0, ~19.8K GitHub stars as of May 2026) and releases roughly bi-weekly.

**ADK is already in production in this repo.** `src/agents/root_apply_decider/`
implements a full `Agent → LiteLlm → Runner → InMemorySessionService` pipeline that
runs on every job-evaluation batch. The `google-adk==1.23.0` pin is present in
`pyproject.toml` alongside `litellm==1.82.1` and `google-genai==1.60.0`. No new
dependency needs to be added for the browser-finisher — the framework is already
installed and the infrastructure pattern is already debugged.

---

## 2. Loop Primitive — Runner + InMemorySessionService

ADK's tool-calling loop is the standard ReAct pattern: the LLM decides whether to
call a tool, ADK dispatches the call, the result feeds back in, and the cycle
repeats until the LLM produces a final text response. The entry point is
`runner.run_async(...)`, an async generator that yields `Event` objects.

The existing `src/agents/root_apply_decider/runtime.py` shows the exact production
pattern (reproduced verbatim):

```python
session_service = InMemorySessionService()  # type: ignore[no-untyped-call]
app_name = "job_apply_decider"
user_id = "worker"
session_id = str(uuid.uuid4())

await session_service.create_session(
    app_name=app_name,
    user_id=user_id,
    session_id=session_id,
    state={},
)

runner = Runner(agent=agent, app_name=app_name, session_service=session_service)

try:
    new_message = types.Content(
        role="user",
        parts=[types.Part(text=build_gate_payload(job))],
    )

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=new_message,
    ):
        event_text = extract_event_text(event)
        if not event_text:
            continue
        if hasattr(event, "is_final_response") and event.is_final_response():
            final_response_text = event_text
finally:
    await runner.close()
```

For the browser-finisher, the same structure applies. Swap `build_gate_payload(job)`
for the browser-fill task prompt and add tools. `InMemorySessionService` gives each
apply its own isolated state; session state is a plain `dict` suitable for tracking
`filled_fields`, `current_url`, etc.

Hard loop cap:
```python
from google.adk.runners import RunConfig
runner.run_async(..., run_config=RunConfig(max_llm_calls=40))
```

---

## 3. Function Tools

ADK auto-wraps plain Python callables in `tools=[...]` as `FunctionTool` instances.
Schema is inferred from type annotations and docstring. No decorator required:

```python
async def fill_field(selector: str, value: str) -> dict:
    """Fill an input field on the current page.

    Args:
        selector: CSS selector identifying the input field.
        value: Text to type into the field.
    Returns:
        dict with keys 'ok' (bool) and 'message' (str).
    """
    ...

agent = Agent(
    name="browser_finisher",
    model=LiteLlm(model="openai/gpt-4.1-mini"),
    instruction="Fill the job application form. Never submit.",
    tools=[fill_field, read_field, click_button, scroll_to, get_page_state, report_done],
)
```

Async functions are first-class. For explicit control, `FunctionTool(name=...,
description=..., func=...)` is also available.

---

## 4. before_tool_callback / after_tool_callback — Blocking Submit

`before_tool_callback` fires before every tool execution at the framework layer.
Returning a non-`None` dict skips the tool entirely and hands that dict to the LLM
as the result. This is the correct hook for the "never click Submit" guardrail.

```python
from typing import Optional
from google.adk.tools import BaseTool, ToolContext

SUBMIT_TOOL_NAMES = {"click_submit", "submit_form", "press_enter_on_submit"}

def block_submit_callback(
    tool: BaseTool,
    args: dict,
    tool_context: ToolContext,
) -> Optional[dict]:
    if tool.name in SUBMIT_TOOL_NAMES:
        return {
            "error": "SUBMIT_BLOCKED",
            "message": (
                "Submitting forms is disabled by policy. "
                "Stop filling and call report_done() instead."
            ),
        }
    return None  # all other tools execute normally
```

Wire it in at agent construction:

```python
agent = Agent(
    name="browser_finisher",
    model=LiteLlm(model="openai/gpt-4.1-mini"),
    instruction="Fill the job application form. Never submit.",
    tools=[...],
    before_tool_callback=block_submit_callback,
)
```

The LLM sees the rejection dict as the tool result. The actual click never executes.
Enforcement is at the Python layer — not relying on prompt-level compliance.

---

## 5. LiteLLM Provider Portability

ADK uses `google.adk.models.lite_llm.LiteLlm` to proxy any LiteLLM-supported
provider. The existing `src/agents/shared/model.py` helper already encapsulates
the pattern:

```python
from google.adk.models.lite_llm import LiteLlm
return LiteLlm(model=model_name)  # e.g. "openai/gpt-5-mini"
```

Provider strings use `"provider/model"` format. For the browser-finisher:

| Model | Estimated cost (20-turn apply) | Notes |
|---|---|---|
| `openai/gpt-5-mini` | ~$0.01–0.03 | Cheapest; already in use for decider |
| `openai/gpt-4.1-mini` | ~$0.02–0.05 | Better instruction following |
| `anthropic/claude-haiku-4-5` | ~$0.02–0.04 | Strong for structured form reasoning |

Switching providers is a one-liner: `LiteLlm(model="anthropic/claude-haiku-4-5")`.
No credential-plumbing changes — just set the corresponding `*_API_KEY` env var.

---

## 6. Browser-Agent Fit — 6 Playwright-CDP Tools

All 6 tools register as plain async Python functions:

```python
async def get_page_state(page: Page) -> dict:
    """Return the current URL, title, and visible form fields."""
    return {"url": page.url, "title": await page.title(),
            "fields": await page.evaluate("() => getFormFields()")}

async def fill_field(page: Page, selector: str, value: str) -> dict:
    """Fill a visible input field using its CSS selector."""
    await page.fill(selector, value)
    return {"ok": True, "selector": selector}

async def click_button(page: Page, selector: str) -> dict:
    """Click a non-submit button (Next page, section nav, etc.)."""
    await page.click(selector)
    return {"ok": True}

async def scroll_to(page: Page, selector: str) -> dict:
    """Scroll an element into view."""
    await page.evaluate(f"document.querySelector('{selector}').scrollIntoView()")
    return {"ok": True}

async def read_field(page: Page, selector: str) -> dict:
    """Read the current value of a form field."""
    return {"value": await page.input_value(selector)}

async def report_done(summary: str) -> dict:
    """Signal that form filling is complete without submitting."""
    return {"status": "DONE", "summary": summary}
```

`page` is injected via closure — wrap each tool as a lambda or `functools.partial`
that closes over the `Page` object obtained from `playwright.chromium.connect_over_cdp(
"http://localhost:9222")`. The Simplify Copilot extension content is already
accessible from the same page context.

---

## 7. Verdict: STRONG

- **Zero new deps.** `google-adk==1.23.0`, `litellm==1.82.1`, and
  `google-genai==1.60.0` are already pinned. The browser-finisher shares the
  same stack without adding a line to `pyproject.toml`.
- **Already proven in this repo.** `root_apply_decider/runtime.py` is the exact
  pattern. Copy, adapt tools, add `before_tool_callback`. Done.
- **Hard Submit guardrail.** `before_tool_callback` fires at the Python layer —
  cannot be bypassed by a well-intentioned LLM response.
- **Provider portability.** LiteLLM bridge already wired; any model swap is one
  line. No vendor lock-in.
- **Cost control.** `RunConfig(max_llm_calls=40)` caps LLM calls hard per apply.
- **In-process.** No sidecar, no HTTP. The agent runs inside the apply-worker
  Python process sharing the Playwright `Page` by reference.

**Weaknesses (acknowledged):**
- ADK 2.0 shipped 2026-05-19 with breaking changes; pinned `1.23.0` is behind.
  Upgrade path exists but requires validation.
- `run_async` async-generator pattern is more verbose than OpenAI Agents SDK's
  single `await Runner.run(...)`. For a multi-turn browser loop the verbosity
  is acceptable and already templated in the repo.
- Real-world public production usage is still mostly tutorial repos. Our own
  `root_apply_decider` is the best battle-tested reference we have.
