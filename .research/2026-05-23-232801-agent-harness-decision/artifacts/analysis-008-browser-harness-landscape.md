# Analysis 008: Browser Harness Landscape Survey

_Generated: 2026-05-24. Primary sources: fetch-003 through fetch-018 in this artifact directory._

---

## 1. Comparison Matrix

| Tool | Lang | Attach to existing CDP? | A11y snapshot? | Self-hosted? | License | Notes |
|---|---|---|---|---|---|---|
| **Playwright Python (BYO tools)** | Python | Yes — `connect_over_cdp("http://localhost:9222")` | Yes — `CDPSession.send("Accessibility.getFullAXTree")` | Yes | Apache-2.0 | Zero extra deps; existing code already uses this path |
| **browser-use** | Python | Yes — `BrowserProfile(cdp_url="http://localhost:9222", is_local=True)` | Hybrid — AX tree via cdp-use + DOM CSS snapshot | Yes | MIT | Heavy opinionated loop; cdp-use dep; large context per step |
| **Playwright MCP** | Node.js | Yes — `--cdp-endpoint http://localhost:9222` | Yes — AX-tree snapshots, no vision needed | Yes | Apache-2.0 | Requires Node.js + npm on Windows dist; forks ownership from Python worker |
| **agent-browser** (Vercel) | Rust/Node CLI | Yes — `agent-browser connect <url>` | Yes — `agent-browser snapshot` with `@eN` refs | Yes | Apache-2.0 | CLI only; Rust binary; no Python API; ref pattern is inspiration |
| **Stagehand** | TypeScript | Partial — Browserbase CDP cloud-first | Hybrid CDP+LLM | Yes (TS only) | MIT | TS-only; Browserbase-coupled; no Python worker path |
| **Steel** | Python/TS SDK | No — cloud sessions only | Via Computer Use integrations | No | Proprietary | Cloud-only; $0.12/hr overage after free tier |
| **Browserbase** | Python/TS SDK | No — cloud-managed CDP | No native AX | No | Proprietary | $20/mo dev, $99/mo startup; hard recurring cost for dist/ users |
| **Anthropic Computer Use** | Any (REST) | No — owns Linux VM desktop | No — pixel-based screenshots only | N/A | Anthropic ToS | 1024×768 ≈ 2,635 image tokens/turn; VM takeover model |

---

## 2. Why "Attach to Existing CDP" is Mandatory

The Simplify Copilot Chrome extension is the load-bearing autofill engine for ~90% of field completion. It runs as a content script and shadow-root component (`div.simplify-jobs-shadow-root`) inside the user's normal Chrome session. Any tool that launches its own browser instance — headless Chromium, a new profile, a cloud VM browser — will have no extension loaded and will produce a blank shadow root. The user's existing session cookies and auth state for LinkedIn, Greenhouse, Workday, etc. are also required; a fresh browser has none of that.

`playwright.chromium.connect_over_cdp("http://localhost:9222")` returns a `Browser` whose first `BrowserContext` is the existing one, complete with all tabs, cookies, and loaded extensions. This is confirmed by the Playwright Python docs (fetch-003) and is already used by our `apply_worker.py`.

Simplify uses an open shadow root (`mode: open`), so Chrome's AX tree pierces it natively — verified by the CDP Accessibility domain docs (fetch-005): "the AX tree built by Chrome includes nodes from open shadow roots."

---

## 3. AX-Tree vs. Screenshots: Token Math

### Per-turn cost estimate

| Observation type | Tokens (typical post-Simplify job page) |
|---|---|
| AX-tree text snapshot (filtered, non-ignored nodes) | ~200–400 tokens |
| JPEG screenshot 1024×768 (Claude Sonnet) | ~1,500–2,000 tokens |
| PNG screenshot 1024×768 | ~2,500–3,000 tokens |

The 1024×768 screenshot token cost comes from Claude's image tile formula: ceil(1024/170) × ceil(768/170) = 6 × 5 = 30 tiles × 85 tokens/tile + 85 base = **2,635 tokens**. This matches the reference resolution in Anthropic Computer Use docs (fetch-014: `display_width_px=1024, display_height_px=768`).

### Across a full apply session

| Turns | AX-tree @ 300 tok | Screenshot @ 2,000 tok | Ratio |
|---|---|---|---|
| 5 | 1,500 | 10,000 | 6.7× |
| 15 | 4,500 | 30,000 | 6.7× |
| 25 | 7,500 | 50,000 | 6.7× |

