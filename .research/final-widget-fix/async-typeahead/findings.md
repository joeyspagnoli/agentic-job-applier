# candidate-location Async Typeahead — Findings

Live-tested on: `https://job-boards.greenhouse.io/cloudflare/jobs/7914628?gh_jid=7914628`  
Date: 2026-05-25  
Result: **"Gainesville, Florida, United States" successfully selected and verified.**

---

## 1. Widget Anatomy

### HTML: input + 2 ancestor levels

```html
<!-- .select-shell (root container — where chosen value appears after selection) -->
<div class="select-shell remix-css-b62m3t-container">

  <!-- .select__control (visible clickable box) -->
  <div class="select__control--outside-label select__control remix-css-12lpvrd-control">

    <!-- .select__value-container (holds placeholder OR single-value after selection) -->
    <div class="select__value-container remix-css-hlgwow">

      <!-- Chosen value appears here AFTER selection: -->
      <div class="select__single-value remix-css-1dimb5e-singleValue">
        Gainesville, Florida, United States
      </div>

      <!-- .select__input-container wraps the actual input -->
      <div class="select__input-container remix-css-19bb58m" data-value="">

        <!-- The combobox input: id="candidate-location" -->
        <input
          class="select__input"
          id="candidate-location"
          role="combobox"
          aria-autocomplete="list"
          aria-expanded="false"
          aria-haspopup="true"
          aria-labelledby="candidate-location-label"
          aria-required="true"
          type="text"
          autocomplete="off"
          style="opacity: 0; width: 100%;"
        />
      </div>
    </div>
  </div>
</div>
```

### React-Select Async pattern

