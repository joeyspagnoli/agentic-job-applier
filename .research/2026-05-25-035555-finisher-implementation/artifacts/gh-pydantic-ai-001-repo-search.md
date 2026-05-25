# gh search — `pydantic-ai` + `playwright` repos

**Command:** `gh search repos "pydantic-ai playwright" --sort=stars`
**Date:** 2026-05-25

## Direct hits (sparse — most prod integrations live in code, not topic tags)

| Repo | Stars | Updated |
|---|---|---|
| `sashokbg/pydantic-ai-playwright` | 0 | 2025-11-18 |
| `lskellerm/TripPlannerAgent` | 0 | 2026-03-11 |

## Real-world code matches (`gh search code "from pydantic_ai import Agent" playwright --lang=python`)

Far richer set — these are the actual production patterns:

| Repo | Path | Pattern |
|---|---|---|
| **`polarsource/polar`** | `server/polar/organization_review/collectors/website.py` | `Agent` + `RunContext` + Playwright `Browser`/`Page`/`Route` — production org-review crawler |
| **`philmade/pydantic_scrape`** | `pydantic_scrape/agents/playwright_browse_agent.py` | dedicated `PlaywrightWebKitBrowser` dep + `playwright_toolset` |
| **`TheAgenticAI/CortexON`** | `ta-browser/core/orchestrator.py` | `Agent`, `RunContext`, `Usage` — full browser-using agent orchestrator |
| **`pamelafox/personal-linkedin-agent`** | `invitations_manager.py` | LinkedIn automation with `NativeOutput` + Playwright `ElementHandle`/`Page` |
| **`strawgate/pydantic-ai-ecosystem`** | `packages/pydantic_ai_playwright/_capability.py` | `PlaywrightCapability(MCPPartnerCapability)` — packaged capability pattern |
| **`djames1109/aix`** | `jobsearch-playwright-mcp-pydanticai/agent/browser_agent.py` | Job search agent (closest analogue to our case) |
| **`vstorm-co/pydantic-deepagents`** | `pydantic_deep/toolsets/browser.py` | `BrowserCapability` packaged with Playwright |
| **`abhishekgusain07/clarity`** | `spikes/pydantic_ai_playwright_spike.py` | Spike — Playwright MCP via `MCPServerStdio` |
| **`pydantic/talks`** | `2025-05-odsc/browser_mcp.py` | Official Pydantic conference talk — Playwright MCP pattern |
| `aaltat/robotframework-analysis` | `src/robotframework_analysis/agent/playwright_log_analyst.py` | Log-analysis agent |
| `drillan/mixseek-plus` | `src/mixseek_plus/agents/playwright_markdown_fetch_agent.py` | Markdown fetch via Playwright |
| `Ciemaar/PrintQueueManager` | `src/worker/llm_scraper.py` | Scraper with sync_playwright |
| `LEVI-DEVIA/Agentic_Entreprise` | `main.py` | Playwright MCP via `MCPServerStdio` |
| `SkafteNicki/dtu_mlops` | `tools/course_stats/viz.py` | One-off viz scraper |
| `sgmurphy/NoiseGate` | `noisegate/importer.py` | Program importer scraper |

## Two integration shapes

The 16 matches partition cleanly into two architectures:

### Shape A — MCP server (Playwright-MCP via `MCPServerStdio`)
The agent talks to the Microsoft-published `@playwright/mcp` Node server over stdio. The model
chooses among ~30 MCP tools (`browser_click`, `browser_type`, `browser_snapshot`, …).
**Pros:** zero browser glue code. **Cons:** can't drive an existing-CDP browser; can't customize
tool surface; high token cost from large tool schemas.

Examples: `pydantic/talks`, `LEVI-DEVIA/Agentic_Entreprise`, `abhishekgusain07/clarity`,
`djames1109/aix`.

### Shape B — BYO Playwright tools (deps via `RunContext`)
The agent gets a Playwright `Page` (or `Browser`) injected via `deps_type` / `RunContext.deps`.
Tools are hand-rolled `@agent.tool` functions that call `page.click()`, `page.fill()`, etc.
**Pros:** works with CDP-attached browser, small tool surface, cheap. **Cons:** must write the
tools yourself (~250 LOC).

Examples: `polarsource/polar`, `philmade/pydantic_scrape`, `TheAgenticAI/CortexON`,
`pamelafox/personal-linkedin-agent`, `strawgate/pydantic-ai-ecosystem`.

## Conclusion

Our locked decision #2 ("BYO Playwright tools over CDP") matches **Shape B**. Five real
production repos use this exact shape — we have strong patterns to copy.

Best references to study, in priority order:

1. `polarsource/polar` (production, mature)
2. `pamelafox/personal-linkedin-agent` (job-context-adjacent, single-purpose)
3. `philmade/pydantic_scrape` (toolset packaging pattern)
4. `TheAgenticAI/CortexON` (multi-step orchestrator with usage capture)
5. `strawgate/pydantic-ai-ecosystem` (capability pattern — what "official-looking" Playwright integration looks like)
