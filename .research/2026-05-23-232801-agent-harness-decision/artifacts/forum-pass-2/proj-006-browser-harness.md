# Project Deep Dive — browser-use/browser-harness

URL: https://github.com/browser-use/browser-harness
Stars: 13,630 (as of 2026-05-24)
Last commit: 2026-05-24 (very active)
Language: Python
Description: "Browser Harness | Self-healing harness that enables LLMs to complete any task."

## Concept

browser-harness is NOT an agent harness in the traditional sense. It's a **thin CDP bridge** that gives Claude Code / Codex direct access to a running Chrome browser. The "harness" is ~1k lines across 4 files:
- `src/browser_harness/run.py` — entry point, executes Python scripts
- `src/browser_harness/daemon.py` — CDP WebSocket daemon
- `src/browser_harness/helpers.py` — browser helper functions (goto_url, page_info, etc.)
- `src/browser_harness/admin.py` — daemon management

## Core Philosophy

From their blog "The Bitter Lesson of Agent Harnesses":
> "Every one of them is a constraint the RL'd model has to fight around."
> "Delete the helpers. Let the agent write what it needs."

The self-healing loop:
1. Agent needs to upload a file
2. helper missing → `agent_helpers.py` doesn't have the function
3. Agent WRITES the function into `agent_helpers.py`
4. File uploaded

## Dependencies (pyproject.toml)

```
cdp-use==1.4.5      # raw CDP access
fetch-use==0.4.0    # HTTP fetch helper
pillow==12.2.0      # screenshots
websockets==15.0.1  # WebSocket to Chrome
```

**NO model SDK at all** — the caller (Claude Code, Codex, etc.) provides the model. This is purely a browser control layer.

## Usage Pattern

```bash
browser-harness <<'PY'
new_tab("https://example.com")
wait_for_load()
print(page_info())
PY
```

The agent (Claude Code etc.) writes Python that calls pre-imported helpers. When a helper is missing, the agent adds it to `agent_helpers.py`.

## What This Means

browser-harness represents the **most minimal possible** browser layer:
- No agent loop (the calling LLM is the loop)
- No model SDK (the calling LLM is the model)
- No harness framework (the calling LLM is the harness)
- Just: CDP connection + editable helper functions

This is relevant to our project because it shows the "BYO Playwright tools" pattern taken to its logical extreme. Our 6-tool Playwright approach (from analysis-010) sits between browser-use (heavier abstraction) and browser-harness (maximal rawness).

## Community Skills

`agent-workspace/domain-skills/` includes LinkedIn, GitHub, Amazon, Alaska, BOSS-zhipin, etc. — this is the closest existing precedent to our "job application domain knowledge" embedded in the agent.

Notable: `agent-workspace/domain-skills/BOSS-zhipin/` and LinkedIn skills confirm the job-application use case is an explicit target use case for browser-harness.