This is **React-Select AsyncSelect** (Greenhouse's "remix" fork). Key characteristics:

- The `<input id="candidate-location">` is the combobox trigger, but its `value` attribute in the DOM is **always `""` after selection** — React-Select tracks typed text in internal state, not the DOM `value` attribute.
- This is why `agent-browser type`, `keyboard type`, and `keyboard inserttext` all appear to succeed but the menu never opens — they write the DOM `value` directly without triggering React's onChange handler.
- Options load asynchronously over the network — a **2-second wait** is required after triggering the input event.

### Where the chosen value lives after selection

```
#candidate-location  →  .closest('.select-shell')  →  .querySelector('.select__single-value')
```

The `.select__single-value` div holds the human-readable label. The `<input value="">` stays empty in the DOM even after selection.

---

## 2. Working CLI Sequence

### Why standard agent-browser commands fail

`agent-browser type @e38 "Gainesville"`, `keyboard type "Gainesville"`, and `keyboard inserttext "Gainesville"` all return success but React-Select's internal state never updates. The widget requires:
1. The **native HTMLInputElement value setter** (bypasses React's synthetic event guards)
2. An **`input` DOM event** dispatch to trigger React's onChange

### Proven working sequence (CDP via Python — live tested)

```python
async def fill_candidate_location(cdp_ws_url: str, city: str = "Gainesville") -> str:
    """
    Fill the Greenhouse React-Select AsyncSelect location field.

    Args:
        cdp_ws_url: CDP WebSocket URL for the greenhouse tab.
                    Get via: curl -s http://localhost:9222/json | python3 -c
                    "import sys,json; t=next(t for t in json.load(sys.stdin)
                     if 'greenhouse.io' in t.get('url','')); print(t['webSocketDebuggerUrl'])"
        city: City name prefix to type (default "Gainesville")

    Returns:
        Text of the selected option, e.g. "Gainesville, Florida, United States"
    """
    import asyncio, json, websockets

    MSG_ID = [0]

    async def run(ws):
        async def cdp(method, params=None):
            MSG_ID[0] += 1; mid = MSG_ID[0]
            await ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
                if msg.get("id") == mid:
                    return msg

        async def js(expr):
            r = await cdp("Runtime.evaluate", {"expression": expr, "returnByValue": True})
            return r["result"]["result"].get("value")

        # Step 1: Trigger React-Select internal onChange via native setter + input event
        await js(f"""
        (function() {{
            var input = document.querySelector('#candidate-location');
            input.focus();
            var setter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value').set;
            setter.call(input, '{city}');
            input.dispatchEvent(new Event('focus', {{ bubbles: true }}));
            input.dispatchEvent(new Event('input', {{ bubbles: true }}));
        }})()
        """)

        # Step 2: Wait 2 seconds for async network fetch of location options
        await asyncio.sleep(2.0)

        # Step 3: Click the Florida option (Gainesville, FL candidate)
        clicked = await js(f"""
        (function() {{
            var opts = document.querySelectorAll('[class*="select__option"]');
            for (var o of opts) {{
                if (o.textContent.includes('{city}, Florida')) {{
                    o.click(); return o.textContent;
                }}
            }}
            if (opts.length > 0) {{ opts[0].click(); return opts[0].textContent; }}
            return null;
        }})()
        """)

        if not clicked:
            raise RuntimeError(
                f"No options found for '{city}' — async fetch may have failed or timed out")

        # Step 4: Verify via .select__single-value
        verified = await js(
            "document.querySelector('#candidate-location')"
            ".closest('.select-shell')"
            ".querySelector('.select__single-value').textContent"
        )
        if not verified:
            raise RuntimeError("Selection did not persist — .select__single-value is empty")

        return verified

    async with websockets.connect(cdp_ws_url) as ws:
        return await run(ws)


# Usage:
# result = asyncio.run(fill_candidate_location(
#     cdp_ws_url="ws://localhost:9222/devtools/page/<TAB_ID>"
# ))
# assert result == "Gainesville, Florida, United States"
```

### The required wait

**`asyncio.sleep(2.0)` (2000 ms).** The Greenhouse API fetches location suggestions over the network. Menu was fully populated after 2 seconds in all live tests. 1 second risks a race condition. 2 seconds is the safe minimum.

### What NOT to use

- `agent-browser type @e38 "Gainesville"` — writes DOM value directly, bypasses React
- `agent-browser keyboard type "Gainesville"` — same issue
- `agent-browser keyboard inserttext "Gainesville"` — same issue
- `agent-browser press ArrowDown` + `press Enter` — no effect if menu never opened

---

## 3. Verifier JS One-Liner

```javascript
document.querySelector('#candidate-location').closest('.select-shell').querySelector('.select__single-value').textContent
```

**Live test result:** `"Gainesville, Florida, United States"` ✓

Run via agent-browser:
```bash
agent-browser --cdp 9222 eval \
  "document.querySelector('#candidate-location').closest('.select-shell').querySelector('.select__single-value').textContent"
```

---

## 4. Prompt-Ready Code Block

```python
# --- candidate-location fill (Greenhouse React-Select AsyncSelect) ---
# Paste into apply agent step handler. Requires: pip install websockets

import asyncio, json, websockets

async def _cdp_fill_location(ws_url: str, city: str = "Gainesville") -> str:
    MSG = [0]
    async def run(ws):
        async def cdp(m, p=None):
            MSG[0] += 1; mid = MSG[0]
            await ws.send(json.dumps({"id": mid, "method": m, "params": p or {}}))
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 15))
                if msg.get("id") == mid: return msg
        async def js(e):
            r = await cdp("Runtime.evaluate", {"expression": e, "returnByValue": True})
            return r["result"]["result"].get("value")

        # 1. Native setter + input event (bypasses React synthetic event guard)
        await js(f"(function(){{var i=document.querySelector('#candidate-location');i.focus();"
                 f"var s=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;"
                 f"s.call(i,'{city}');i.dispatchEvent(new Event('focus',{{bubbles:true}}));"
                 f"i.dispatchEvent(new Event('input',{{bubbles:true}}));}})()") 

        # 2. Wait 2s for async fetch
        await asyncio.sleep(2.0)

        # 3. Click Florida option (candidate is in Gainesville, FL)
        clicked = await js(
            f"(function(){{var o=document.querySelectorAll('[class*=\"select__option\"]');"
            f"for(var x of o){{if(x.textContent.includes('{city}, Florida')){{x.click();return x.textContent;}}}}"
            f"if(o.length>0){{o[0].click();return o[0].textContent;}}return null;}})()")

        if not clicked:
            raise RuntimeError(f"candidate-location: no options for '{city}'")

        # 4. Verify
        val = await js(
            "document.querySelector('#candidate-location')"
            ".closest('.select-shell').querySelector('.select__single-value').textContent")
        if not val:
            raise RuntimeError("candidate-location: selection did not persist")
        return val

    async with websockets.connect(ws_url) as ws:
        return await run(ws)


def fill_candidate_location(tab_id: str, city: str = "Gainesville") -> str:
    """Fill the candidate-location React-Select AsyncSelect on Greenhouse."""
    ws_url = f"ws://localhost:9222/devtools/page/{tab_id}"
    return asyncio.run(_cdp_fill_location(ws_url, city))
# --- end candidate-location fill ---
```

---

## Key Findings Summary

| What | Detail |
|------|--------|
| Widget type | React-Select AsyncSelect (Greenhouse "remix" fork) |
| Input selector | `#candidate-location` |
| Label text | "Location (City)" |
| Why standard type fails | React-Select ignores DOM value writes; needs native HTMLInputElement setter + `input` event |
| Required wait | **2000 ms** minimum after triggering input event (async network fetch) |
| Option selector | `[class*="select__option"]` |
| Target option text | `"Gainesville, Florida, United States"` |
| Value after selection | In `.select__single-value` inside `.select-shell` (NOT in `input.value`) |
| Verifier one-liner | `document.querySelector('#candidate-location').closest('.select-shell').querySelector('.select__single-value').textContent` |
| Live test result | `"Gainesville, Florida, United States"` ✓ |
