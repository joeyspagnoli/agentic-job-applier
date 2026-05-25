# Playwright Python API — Fetched Content

Source: https://playwright.dev/python/docs/api/class-playwright

## Main Entry Point
Provides browser launch capabilities through a context manager:
```python
from playwright.sync_api import sync_playwright
with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
```

## Key Properties
- `chromium` — BrowserType for Chromium
- `firefox` — BrowserType for Firefox
- `webkit` — BrowserType for WebKit
- `devices` — dict of devices for emulation
- `selectors` — custom selector engines
- `request` — APIRequest for web API testing

## Device Emulation
```python
iphone = playwright.devices["iPhone 6"]
context = browser.new_context(**iphone)
```

## Methods
- `playwright.stop()` — terminates instance if not using context manager

## CDP Connection (BrowserType API)
The CDP connect method lives on `BrowserType` (e.g. `playwright.chromium`):
```python
# Async
browser = await playwright.chromium.connect_over_cdp("http://localhost:9222")
```
This returns a `Browser` whose first context is the existing one with all its tabs and (critically) its loaded extensions.

## Notes
Page accessibility is exposed via `page.accessibility.snapshot()` but the legacy `Accessibility` doc page returned 404 (deprecated in favor of role-based locators + raw CDP). The recommended modern path is either:
- Use `page.locator("role=...")` for direct queries, or
- Use a raw CDP session to call `Accessibility.getFullAXTree`.