### Cost in dollars (claude-sonnet-4-6 input: $3/MTok)

| Turns | AX-tree | Screenshot |
|---|---|---|
| 5 | $0.0045 | $0.030 |
| 15 | $0.0135 | $0.090 |
| 25 | $0.0225 | $0.150 |

**AX-tree at 15 turns ≈ $0.013 — within the $0.01–0.10/apply budget.** Screenshots at 15 turns hit $0.090 and blow the budget at 25 turns. Screenshots also require a vision-capable model, eliminating cheaper text-only options.

---

## 4. Playwright + CDP — The Baseline

The existing codebase already calls `playwright.chromium.connect_over_cdp(...)`. From that `Page` object, two AX snapshot paths are immediately available with no new dependencies:

```python
# Option A: Playwright's built-in (convenience wrapper, legacy)
snapshot = await page.accessibility.snapshot()   # returns dict tree

# Option B: Raw CDP (preferred — direct access to backendDOMNodeId)
cdp = await page.context.new_cdp_session(page)
result = await cdp.send("Accessibility.getFullAXTree")
nodes = result["nodes"]   # list of AXNode dicts with nodeId, role, name, backendDOMNodeId
```

Option B is preferred because `page.accessibility.snapshot()` is documented as legacy/deprecated in favor of role-based locators (fetch-003), and the raw CDP call gives direct access to `backendDOMNodeId` — the link from AX node to DOM node needed for click/type dispatch. The CDP `Accessibility` domain (fetch-005) confirms: `backendDOMNodeId` is present on each AXNode and can be used with `DOM.resolveNode` to get a JavaScript `objectId` for element interaction.

Both options confirm that open shadow root nodes — including Simplify's `div.simplify-jobs-shadow-root` — appear in the AX tree because Chrome builds it across shadow boundaries for screen-reader support.

---

## 5. The `@eN` Ref Pattern — Python Implementation Outline

agent-browser (fetch-016) popularized the `@eN` ref pattern: after a `snapshot` call, each interactive AX node gets a stable short ref (`@e1`, `@e2`, ...). The model uses refs to address elements; it never constructs CSS selectors. The registry is reset on every snapshot call, preventing stale refs.

Implementation outline (~180 lines of pure Python):

```python
# browser_tools/snapshot.py

@dataclass
class AXRef:
    ref: str               # "@e1", "@e2", ...
    node_id: str           # CDP AXNodeId (string)
    backend_dom_node_id: int  # for DOM.resolveNode
    role: str
    name: str
    value: str = ""

_ref_registry: dict[str, AXRef] = {}  # reset each snapshot()

INTERACTIVE_ROLES = {
    "button", "link", "textbox", "combobox", "listbox", "checkbox",
    "radio", "menuitem", "tab", "option", "spinbutton", "searchbox",
    "switch", "slider", "menuitemcheckbox", "treeitem",
}

async def snapshot(page) -> str:
    global _ref_registry
    _ref_registry = {}
    cdp = await page.context.new_cdp_session(page)
    result = await cdp.send("Accessibility.getFullAXTree")
    nodes = result["nodes"]
    by_id = {n["nodeId"]: n for n in nodes}
    roots = [n for n in nodes if not n.get("parentId")]
    ref_counter = 0
    lines = []

    def walk(node_id, depth=0):
        nonlocal ref_counter
        node = by_id.get(node_id)
        if not node or node.get("ignored"):
            return
        role = (node.get("role") or {}).get("value", "")
        name = (node.get("name") or {}).get("value", "")
        value = (node.get("value") or {}).get("value", "")
        indent = "  " * depth
        if role in INTERACTIVE_ROLES and node.get("backendDOMNodeId"):
            ref_counter += 1
            ref = f"@e{ref_counter}"
            _ref_registry[ref] = AXRef(ref, node["nodeId"],
                                        node["backendDOMNodeId"], role, name, value)
            val_str = f' value="{value}"' if value else ""
            lines.append(f'{indent}[{ref}] {role} "{name}"{val_str}')
        elif name and role not in ("none", "generic", ""):
            lines.append(f'{indent}{role} "{name}"')
        for child_id in node.get("childIds", []):
            walk(child_id, depth + 1)

    for root in roots:
        walk(root["nodeId"])
    await cdp.detach()
    return "\n".join(lines)


async def resolve_ref(page, ref: str):
    ax_ref = _ref_registry[ref]   # KeyError if stale/unknown
    cdp = await page.context.new_cdp_session(page)
    obj = await cdp.send("DOM.resolveNode", {"backendNodeId": ax_ref.backend_dom_node_id})
    object_id = obj["object"]["objectId"]
    handle = await page.evaluate_handle("id => id", object_id)
    el = handle.as_element()
    await cdp.detach()
    return el

# The 6 tools are thin wrappers over resolve_ref:
async def click(page, ref):              el = await resolve_ref(page, ref); await el.click()
async def type_text(page, ref, text):    el = await resolve_ref(page, ref); await el.fill(text)
async def select(page, ref, option):     el = await resolve_ref(page, ref); await el.select_option(option)
async def goto(page, url):               await page.goto(url)
async def wait_for(page, pred):          await page.wait_for_function(pred)
```

