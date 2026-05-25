# GH Survey 002 — Playwright + LLM Python Repos

Date: 2026-05-24
Command: `gh search repos "playwright agent llm" --language python --sort=stars --limit 15`

Result: **0 results returned** — the query returned an empty array.

## Interpretation

"playwright agent llm" as combined query terms returned no matches on GitHub Python repos. This means:
1. Projects integrating Playwright + LLM don't tend to use these exact terms together in a README/description
2. The actual production projects (browser-use, Skyvern) use different terminology ("browser automation", "web agent", etc.)
3. Cross-referencing with survey-001: the top projects use Playwright directly without advertising it as "playwright LLM agent" — it's just their implementation detail

## Supplementary finding (from survey-001 analysis)

Projects that do use Playwright + LLM:
- browser-use/browser-use — Playwright as browser layer, custom loop as harness
- Skyvern-AI/skyvern — Playwright as browser layer, custom BYO loop as harness  
- lmnr-ai/index — Custom Browser class wrapping Playwright, custom loop
- microsoft/magentic-ui — Playwright for web_surfer agent, custom protocol harness
- gptme/gptme — Playwright as optional browser tool, BYO loop
