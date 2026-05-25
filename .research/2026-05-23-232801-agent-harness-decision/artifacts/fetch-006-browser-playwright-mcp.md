# Microsoft Playwright MCP Server

Source: https://github.com/microsoft/playwright-mcp

## 1. Browser Connection Options
Supports BOTH launching a new browser and attaching to an existing one:

- **New browser (default)**: launches a persistent browser with profile storage
- **Existing browser via CDP**: `--cdp-endpoint` flag connects to running Chromium
- **Browser Extension**: can connect to existing Edge/Chrome tabs via the Playwright Extension
- **Remote endpoint**: supports connecting to existing Playwright server instances

Key CDP CLI flags:
```
--cdp-endpoint <url>     CDP endpoint to connect to
--cdp-header <headers>   CDP headers for connect request
--cdp-timeout <ms>       Timeout for CDP connection (default 30000)
```

## 2. Tools Exposed (40+)
- Core automation: click, type, navigate, hover, drag, fill forms, file upload, keyboard input
- Tab management: list, create, close, select
- Snapshots & inspection: AX-tree snapshots (preferred over screenshots), page snapshots
- Storage: cookies, localStorage, sessionStorage
- Network: mock requests, set routes, list requests, offline mode
- DevTools: highlighting, tracing, video recording
- Coordinate-based mouse ops
- PDF generation, test assertions, code generation

## 3. Accessibility vs. Screenshots
Documentation explicitly states:
> "Uses Playwright's accessibility tree, not pixel-based input. LLM-friendly. No vision models needed."

Snapshots are the primary observation format. Screenshots available but secondary.

## 4. Install & Config
MCP Config:
```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp@latest"]
    }
  }
}
```

To attach to our existing CDP Chrome:
```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp@latest", "--cdp-endpoint", "http://localhost:9222"]
    }
  }
}
```

- License: Apache-2.0
- Maturity: 65 releases, 32.9k stars (as of May 2026), latest v0.0.75
- Active maintenance by Microsoft

## 5. Programmatic Usage
```javascript
import { createConnection } from '@playwright/mcp';
const connection = await createConnection({
  browser: { launchOptions: { headless: true } }
});
```

## Verdict for our use case
- Pros: Off-the-shelf MCP server, attaches via `--cdp-endpoint`, AX-tree-based.
- Cons: Node-only (we are Python). Adds a Node runtime + npm dep to dist/ for Windows non-technical users. The Claude Agent SDK can speak MCP, but our existing apply_worker is Python and already holds Playwright session state — handing the page to a sidecar Node process would fork browser-control ownership.