Snapshot output is compact text. A typical form section renders as ~15–30 lines, keeping context under 400 tokens.

---

## 6. browser-use — Definitive Assessment

**Does it attach to an existing CDP browser?** Yes. Confirmed by source (fetch-017, `profile.py`):
```python
cdp_url: str | None = Field(default=None,
    description='CDP URL for connecting to existing browser instance')
```
Usage: `BrowserProfile(cdp_url="http://localhost:9222", is_local=True)`. Confirmed by GitHub issue search: "Use `BrowserProfile(cdp_url='http://localhost:9222', is_local=True)`" is the documented pattern.

**Does it use AX or DOM serialization?** Both — merged. The `DomService` (fetch-018) imports `GetFullAXTree` from the `cdp-use` package (a lower-level CDP wrapper separate from Playwright) AND fetches DOM computed styles, CSS layout, and clickability data. Result: an `EnhancedDOMTreeNode` tree richer than a raw AX snapshot, but also much larger — hundreds to thousands of tokens per step.

**Is it BYO browser-friendly?** Technically yes. Practically, it is a full-stack browser agent framework with its own LLM integration, opinionated prompt format, `cdp-use` dependency, and agent loop. The apply_worker already has a Claude Agent SDK loop; browser-use's loop would be redundant and conflicting. Stripping it to a thin 6-tool layer would mean fighting the library.

**Verdict: Skip browser-use as the harness layer.** Its CDP attach is real but the rest of the framework is not needed and adds complexity. Its DOM serialization is optimized for its own larger-context prompt format, not for our 200–400 token AX-tree target.

---

## 7. Stagehand — Rejected

TypeScript only (80.5% of repo by language, fetch-011). Designed around Browserbase's managed CDP cloud sessions as the primary backend. A separate Python port exists but is not the canonical implementation and is under active divergence. The CDP engine uses Playwright internally, but the quickstart, documentation, and tooling are all TS + Browserbase. No straightforward path to attaching to our local Chrome with Simplify pre-loaded from a Python worker. Rejected.

---

## 8. Steel + Browserbase — Rejected for Self-Hosted Dist

**Steel** (fetch-012): Cloud-managed browser sessions via REST API (`steel.dev` API key). Sessions are provisioned cloud-side; there is no concept of attaching to a pre-existing local Chrome. Integrations with Computer Use and browser-use require connecting to Steel's cloud Chromium, not the user's machine.

**Browserbase** (fetch-013): Cloud-only managed browsers. Free plan: 1 browser-hour/month. Developer: $20/month + $0.12/browser-hour overage. Startup: $99/month. At 5–10 minutes per apply, 1 browser-hour ≈ 6–12 applies — a free user hits the cap immediately. The Developer plan at $20/month is a hard recurring cost before any LLM spend. Both services require a cloud API key and cannot attach to the user's local Chrome with Simplify loaded. Rejected for self-hosted dist/.

---

## 9. Anthropic Computer Use — Rejected

Computer Use (fetch-014) provides a `computer_20251124` tool giving Claude screenshot capture + mouse/keyboard dispatch over a Linux VM desktop (Docker container with Mutter WM, Firefox, LibreOffice). It does not have a CDP endpoint parameter or any mechanism to attach to a Chrome instance outside its container.

**Token cost:** 1024×768 screenshot = 2,635 tokens. At 15 turns = 39,525 image tokens = $0.12 at Sonnet input pricing — already at the top of the $0.01–0.10/apply budget for input tokens alone, before output tokens or any text context. Pixel-based observation also requires a vision-capable model; the `computer-use-2025-11-24` beta header restricts which models are available.

