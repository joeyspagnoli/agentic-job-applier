# Vercel agent-browser README

Source: https://github.com/vercel-labs/agent-browser

- GitHub - vercel-labs/agent-browser: Browser automation CLI for AI agents · GitHub

































































































Skip to content






























## Navigation Menu


Toggle navigation

























Sign in






Appearance settings




























Platform AI CODE CREATION GitHub Copilot Write better code with AI
- GitHub Spark Build and deploy intelligent apps
- GitHub Models Manage and compare prompts
- MCP Registry New Integrate external tools


- DEVELOPER WORKFLOWS Actions Automate any workflow
- Codespaces Instant dev environments
- Issues Plan and track work
- Code Review Manage code changes


- APPLICATION SECURITY GitHub Advanced Security Find and fix vulnerabilities
- Code security Secure your code as you build
- Secret protection Stop leaks before they start


- EXPLORE Why GitHub
- Documentation
- Blog
- Changelog
- Marketplace


View all features - Solutions BY COMPANY SIZE Enterprises
- Small and medium teams
- Startups
- Nonprofits


- BY USE CASE App Modernization
- DevSecOps
- DevOps
- CI/CD
- View all use cases


- BY INDUSTRY Healthcare
- Financial services
- Manufacturing
- Government
- View all industries


View all solutions

- Resources EXPLORE BY TOPIC AI
- Software Development
- DevOps
- Security
- View all topics


- EXPLORE BY TYPE Customer stories
- Events & webinars
- Ebooks & reports
- Business insights
- GitHub Skills


- SUPPORT & SERVICES Documentation
- Customer support
- Community forum
- Trust center
- Partners


View all resources

- Open Source COMMUNITY GitHub Sponsors Fund open source developers


- PROGRAMS Security Lab
- Maintainer Community
- Accelerator
- GitHub Stars
- Archive Program


- REPOSITORIES Topics
- Trending
- Collections




- Enterprise ENTERPRISE SOLUTIONS Enterprise platform AI-powered developer platform


- AVAILABLE ADD-ONS GitHub Advanced Security Enterprise-grade security features
- Copilot for Business Enterprise-grade AI features
- Premium Support Enterprise-grade 24/7 support




- Pricing
















Search or jump to...












# Search code, repositories, users, issues, pull requests...




-->



Search



















Clear







































































































































































































































Search syntax tips





















# Provide feedback















-->
We read every piece of feedback, and take your input very seriously.



Include my email address so I can be contacted



Cancel

Submit feedback












# Saved searches


## Use saved searches to filter your results more quickly





-->





Name







Query




To see all available qualifiers, see our documentation .









Cancel

Create saved search










Sign in




Sign up





Appearance settings



- Resetting focus















You signed in with another tab or window. Reload to refresh your session.
You signed out in another tab or window. Reload to refresh your session.
You switched accounts on another tab or window. Reload to refresh your session.




Dismiss alert




















{{ message }}

































vercel-labs

/

agent-browser


Public












Notifications
You must be signed in to change notification settings

- Fork
2.1k

- Star
34.2k












- Code

- Issues
253

- Pull requests
230

- Actions

- Projects

- Security and quality
0

- Insights







Additional navigation options







- Code

- Issues

- Pull requests

- Actions

- Projects

- Security and quality

- Insights































# vercel-labs/agent-browser










main



283 Branches 82 Tags







Go to file

Code Open more actions menu



## Folders and files

Name Name Last commit message

Last commit date


## Latest commit

ctate



