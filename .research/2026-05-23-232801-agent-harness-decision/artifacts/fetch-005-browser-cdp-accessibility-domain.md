# Chrome DevTools Protocol — Accessibility Domain

Source: https://chromedevtools.github.io/devtools-protocol/tot/Accessibility/

## Methods

### Accessibility.enable
Activates accessibility tracking, maintaining consistent `AXNodeId`s across calls.
Note: can impact performance until disabled.

### Accessibility.disable
Deactivates the accessibility domain.

### Accessibility.getFullAXTree
Retrieves the complete accessibility tree from the root document.
- Parameters: `depth` (optional integer), `frameId` (optional)
- Returns: Array of `AXNode` objects

### Accessibility.getPartialAXTree
Fetches the `AXNode` for a given DOM node plus its ancestors, siblings, children if requested.
- Parameters: `nodeId`, `backendNodeId`, or `objectId`; optional `fetchRelatives` boolean
- Returns: partial tree as `AXNode` array

### Accessibility.getRootAXNode
Returns the root accessibility node for a specified frame.
- Parameters: `frameId` (optional)
- Returns: Single `AXNode`

### Accessibility.getAXNodeAndAncestors
Retrieves a node and all ancestors up to and including the root.
- Parameters: node identifier (one of three types)
- Returns: `AXNode` array

### Accessibility.getChildAXNodes
Fetches child nodes of a specified accessibility node.
- Parameters: `id` (AXNodeId), `frameId` (optional)
- Returns: `AXNode` array

### Accessibility.queryAXTree
Searches subtrees for nodes matching accessible name/role criteria.
Returns results "including nodes that are ignored for accessibility."
- Parameters: node identifier, `accessibleName`, `role` (optional)
- Returns: matching `AXNode` array

## AXNode Structure
```
nodeId            — Unique identifier (AXNodeId)
ignored           — Boolean indicating accessibility status
ignoredReasons    — Array of AXProperty objects
role              — Computed role (AXValue)
chromeRole        — Chrome raw role (AXValue)
name              — Accessible name (AXValue)
description       — Accessible description (AXValue)
value             — Node value (AXValue)
properties        — Additional AXProperty array
parentId/childIds — Hierarchy references
backendDOMNodeId  — Associated DOM node
frameId           — Document frame reference
```

## Shadow DOM Behavior (verified in practice)
- The AX-tree built by Chrome includes nodes from open shadow roots (this is how screen readers see content like custom web components and the Simplify Copilot extension's UI inside `div.simplify-jobs-shadow-root`).
- Closed shadow roots are not included — but Simplify uses an open shadow root, so AX-tree access works.
- For traversal across frames, `frameId` is provided on AXNodes belonging to other frames; you can request per-frame trees if needed.

## For our 6 tools
- snapshot → `Accessibility.getFullAXTree` once per turn, filter `ignored=false`, assign `@eN` refs by index, map `nodeId → backendDOMNodeId`.
- click/type/select → resolve `@eN` → `backendDOMNodeId` → use `DOM.resolveNode` to get an `objectId` → call existing Playwright `ElementHandle.click()` / `fill()` / `select_option()` via `JSHandle`.
  Or simpler: just call CDP `Input.dispatchMouseEvent` / `Input.dispatchKeyEvent` after `DOM.getBoxModel`.
