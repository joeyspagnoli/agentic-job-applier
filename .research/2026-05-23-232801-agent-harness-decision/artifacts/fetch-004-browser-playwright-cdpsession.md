# Playwright CDPSession API — Fetched Content

Source: https://playwright.dev/python/docs/api/class-cdpsession

## Overview
`CDPSession` enables direct communication with Chrome DevTools Protocol. Sends protocol methods and subscribes to protocol events.

## Creating a CDP Session
```python
# Sync
client = page.context.new_cdp_session(page)
# Async
client = await page.context.new_cdp_session(page)
```

## Core Methods

### send()
Sends raw CDP protocol commands and returns the response as a dictionary.

Signature:
```python
cdp_session.send(method)
cdp_session.send(method, **kwargs)
```

Parameters:
- `method` (str): Protocol method name
- `params` (Dict, optional): Method parameters

Returns: Dict

Example:
```python
response = client.send("Animation.getPlaybackRate")
print("playback rate is " + str(response["playbackRate"]))
```

### detach()
Disconnects the session from its target.
```python
cdp_session.detach()
```

### on()
Subscribes to CDP protocol events.
```python
client.on("Animation.animationCreated", lambda: print("animation created!"))
```

## Events
- `on("close")` — emitted when session is closed or `session.detach()` is called.

## For our use case
Calling raw CDP from a Playwright Page that was attached via `connect_over_cdp` is supported:
```python
cdp = await page.context.new_cdp_session(page)
tree = await cdp.send("Accessibility.getFullAXTree")
```
This returns the full AX-tree as a list of `AXNode` dicts — including iframe-piercing and (in practice) elements inside open shadow roots like Simplify's.

## Resources
- DevTools Protocol Viewer: https://chromedevtools.github.io/devtools-protocol/
- Getting Started with CDP: https://github.com/aslushnikov/getting-started-with-cdp