chore: enforce pnpm minimum release age ( #1377 )

Open commit details failure

May 20, 2026

4ad2848  ·  May 20, 2026


## History

575 Commits Open commit details

575 Commits

.claude-plugin

.claude-plugin

feat: dashboard provider support and session creation improvements ( #…

Mar 30, 2026

.github/ workflows

.github/ workflows

chore: enforce pnpm minimum release age ( #1377 )

May 20, 2026

.husky

.husky

full native ( #754 )

Mar 13, 2026

benchmarks

benchmarks

full native ( #754 )

Mar 13, 2026

bin

bin

feat: add linux-musl (Alpine) builds for x64 and arm64 ( #784 )

Mar 14, 2026

cli

cli

Require same-origin stream commands ( #1355 )

May 13, 2026

docker

docker

faster builds

Jan 11, 2026

docs

docs

chore: enforce pnpm minimum release age ( #1377 )

May 20, 2026

evals

evals

feat(skills): rename "agent-browser" skill to "core"; make CLI-served…

Apr 16, 2026

examples/ environments

examples/ environments

fix deployment for example ( #701 )

Mar 9, 2026

packages/ dashboard

packages/ dashboard

Prepare v0.27.0 release ( #1332 )

May 7, 2026

scripts

scripts

streamline release ( #1095 )

Mar 30, 2026

skill-data

skill-data

feat(react): React introspection, Web Vitals, and SPA primitives ( #1257 )

Apr 20, 2026

skills/ agent-browser

skills/ agent-browser

Make dashboard work from proxied origins via same-origin proxy ( #1111 )

May 7, 2026

.gitignore

.gitignore

Add AI chat to dashboard, refactor stream module, snapshot --urls, ba…

Apr 6, 2026

.node-version

.node-version

chore: enforce pnpm minimum release age ( #1377 )

May 20, 2026

.prettierrc

.prettierrc

scripts

Jan 10, 2026

AGENTS.md

AGENTS.md

feat(skills): rename "agent-browser" skill to "core"; make CLI-served…

Apr 16, 2026

CHANGELOG.md

CHANGELOG.md

Prepare v0.27.0 release ( #1332 )

May 7, 2026

LICENSE

LICENSE

fixes

Jan 10, 2026

README.md

README.md

chore: enforce pnpm minimum release age ( #1377 )

May 20, 2026

agent-browser.schema.json

agent-browser.schema.json

feat(tabs): t prefix for tab ids; --label for named tabs; drop --t…

Apr 16, 2026

package.json

package.json

chore: enforce pnpm minimum release age ( #1377 )

May 20, 2026

pnpm-lock.yaml

pnpm-lock.yaml

Add AI chat to dashboard, refactor stream module, snapshot --urls, ba…

Apr 6, 2026

pnpm-workspace.yaml

pnpm-workspace.yaml

chore: enforce pnpm minimum release age ( #1377 )

May 20, 2026

View all files




## Repository files navigation

- README
- Apache-2.0 license



# agent-browser



Browser automation CLI for AI agents. Fast native Rust CLI.


## Installation

### Global Installation (recommended)



Installs the native Rust binary:

npm install -g agent-browser
agent-browser install # Download Chrome from Chrome for Testing (first time only)











### Project Installation (local dependency)



For projects that want to pin the version in package.json :

npm install agent-browser
agent-browser install










Then use via package.json scripts or by invoking agent-browser directly.


### Homebrew (macOS)

brew install agent-browser
agent-browser install # Download Chrome from Chrome for Testing (first time only)











### Cargo (Rust)



cargo install agent-browser
agent-browser install # Download Chrome from Chrome for Testing (first time only)











### From Source



Requires Node.js 24+, pnpm 11+, and Rust.

git clone https://github.com/vercel-labs/agent-browser
cd agent-browser
pnpm install
pnpm build
pnpm build:native # Requires Rust (https://rustup.rs)
pnpm link --global # Makes agent-browser available globally
agent-browser install











### Linux Dependencies



On Linux, install system dependencies:

agent-browser install --with-deps











### Updating



Upgrade to the latest version:

agent-browser upgrade










Detects your installation method (npm, Homebrew, or Cargo) and runs the appropriate update command automatically.


### Requirements

- Chrome - Run agent-browser install to download Chrome from Chrome for Testing (Google's official automation channel). Existing Chrome, Brave, Playwright, and Puppeteer installations are detected automatically. No Playwright or Node.js required for the daemon.

- Node.js 24+ and pnpm 11+ - Only needed when building from source.

- Rust - Only needed when building from source (see From Source above).



## Quick Start



agent-browser open example.com
agent-browser snapshot # Get accessibility tree with refs
agent-browser click @e2 # Click by ref from snapshot
agent-browser fill @e3 " test@example.com " # Fill by ref
agent-browser get text @e1 # Get text by ref
agent-browser screenshot page.png
agent-browser close











### Traditional Selectors (also supported)



agent-browser click " #submit "
agent-browser fill " #email " " test@example.com "
agent-browser find role button click --name " Submit "











## Commands




### Core Commands



agent-browser open # Launch browser (no navigation); stays on about:blank
agent-browser open # Launch + navigate to URL (aliases: goto, navigate)
agent-browser click # Click element (--new-tab to open in new tab)
agent-browser dblclick # Double-click element
agent-browser focus # Focus element
agent-browser type # Type into element
agent-browser fill # Clear and fill
agent-browser press # Press key (Enter, Tab, Control+a) (alias: key)
agent-browser keyboard type # Type with real keystrokes (no selector, current focus)
agent-browser keyboard inserttext # Insert text without key events (no selector)
agent-browser keydown # Hold key down
agent-browser keyup # Release key
agent-browser hover # Hover element
agent-browser select # Select dropdown option
agent-browser check # Check checkbox
agent-browser uncheck # Uncheck checkbox
agent-browser scroll [px] # Scroll (up/down/left/right, --selector )
agent-browser scrollintoview # Scroll element into view (alias: scrollinto)
agent-browser drag # Drag and drop
agent-browser upload # Upload files
agent-browser screenshot [path] # Take screenshot (--full for full page, saves to a temporary directory if no path)
agent-browser screenshot --annotate # Annotated screenshot with numbered element labels
agent-browser screenshot --screenshot-dir ./shots # Save to custom directory
agent-browser screenshot --screenshot-format jpeg --screenshot-quality 80
agent-browser pdf # Save as PDF
agent-browser snapshot # Accessibility tree with refs (best for AI)
agent-browser eval # Run JavaScript (-b for base64, --stdin for piped input)
agent-browser connect # Connect to browser via CDP
agent-browser stream enable [--port ] # Start runtime WebSocket streaming
agent-browser stream status # Show runtime streaming state and bound port
agent-browser stream disable # Stop runtime WebSocket streaming
agent-browser close # Close browser (aliases: quit, exit)
agent-browser close --all # Close all active sessions
agent-browser chat " " # AI chat: natural language browser control (single-shot)
agent-browser chat # AI chat: interactive REPL mode











### Get Info



agent-browser get text # Get text content
agent-browser get html # Get innerHTML
agent-browser get value # Get input value
agent-browser get attr # Get attribute
agent-browser get title # Get page title
agent-browser get url # Get current URL
agent-browser get cdp-url # Get CDP WebSocket URL (for DevTools, debugging)
agent-browser get count # Count matching elements
agent-browser get box # Get bounding box
agent-browser get styles # Get computed styles











### Check State



agent-browser is visible # Check if visible
agent-browser is enabled # Check if enabled
agent-browser is checked # Check if checked











### Find Elements (Semantic Locators)



agent-browser find role [value] # By ARIA role
agent-browser find text # By text content
agent-browser find label [value] # By label
agent-browser find placeholder [value] # By placeholder
agent-browser find alt # By alt text
agent-browser find title # By title attr
agent-browser find testid [value] # By data-testid
agent-browser find first [value] # First match
agent-browser find last [value] # Last match
agent-browser find nth [value] # Nth match










Actions: click , fill , type , hover , focus , check , uncheck , text

Options: --name (filter role by accessible name), --exact (require exact text match)

Examples:

agent-browser find role button click --name " Submit "
agent-browser find text " Sign In " click
agent-browser find label " Email " fill " test@test.com "
agent-browser find first " .item " click
agent-browser find nth 2 " a " text











### Wait



agent-browser wait # Wait for element to be visible
agent-browser wait # Wait for time (milliseconds)
agent-browser wait --text " Welcome " # Wait for text to appear (substring match)
agent-browser wait --url " **/dash " # Wait for URL pattern
agent-browser wait --load networkidle # Wait for load state
agent-browser wait --fn " window.ready === true " # Wait for JS condition

# Wait for text/element to disappear
agent-browser wait --fn " !document.body.innerText.includes('Loading...') "
agent-browser wait " #spinner " --state hidden










Load states: load , domcontentloaded , networkidle


### Batch Execution

Execute multiple commands in a single invocation. Commands can be passed as
quoted arguments or piped as JSON via stdin. This avoids per-command process
startup overhead when running multi-step workflows.

# Argument mode: each quoted argument is a full command
agent-browser batch " open https://example.com " " snapshot -i " " screenshot "

# With --bail to stop on first error
agent-browser batch --bail " open https://example.com " " click @e1 " " screenshot "

# Stdin mode: pipe commands as JSON
echo ' [
["open", "https://example.com"],
["snapshot", "-i"],
["click", "@e1"],
["screenshot", "result.png"]
] ' | agent-browser batch --json











### Clipboard



agent-browser clipboard read # Read text from clipboard
agent-browser clipboard write " Hello, World! " # Write text to clipboard
agent-browser clipboard copy # Copy current selection (Ctrl+C)
agent-browser clipboard paste # Paste from clipboard (Ctrl+V)











### Mouse Control



agent-browser mouse move # Move mouse
agent-browser mouse down [button] # Press button (left/right/middle)
agent-browser mouse up [button] # Release button
agent-browser mouse wheel [dx] # Scroll wheel











### Browser Settings



agent-browser set viewport [scale] # Set viewport size (scale for retina, e.g. 2)
agent-browser set device # Emulate device ("iPhone 14")
agent-browser set geo # Set geolocation
agent-browser set offline [on | off] # Toggle offline mode
agent-browser set headers # Extra HTTP headers
agent-browser set credentials # HTTP basic auth
agent-browser set media [dark | light] # Emulate color scheme











### Cookies & Storage



agent-browser cookies # Get all cookies
agent-browser cookies set # Set cookie
agent-browser cookies set --curl # Import cookies from a Copy-as-cURL dump,
# JSON array, or bare Cookie header (auto-detected)
agent-browser cookies clear # Clear cookies

agent-browser storage local # Get all localStorage
agent-browser storage local # Get specific key
agent-browser storage local set # Set value
agent-browser storage local clear # Clear all

agent-browser storage session # Same for sessionStorage











### Network



agent-browser network route # Intercept requests
agent-browser network route --abort # Block requests
agent-browser network route --body # Mock response
agent-browser network route ' * ' --abort --resource-type script # Block scripts only
agent-browser network unroute [url] # Remove routes
agent-browser network requests # View tracked requests
agent-browser network requests --filter api # Filter requests
agent-browser network requests --type xhr,fetch # Filter by resource type
agent-browser network requests --method POST # Filter by HTTP method
agent-browser network requests --status 2xx # Filter by status (200, 2xx, 400-499)
agent-browser network request # View full request/response detail
agent-browser network har start # Start HAR recording
agent-browser network har stop [output.har] # Stop and save HAR (temp path if omitted)











### Tabs & Windows



agent-browser tab # List tabs (shows `tabId` and optional label)
agent-browser tab new [url] # New tab (optionally with URL)
agent-browser tab new --label docs [url] # New tab with a user-assigned label
agent-browser tab | label > # Switch to a tab by id or label
agent-browser tab close [t | label] # Close a tab (defaults to active)
agent-browser window new # New window










Tab ids are stable strings of the form t1 , t2 , t3 . They're never reused
within a session, so scripts and agents can keep referring to the same tab
even after other tabs are opened or closed. Positional integers like tab 2
are not accepted; the t prefix disambiguates handles from indices and
mirrors the @e1 convention used for element refs.

You can also assign a memorable label ( docs , app , admin ) and use it
interchangeably with the id. Labels are never auto-generated and never
rewritten on navigation — they're yours to name and keep:

agent-browser tab new --label docs https://docs.example.com
agent-browser tab docs # switch to the docs tab
agent-browser snapshot # populate refs for docs
agent-browser click @e3 # click uses docs's refs
agent-browser tab close docs # close by label











### Frames



agent-browser frame # Switch to iframe
agent-browser frame main # Back to main frame











### Dialogs



agent-browser dialog accept [text] # Accept (with optional prompt text)
agent-browser dialog dismiss # Dismiss
agent-browser dialog status # Check if a dialog is currently open










By default, alert and beforeunload dialogs are automatically accepted so they never block the agent. confirm and prompt dialogs still require explicit handling. Use --no-auto-dialog (or AGENT_BROWSER_NO_AUTO_DIALOG=1 ) to disable automatic handling.

When a JavaScript dialog is pending, all command responses include a warning field with the dialog type and message.


### Diff

agent-browser diff snapshot # Compare current vs last snapshot
agent-browser diff snapshot --baseline before.txt # Compare current vs saved snapshot file
agent-browser diff snapshot --selector " #main " --compact # Scoped snapshot diff
agent-browser diff screenshot --baseline before.png # Visual pixel diff against baseline
agent-browser diff screenshot --baseline b.png -o d.png # Save diff image to custom path
agent-browser diff screenshot --baseline b.png -t 0.2 # Adjust color threshold (0-1)
agent-browser diff url https://v1.com https://v2.com # Compare two URLs (snapshot diff)
agent-browser diff url https://v1.com https://v2.com --screenshot # Also visual diff
agent-browser diff url https://v1.com https://v2.com --wait-until networkidle # Custom wait strategy
agent-browser diff url https://v1.com https://v2.com --selector " #main " # Scope to element











### Debug



agent-browser trace start [path] # Start recording trace
agent-browser trace stop [path] # Stop and save trace
agent-browser profiler start # Start Chrome DevTools profiling
agent-browser profiler stop [path] # Stop and save profile (.json)
agent-browser console # View console messages (log, error, warn, info)
agent-browser console --json # JSON output with raw CDP args for programmatic access
agent-browser console --clear # Clear console
agent-browser errors # View page errors (uncaught JavaScript exceptions)
agent-browser errors --clear # Clear errors
agent-browser highlight # Highlight element
agent-browser inspect # Open Chrome DevTools for the active page
agent-browser state save # Save auth state
agent-browser state load # Load auth state
agent-browser state list # List saved state files
agent-browser state show # Show state summary
agent-browser state rename # Rename state file
agent-browser state clear [name] # Clear states for session
agent-browser state clear --all # Clear all saved states
agent-browser state clean --older-than # Delete old states











### Navigation



agent-browser back # Go back
agent-browser forward # Go forward
agent-browser reload # Reload page
agent-browser pushstate # SPA client-side nav; auto-detects window.next.router.push,
# falls back to history.pushState + popstate











### Pre-navigation setup



Some flows (SSR debug, auth cookies for protected origins, init scripts)
need state set up before the first navigation. Use open with no URL
to launch the browser, then stage cookies / routes / init scripts, then
navigate. batch sends it all in one CLI call:

agent-browser batch \
' ["open"] ' \
' ["network","route","*","--abort","--resource-type","script"] ' \
' ["cookies","set","--curl","cookies.curl","--domain","localhost"] ' \
' ["navigate","http://localhost:3000/target"] '










Without batch the same sequence is three commands that all reuse the
same daemon (fast, but not one turn).


### React / Web Vitals

Agent-browser ships with first-class React introspection and universal Web
Vitals metrics. The React commands need the React DevTools hook installed at
launch; Web Vitals and pushstate are framework-agnostic.

agent-browser open --enable react-devtools # Launch with React hook installed
agent-browser react tree # Full component tree
agent-browser react inspect # props, hooks, state, source
agent-browser react renders start # Begin fiber render recording
agent-browser react renders stop [--json] # Stop and print profile (--json for raw data)
agent-browser react suspense [--only-dynamic] [--json] # Suspense boundaries + classifier
# --only-dynamic hides the "static" list
agent-browser vitals [url] [--json] # LCP/CLS/TTFB/FCP/INP + React hydration phases










Each react ... subcommand requires --enable react-devtools to have been
passed at launch (the React DevTools installHook.js is embedded in the
binary). Without it the commands error with `React DevTools hook not installed


- relaunch with --enable react-devtools`.


Works on any React app — Next.js, Remix, Vite+React, CRA, TanStack Start,
React Native Web, etc. vitals and pushstate are framework-agnostic.


### Init scripts

agent-browser open --init-script # Register page init script before first navigation
# (repeatable; also AGENT_BROWSER_INIT_SCRIPTS env)
agent-browser addinitscript # Register at runtime (returns identifier)
agent-browser removeinitscript # Remove a previously registered init script











### Setup



agent-browser install # Download Chrome from Chrome for Testing (Google's official automation channel)
agent-browser install --with-deps # Also install system deps (Linux)
agent-browser upgrade # Upgrade agent-browser to the latest version
agent-browser doctor # Diagnose the install and auto-clean stale daemon files
agent-browser doctor --fix # Also run destructive repairs (reinstall Chrome, purge old state, ...)
agent-browser doctor --offline --quick # Skip network probes and the live launch test










doctor checks your environment, Chrome install, daemon state, config files,
encryption key, providers, network reachability, and runs a live headless
browser launch test. Stale socket/pid sidecar files are auto-cleaned. Output
is also available as --json for agents.


### Skills

agent-browser skills # List available skills
agent-browser skills list # Same as above
agent-browser skills get # Output a skill's full content
agent-browser skills get --full # Include references and templates
agent-browser skills get --all # Output every skill
agent-browser skills path [name] # Print skill directory path










Serves bundled skill content that always matches the installed CLI version. AI agents use this to get current instructions rather than relying on cached copies. Set AGENT_BROWSER_SKILLS_DIR to override the skills directory path.


## Authentication

agent-browser provides multiple ways to persist login sessions so you don't re-authenticate every run.


### Quick summary

Approach
Best for
Flag / Env




Chrome profile reuse
Reuse your existing Chrome login state (cookies, sessions) with zero setup
--profile / AGENT_BROWSER_PROFILE


Persistent profile
Full browser state (cookies, IndexedDB, service workers, cache) across restarts
--profile / AGENT_BROWSER_PROFILE


Session persistence
Auto-save/restore cookies + localStorage by name
--session-name / AGENT_BROWSER_SESSION_NAME


Import from your browser
Grab auth from a Chrome session you already logged into
--auto-connect + state save


State file
Load a previously saved state JSON on launch
--state / AGENT_BROWSER_STATE


Auth vault
Store credentials locally (encrypted), login by name
auth save / auth login




### Import auth from your browser



If you are already logged in to a site in Chrome, you can grab that auth state and reuse it:

# 1. Launch Chrome with remote debugging enabled
# macOS:
" /Applications/Google Chrome.app/Contents/MacOS/Google Chrome " --remote-debugging-port=9222
# Or use --auto-connect to discover an already-running Chrome

# 2. Connect and save the authenticated state
agent-browser --auto-connect state save ./my-auth.json

# 3. Use the saved auth in future sessions
agent-browser --state ./my-auth.json open https://app.example.com/dashboard

# 4. Or use --session-name for automatic persistence
agent-browser --session-name myapp state load ./my-auth.json
# From now on, --session-name myapp auto-saves/restores this state











Security notes:


- --remote-debugging-port exposes full browser control on localhost. Any local process can connect. Only use on trusted machines and close Chrome when done.

- State files contain session tokens in plaintext. Add them to .gitignore and delete when no longer needed. For encryption at rest, set AGENT_BROWSER_ENCRYPTION_KEY (see State Encryption ).



For full details on login flows, OAuth, 2FA, cookie-based auth, and the auth vault, see the Authentication docs.


## Sessions

Run multiple isolated browser instances:

# Different sessions
agent-browser --session agent1 open site-a.com
agent-browser --session agent2 open site-b.com

# Or via environment variable
AGENT_BROWSER_SESSION=agent1 agent-browser click " #btn "

# List active sessions
agent-browser session list
# Output:
# Active sessions:
# -> default
# agent1

# Show current session
agent-browser session










Each session has its own:


- Browser instance

- Cookies and storage

- Navigation history

- Authentication state



## Chrome Profile Reuse

The fastest way to use your existing login state: pass a Chrome profile name to --profile :

# List available Chrome profiles
agent-browser profiles

# Reuse your default Chrome profile's login state
agent-browser --profile Default open https://gmail.com

# Use a named profile (by display name or directory name)
agent-browser --profile " Work " open https://app.example.com

# Or via environment variable
AGENT_BROWSER_PROFILE=Default agent-browser open https://gmail.com










This copies your Chrome profile to a temp directory (read-only snapshot, no changes to your original profile), so the browser launches with your existing cookies and sessions.


Note: On Windows, close Chrome before using --profile if Chrome is running, as some profile files may be locked.



## Persistent Profiles

For a persistent custom profile directory that stores state across browser restarts, pass a path to --profile :

# Use a persistent profile directory
agent-browser --profile ~ /.myapp-profile open myapp.com

# Login once, then reuse the authenticated session
agent-browser --profile ~ /.myapp-profile open myapp.com/dashboard

# Or via environment variable
AGENT_BROWSER_PROFILE= ~ /.myapp-profile agent-browser open myapp.com










The profile directory stores:


- Cookies and localStorage

- IndexedDB data

- Service workers

- Browser cache

- Login sessions


Tip : Use different profile paths for different projects to keep their browser state isolated.


## Session Persistence

Alternatively, use --session-name to automatically save and restore cookies and localStorage across browser restarts:

# Auto-save/load state for "twitter" session
agent-browser --session-name twitter open twitter.com

# Login once, then state persists automatically
# State files stored in ~/.agent-browser/sessions/

# Or via environment variable
export AGENT_BROWSER_SESSION_NAME=twitter
agent-browser open twitter.com











### State Encryption



Encrypt saved session data at rest with AES-256-GCM:

# Generate key: openssl rand -hex 32
export AGENT_BROWSER_ENCRYPTION_KEY=

# State files are now encrypted automatically
agent-browser --session-name secure open example.com













Variable
Description




AGENT_BROWSER_SESSION_NAME
Auto-save/load state persistence name


AGENT_BROWSER_ENCRYPTION_KEY
64-char hex key for AES-256-GCM encryption


AGENT_BROWSER_STATE_EXPIRE_DAYS
Auto-delete states older than N days (default: 30)




## Security



agent-browser includes security features for safe AI agent deployments. All features are opt-in -- existing workflows are unaffected until you explicitly enable a feature:


- Authentication Vault -- Store credentials locally (always encrypted), reference by name. The LLM never sees passwords. auth login navigates with load and then waits for login form selectors to appear (SPA-friendly, timeout follows the default action timeout). A key is auto-generated at ~/.agent-browser/.encryption-key if AGENT_BROWSER_ENCRYPTION_KEY is not set: echo "pass" | agent-browser auth save github --url https://github.com/login --username user --password-stdin then agent-browser auth login github

- Content Boundary Markers -- Wrap page output in delimiters so LLMs can distinguish tool output from untrusted content: --content-boundaries

- Domain Allowlist -- Restrict navigation to trusted domains (wildcards like *.example.com also match the bare domain): --allowed-domains "example.com,*.example.com" . Sub-resource requests (scripts, images, fetch) and WebSocket/EventSource connections to non-allowed domains are also blocked. Include any CDN domains your target pages depend on (e.g., *.cdn.example.com ).

- Action Policy -- Gate destructive actions with a static policy file: --action-policy ./policy.json

- Action Confirmation -- Require explicit approval for sensitive action categories: --confirm-actions eval,download

- Output Length Limits -- Prevent context flooding: --max-output 50000





Variable
Description




AGENT_BROWSER_CONTENT_BOUNDARIES
Wrap page output in boundary markers


AGENT_BROWSER_MAX_OUTPUT
Max characters for page output


AGENT_BROWSER_ALLOWED_DOMAINS
Comma-separated allowed domain patterns


AGENT_BROWSER_ACTION_POLICY
Path to action policy JSON file


AGENT_BROWSER_CONFIRM_ACTIONS
Action categories requiring confirmation


AGENT_BROWSER_CONFIRM_INTERACTIVE
Enable interactive confirmation prompts



See Security documentation for details.


## Snapshot Options

The snapshot command supports filtering to reduce output size:

agent-browser snapshot # Full accessibility tree
agent-browser snapshot -i # Interactive elements only (buttons, inputs, links)
agent-browser snapshot -i --urls # Interactive elements with link URLs
agent-browser snapshot -c # Compact (remove empty structural elements)
agent-browser snapshot -d 3 # Limit depth to 3 levels
agent-browser snapshot -s " #main " # Scope to CSS selector
agent-browser snapshot -i -c -d 5 # Combine options













Option
Description




-i, --interactive
Only show interactive elements (buttons, links, inputs)


-u, --urls
Include href URLs for link elements


-c, --compact
Remove empty structural elements


-d, --depth
Limit tree depth


-s, --selector
Scope to CSS selector




## Annotated Screenshots



The --annotate flag overlays numbered labels on interactive elements in the screenshot. Each label [N] corresponds to ref @eN , so the same refs work for both visual and text-based workflows.

Annotated screenshots are supported on the CDP-backed browser path (Chrome/Lightpanda). The Safari/WebDriver backend does not yet support --annotate .

agent-browser screenshot --annotate
# -> Screenshot saved to /tmp/screenshot-2026-02-17T12-00-00-abc123.png
# [1] @e1 button "Submit"
# [2] @e2 link "Home"
# [3] @e3 textbox "Email"










After an annotated screenshot, refs are cached so you can immediately interact with elements:

agent-browser screenshot --annotate ./page.png
agent-browser click @e2 # Click the "Home" link labeled [2]










This is useful for multimodal AI models that can reason about visual layout, unlabeled icon buttons, canvas elements, or visual state that the text accessibility tree cannot capture.


## Options

Option
Description




--session
Use isolated session (or AGENT_BROWSER_SESSION env)


--session-name
Auto-save/restore session state (or AGENT_BROWSER_SESSION_NAME env)


--profile
Chrome profile name or persistent directory path (or AGENT_BROWSER_PROFILE env)


--state
Load storage state from JSON file (or AGENT_BROWSER_STATE env)


--headers
Set HTTP headers scoped to the URL's origin


--executable-path
Custom browser executable (or AGENT_BROWSER_EXECUTABLE_PATH env)


--extension
Load browser extension (repeatable; or AGENT_BROWSER_EXTENSIONS env)


--init-script
Register a page init script before the first navigation (repeatable; or AGENT_BROWSER_INIT_SCRIPTS env)


--enable
Built-in init scripts: react-devtools (repeatable or comma-list; or AGENT_BROWSER_ENABLE env)


--args
Browser launch args, comma or newline separated (or AGENT_BROWSER_ARGS env)


--user-agent
Custom User-Agent string (or AGENT_BROWSER_USER_AGENT env)


--proxy
Proxy server URL with optional auth (or AGENT_BROWSER_PROXY env)


--proxy-bypass
Hosts to bypass proxy (or AGENT_BROWSER_PROXY_BYPASS env)


--ignore-https-errors
Ignore HTTPS certificate errors (useful for self-signed certs)


--allow-file-access
Allow file:// URLs to access local files (Chromium only)


-p, --provider
Cloud browser provider (or AGENT_BROWSER_PROVIDER env)


--device
iOS device name, e.g. "iPhone 15 Pro" (or AGENT_BROWSER_IOS_DEVICE env)


--json
JSON output (for agents)


--annotate
Annotated screenshot with numbered element labels (or AGENT_BROWSER_ANNOTATE env)


--screenshot-dir
Default screenshot output directory (or AGENT_BROWSER_SCREENSHOT_DIR env)


--screenshot-quality
JPEG quality 0-100 (or AGENT_BROWSER_SCREENSHOT_QUALITY env)


--screenshot-format
Screenshot format: png , jpeg (or AGENT_BROWSER_SCREENSHOT_FORMAT env)


--headed
Show browser window (not headless) (or AGENT_BROWSER_HEADED env)


--cdp
Connect via Chrome DevTools Protocol (port or WebSocket URL)


--auto-connect
Auto-discover and connect to running Chrome (or AGENT_BROWSER_AUTO_CONNECT env)


--color-scheme
Color scheme: dark , light , no-preference (or AGENT_BROWSER_COLOR_SCHEME env)


--download-path
Default download directory (or AGENT_BROWSER_DOWNLOAD_PATH env)


--content-boundaries
Wrap page output in boundary markers for LLM safety (or AGENT_BROWSER_CONTENT_BOUNDARIES env)


--max-output
Truncate page output to N characters (or AGENT_BROWSER_MAX_OUTPUT env)


--allowed-domains
Comma-separated allowed domain patterns (or AGENT_BROWSER_ALLOWED_DOMAINS env)


--action-policy
Path to action policy JSON file (or AGENT_BROWSER_ACTION_POLICY env)


--confirm-actions
Action categories requiring confirmation (or AGENT_BROWSER_CONFIRM_ACTIONS env)


--confirm-interactive
Interactive confirmation prompts; auto-denies if stdin is not a TTY (or AGENT_BROWSER_CONFIRM_INTERACTIVE env)


--engine
Browser engine: chrome (default), lightpanda (or AGENT_BROWSER_ENGINE env)


--no-auto-dialog
Disable automatic dismissal of alert / beforeunload dialogs (or AGENT_BROWSER_NO_AUTO_DIALOG env)


--model
AI model for chat command (or AI_GATEWAY_MODEL env)


-v , --verbose
Show tool commands and their raw output (chat)


-q , --quiet
Show only AI text responses, hide tool calls (chat)


--config
Use a custom config file (or AGENT_BROWSER_CONFIG env)


--debug
Debug output




## Observability Dashboard



Monitor agent-browser sessions in real time with a local web dashboard showing a live viewport and command activity feed.

# Start the dashboard server (runs in background on port 4848)
agent-browser dashboard start
agent-browser dashboard start --port 8080 # Custom port

# All sessions are automatically visible in the dashboard
agent-browser open example.com

# Stop the dashboard
agent-browser dashboard stop










The dashboard runs as a standalone background process on port 4848, independent of browser sessions. It stays available even when no sessions are running, and it works from http://localhost:4848 or a proxied/forwarded URL that reaches the dashboard server, such as https://dashboard.agent-browser.localhost or a Coder workspace URL. The browser stays on the dashboard origin; session-specific tabs, status, and stream traffic are proxied internally, so session ports do not need to be exposed.

The dashboard displays:


- Live viewport -- real-time JPEG frames from the browser

- Activity feed -- chronological command/result stream with timing and expandable details

- Console output -- browser console messages (log, warn, error)

- Session creation -- create new sessions from the UI with local engines (Chrome, Lightpanda) or cloud providers (AgentCore, Browserbase, Browserless, Browser Use, Kernel)

- AI Chat -- chat with an AI assistant directly in the dashboard (requires Vercel AI Gateway configuration)



### AI Chat

The dashboard includes an optional AI chat panel powered by the Vercel AI Gateway. The same functionality is available directly from the CLI via the chat command. Set these environment variables to enable AI chat:

export AI_GATEWAY_API_KEY=gw_your_key_here
export AI_GATEWAY_MODEL=anthropic/claude-sonnet-4.6 # optional, this is the default
export AI_GATEWAY_URL=https://ai-gateway.vercel.sh # optional, this is the default










CLI usage:

agent-browser chat " open google.com and search for cats " # Single-shot
agent-browser chat # Interactive REPL
agent-browser -q chat " summarize this page " # Quiet mode (text only)
agent-browser -v chat " fill in the login form " # Verbose (show command output)
agent-browser --model openai/gpt-4o chat " take a screenshot " # Override model










The chat command translates natural language instructions into agent-browser commands, executes them, and streams the AI response. In interactive mode, type quit to exit. Use --json for structured output suitable for agent consumption.

Dashboard usage:

The Chat tab is always visible in the dashboard. When AI_GATEWAY_API_KEY is set, the Rust server proxies requests to the gateway and streams responses back using the Vercel AI SDK's UI Message Stream protocol. Without the key, sending a message shows an error inline.


## Configuration

Create an agent-browser.json file to set persistent defaults instead of repeating flags on every command.

Locations (lowest to highest priority):


- ~/.agent-browser/config.json -- user-level defaults

- ./agent-browser.json -- project-level overrides (in working directory)

- AGENT_BROWSER_* environment variables override config file values

- CLI flags override everything


Example agent-browser.json :

{
"headed" : true ,
"proxy" : " http://localhost:8080 " ,
"profile" : " ./browser-data " ,
"userAgent" : " my-agent/1.0 " ,
"ignoreHttpsErrors" : true
}










Use --config or AGENT_BROWSER_CONFIG to load a specific config file instead of the defaults:

agent-browser --config ./ci-config.json open example.com
AGENT_BROWSER_CONFIG=./ci-config.json agent-browser open example.com










All options from the table above can be set in the config file using camelCase keys (e.g., --executable-path becomes "executablePath" , --proxy-bypass becomes "proxyBypass" ). Unknown keys are ignored for forward compatibility.

A JSON Schema is available for IDE autocomplete and validation. Add a $schema key to your config file to enable it:

{
"$schema" : " https://agent-browser.dev/schema.json " ,
"headed" : true
}










Boolean flags accept an optional true / false value to override config settings. For example, --headed false disables "headed": true from config. A bare --headed is equivalent to --headed true .

Auto-discovered config files that are missing are silently ignored. If --config points to a missing or invalid file, agent-browser exits with an error. Extensions from user and project configs are merged (concatenated), not replaced.


Tip: If your project-level agent-browser.json contains environment-specific values (paths, proxies), consider adding it to .gitignore .



## Default Timeout

The default timeout for standard operations (clicks, waits, fills, etc.) is 25 seconds. This is intentionally below the CLI's 30-second IPC read timeout so that the daemon returns a proper error instead of the CLI timing out with EAGAIN.

Override the default timeout via environment variable:

# Set a longer timeout for slow pages (in milliseconds)
export AGENT_BROWSER_DEFAULT_TIMEOUT=45000











Note: Setting this above 30000 (30s) may cause EAGAIN errors on slow operations because the CLI's read timeout will expire before the daemon responds. The CLI retries transient errors automatically, but response times will increase.





Variable
Description




AGENT_BROWSER_DEFAULT_TIMEOUT
Default operation timeout in ms (default: 25000)




## Selectors

### Refs (Recommended for AI)



Refs provide deterministic element selection from snapshots:

# 1. Get snapshot with refs
agent-browser snapshot
# Output:
# - heading "Example Domain" [ref=e1] [level=1]
# - button "Submit" [ref=e2]
# - textbox "Email" [ref=e3]
# - link "Learn more" [ref=e4]

# 2. Use refs to interact
agent-browser click @e2 # Click the button
agent-browser fill @e3 " test@example.com " # Fill the textbox
agent-browser get text @e1 # Get heading text
agent-browser hover @e4 # Hover the link










Why use refs?


- Deterministic : Ref points to exact element from snapshot

- Fast : No DOM re-query needed

- AI-friendly : Snapshot + ref workflow is optimal for LLMs



### CSS Selectors

agent-browser click " #id "
agent-browser click " .class "
agent-browser click " div > button "











### Text & XPath



agent-browser click " text=Submit "
agent-browser click " xpath=//button "











### Semantic Locators



agent-browser find role button click --name " Submit "
agent-browser find label " Email " fill " test@test.com "











## Agent Mode



Use --json for machine-readable output:

agent-browser snapshot --json
# Returns: {"success":true,"data":{"snapshot":"...","refs":{"e1":{"role":"heading","name":"Title"},...}}}

agent-browser get text @e1 --json
agent-browser is visible @e2 --json











### Optimal AI Workflow



# 1. Navigate and get snapshot
agent-browser open example.com
agent-browser snapshot -i --json # AI parses tree and refs

# 2. AI identifies target refs from snapshot
# 3. Execute actions using refs
agent-browser click @e2
agent-browser fill @e3 " input text "

# 4. Get new snapshot if page changed
agent-browser snapshot -i --json











### Command Chaining



Commands can be chained with && in a single shell invocation. The browser persists via a background daemon, so chaining is safe and more efficient:

# Open, wait for load, and snapshot in one call
agent-browser open example.com && agent-browser wait --load networkidle && agent-browser snapshot -i

# Chain multiple interactions
agent-browser fill @e1 " user@example.com " && agent-browser fill @e2 " pass " && agent-browser click @e3

# Navigate and screenshot
agent-browser open example.com && agent-browser wait --load networkidle && agent-browser screenshot page.png










Use && when you don't need intermediate output. Run commands separately when you need to parse output first (e.g., snapshot to discover refs before interacting).


## Headed Mode

Show the browser window for debugging:

agent-browser open example.com --headed










This opens a visible browser window instead of running headless.


Note: Browser extensions work in both headed and headless mode (Chrome's --headless=new ).



## Authenticated Sessions

Use --headers to set HTTP headers for a specific origin, enabling authentication without login flows:

# Headers are scoped to api.example.com only
agent-browser open api.example.com --headers ' {"Authorization": "Bearer "} '

# Requests to api.example.com include the auth header
agent-browser snapshot -i --json
agent-browser click @e2

# Navigate to another domain - headers are NOT sent (safe!)
agent-browser open other-site.com










This is useful for:


- Skipping login flows - Authenticate via headers instead of UI

- Switching users - Start new sessions with different auth tokens

- API testing - Access protected endpoints directly

- Security - Headers are scoped to the origin, not leaked to other domains


To set headers for multiple origins, use --headers with each open command:

agent-browser open api.example.com --headers ' {"Authorization": "Bearer token1"} '
agent-browser open api.acme.com --headers ' {"Authorization": "Bearer token2"} '










For global headers (all domains), use set headers :

agent-browser set headers ' {"X-Custom-Header": "value"} '











## Custom Browser Executable



Use a custom browser executable instead of the bundled Chromium. This is useful for:


- Serverless deployment : Use lightweight Chromium builds like @sparticuz/chromium (~50MB vs ~684MB)

- System browsers : Use an existing Chrome/Chromium installation

- Custom builds : Use modified browser builds



### CLI Usage

# Via flag
agent-browser --executable-path /path/to/chromium open example.com

# Via environment variable
AGENT_BROWSER_EXECUTABLE_PATH=/path/to/chromium agent-browser open example.com











### Serverless (Vercel)



Run agent-browser + Chrome in an ephemeral Vercel Sandbox microVM. No external server needed:

import { Sandbox } from "@vercel/sandbox" ;

const sandbox = await Sandbox . create ( { runtime : "node24" } ) ;
await sandbox . runCommand ( "agent-browser" , [ "open" , "https://example.com" ] ) ;
const result = await sandbox . runCommand ( "agent-browser" , [ "screenshot" , "--json" ] ) ;
await sandbox . stop ( ) ;










See the environments example for a working demo with a UI and deploy-to-Vercel button.


### Serverless (AWS Lambda)

import chromium from '@sparticuz/chromium' ;
import { execSync } from 'child_process' ;

export async function handler ( ) {
const executablePath = await chromium . executablePath ( ) ;
const result = execSync (
`AGENT_BROWSER_EXECUTABLE_PATH= ${ executablePath } agent-browser open https://example.com && agent-browser snapshot -i --json` ,
{ encoding : 'utf-8' }
) ;
return JSON . parse ( result ) ;
}











## Local Files



Open and interact with local files (PDFs, HTML, etc.) using file:// URLs:

# Enable file access (required for JavaScript to access local files)
agent-browser --allow-file-access open file:///path/to/document.pdf
agent-browser --allow-file-access open file:///path/to/page.html

# Take screenshot of a local PDF
agent-browser --allow-file-access open file:///Users/me/report.pdf
agent-browser screenshot report.png










The --allow-file-access flag adds Chromium flags ( --allow-file-access-from-files , --allow-file-access ) that allow file:// URLs to:


- Load and render local files

- Access other local files via JavaScript (XHR, fetch)

- Load local resources (images, scripts, stylesheets)


Note: This flag only works with Chromium. For security, it's disabled by default.


## CDP Mode

Connect to an existing browser via Chrome DevTools Protocol:

# Start Chrome with: google-chrome --remote-debugging-port=9222

# Connect once, then run commands without --cdp
agent-browser connect 9222
agent-browser snapshot
agent-browser tab
agent-browser close

# Or pass --cdp on each command
agent-browser --cdp 9222 snapshot

# Connect to remote browser via WebSocket URL
agent-browser --cdp " wss://your-browser-service.com/cdp?token=... " snapshot










The --cdp flag accepts either:


- A port number (e.g., 9222 ) for local connections via http://localhost:{port}

- A full WebSocket URL (e.g., wss://... or ws://... ) for remote browser services


This enables control of:


- Electron apps

- Chrome/Chromium instances with remote debugging

- WebView2 applications

- Any browser exposing a CDP endpoint



### Auto-Connect

Use --auto-connect to automatically discover and connect to a running Chrome instance without specifying a port:

# Auto-discover running Chrome with remote debugging
agent-browser --auto-connect open example.com
agent-browser --auto-connect snapshot

# Or via environment variable
AGENT_BROWSER_AUTO_CONNECT=1 agent-browser snapshot










Auto-connect discovers Chrome by:


- Reading Chrome's DevToolsActivePort file from the default user data directory

- Falling back to probing common debugging ports (9222, 9229)

- If HTTP-based discovery ( /json/version , /json/list ) fails, falling back to a direct WebSocket connection


This is useful when:


- Chrome 144+ has remote debugging enabled via chrome://inspect/#remote-debugging (which uses a dynamic port)

- You want a zero-configuration connection to your existing browser

- You don't want to track which port Chrome is using



## Streaming (Browser Preview)

Stream the browser viewport via WebSocket for live preview or "pair browsing" where a human can watch and interact alongside an AI agent.


### Streaming

Every session automatically starts a WebSocket stream server on an OS-assigned port. Use stream status to see the bound port and connection state:

agent-browser stream status










To bind to a specific port, set AGENT_BROWSER_STREAM_PORT :

AGENT_BROWSER_STREAM_PORT=9223 agent-browser open example.com










You can also manage streaming at run

…(truncated)
