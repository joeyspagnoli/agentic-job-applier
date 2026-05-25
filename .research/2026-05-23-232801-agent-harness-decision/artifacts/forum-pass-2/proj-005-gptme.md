# Project Deep Dive — gptme/gptme

URL: https://github.com/gptme/gptme
Stars: 4,309 (as of 2026-05-24)
Last commit: 2026-05-24 (active)
Language: Python
Description: "Your agent in your terminal, equipped with local tools: writes code, uses the terminal, browses the web."

## Agent Harness

**BYO CUSTOM LOOP — pure Python, no framework.**

gptme is a terminal-based coding/browsing agent that uses a custom conversation loop. No LangChain, no OpenAI Agents SDK, no Google ADK.

From `pyproject.toml`:
```
openai = "^1.0"
anthropic = "^0.47"
pydantic = "^2.11.7"
browser = ["playwright"]   # optional dep
```

Explicit exclusion: `module = "langchain.*"` — the mypy config actively excludes langchain type checking, suggesting it's not in use.

## Browser Layer

Playwright as an optional dep (`[browser]` extra). Custom browser tools that read accessibility trees and take screenshots.

## Architecture

Unlike browser-use or Skyvern which are pure browser agents, gptme is a general terminal agent that adds browser capability as a tool. This is closest to the "BYO Playwright tools" pattern in our project — Playwright is one tool among many (shell, code execution, file ops).

## What This Means

Even for a general-purpose agent (not browser-specific), the 4.3k-star production project chose BYO custom loop over any framework. Playwright is registered as a tool, not wrapped in a framework.