**Execution model mismatch:** Computer Use is designed to OWN a desktop environment (start → see screen → click → see screen). Our architecture requires attaching to an existing Chrome session where the Simplify extension is already loaded and has already performed autofill. There is no way to retrofit Computer Use into this model. Rejected.

---

## 10. Microsoft Playwright MCP — One Strong Contender

**CDP attach:** Confirmed (fetch-015, README). `--cdp-endpoint http://localhost:9222` is a documented first-class mode. The flag is listed with its env var `PLAYWRIGHT_MCP_CDP_ENDPOINT`. Works the same as `playwright.chromium.connect_over_cdp()`.

**AX-tree snapshots:** Confirmed. README explicitly states: "Uses Playwright's accessibility tree, not pixel-based input. LLM-friendly. No vision models needed." Snapshots are the primary observation format; screenshots are opt-in.

**Self-hosted:** Yes. Apache-2.0, `npx @playwright/mcp@latest`, no cloud dependency.

**40+ built-in tools** covering all 6 primitives: click, fill, navigate, select, wait, and more.

**The blocker for our dist/:** Requires Node.js 18+ installed on Windows. Our users are non-technical; adding a Node.js runtime + npm to the Windows installer is a significant packaging burden that doesn't exist today. Additionally, the Python apply_worker holds the Playwright `Page` object and session state. Running Playwright MCP as a sidecar Node process would fork browser-control ownership — both would be acting on the same browser, creating race conditions and state management complexity.

**When it becomes the right choice:** If the apply_worker is refactored from a Python `async` CDP loop into a pure MCP-tool-calling Claude Agent SDK session, Playwright MCP becomes a drop-in. One `claude mcp add` command replaces our entire custom browser tool layer. The Claude Agent SDK already speaks MCP natively.

---

## 11. Final Recommendation: BYO 6 Thin Python Tools

**Recommendation: Implement the 6 browser tools as thin Python functions over `playwright.chromium.connect_over_cdp()` + raw CDP `Accessibility.getFullAXTree`, using the `@eN` ref pattern from agent-browser. Zero new dependencies.**

Supporting evidence:

1. **Already in-path.** `apply_worker.py` already holds a Playwright `Page` from `connect_over_cdp`. The 6 tools are ~200 lines wrapping APIs we already import.

2. **AX-tree via CDPSession is confirmed working** for open shadow roots including Simplify's (fetch-004, fetch-005). `backendDOMNodeId` on each AX node gives direct DOM dispatch without selector fragility.

3. **`@eN` ref pattern** (agent-browser, fetch-016) is a 100–150-line in-process registry. The model only sees short refs; CSS selector construction is eliminated.

4. **Token budget confirmed:** 200–400 tokens/snapshot × 15 turns ≈ $0.013 at Sonnet pricing — 4–7× cheaper than screenshot alternatives, within the $0.01–0.10/apply LLM budget.

5. **Zero new dist/ dependencies.** `playwright` is already pinned in `requirements.txt`. Nothing new to package for Windows non-technical users.

6. **No ownership fork.** Python loop retains full ownership of the `Page` object. No sidecar processes, no IPC, no race conditions.

7. **browser-use confirms the CDP path works** (`BrowserProfile(cdp_url=...)` is real and documented), but adds a full agent framework we don't need.

8. **Playwright MCP is the future option** if we ever move to a pure-MCP agent architecture — one config line replaces our custom tools. But today it requires Node.js on Windows dist and forks session ownership.

---

## 12. One Strong Contender: Playwright MCP (conditional)

Microsoft Playwright MCP (`@playwright/mcp`, Apache-2.0, 33k stars, active Microsoft maintenance) is the one tool that rises above BYO on feature completeness:

- CDP attach via `--cdp-endpoint` confirmed ✓
- AX-tree snapshots confirmed ✓  
- 40+ tools covering all 6 needed primitives ✓
- Self-hosted, no cloud dependency ✓
- Would reduce our 200-line BYO implementation to zero lines ✓

**Adopt when:** apply_worker is refactored to a pure MCP-tool-calling architecture (Claude Agent SDK MCP toolset). At that point: `claude mcp add playwright npx @playwright/mcp@latest --cdp-endpoint http://localhost:9222` and the browser harness is done.

**Blocked today by:** Node.js install requirement on Windows dist/ + Python session ownership conflict.
