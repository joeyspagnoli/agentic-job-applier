# Microsoft Playwright MCP README

Source: https://github.com/microsoft/playwright-mcp/blob/main/README.md

- playwright-mcp/README.md at main · microsoft/playwright-mcp · GitHub

































































































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

































microsoft

/

playwright-mcp


Public












Notifications
You must be signed in to change notification settings

- Fork
2.7k

- Star
33k












- Code

- Issues
2

- Pull requests
4

- Actions

- Models

- Security and quality
0

- Insights







Additional navigation options







- Code

- Issues

- Pull requests

- Actions

- Models

- Security and quality

- Insights
































## Collapse file tree

## Files



main



Search this repository (forward slash) forward slash /









- .claude
- .devcontainer
- .github
- src
- tests
- .gitignore
- .npmignore
- CLAUDE.md
- CONTRIBUTING.md
- Dockerfile
- LICENSE
- README.md
- SECURITY.md
- cli.js
- config.d.ts
- index.d.ts
- index.js
- package-lock.json
- package.json
- playwright.config.ts
- roll.js
- server.json
- update-readme.js





## Breadcrumbs

- playwright-mcp
/
# README.md

Copy path

Blame

More file actions

Blame

More file actions






## Latest commit

deejay1



Fix docker entry point in README.md ( #1610 )

Open commit details success

May 7, 2026

55eada9  ·  May 7, 2026


## History

History Open commit details

History

1530 lines (1180 loc) · 56.5 KB


## Breadcrumbs

- playwright-mcp
/
# README.md

Top


## File metadata and controls

- Preview
- Code
- Blame


1530 lines (1180 loc) · 56.5 KB





Raw

Copy raw file

Download raw file

You must be signed in to make or propose changes

More edit options

Outline Edit and raw actions




## Playwright MCP



A Model Context Protocol (MCP) server that provides browser automation capabilities using Playwright . This server enables LLMs to interact with web pages through structured accessibility snapshots, bypassing the need for screenshots or visually-tuned models.


### Playwright MCP vs Playwright CLI

This package provides MCP interface into Playwright. If you are using a coding agent , you might benefit from using the CLI+SKILLS instead.


- CLI : Modern coding agents increasingly favor CLI–based workflows exposed as SKILLs over MCP because CLI invocations are more token-efficient: they avoid loading large tool schemas and verbose accessibility trees into the model context, allowing agents to act through concise, purpose-built commands. This makes CLI + SKILLs better suited for high-throughput coding agents that must balance browser automation with large codebases, tests, and reasoning within limited context windows.
Learn more about Playwright CLI with SKILLS .

- MCP : MCP remains relevant for specialized agentic loops that benefit from persistent state, rich introspection, and iterative reasoning over page structure, such as exploratory automation, self-healing tests, or long-running autonomous workflows where maintaining continuous browser context outweighs token cost concerns.



### Key Features

- Fast and lightweight . Uses Playwright's accessibility tree, not pixel-based input.

- LLM-friendly . No vision models needed, operates purely on structured data.

- Deterministic tool application . Avoids ambiguity common with screenshot-based approaches.



### Requirements




- Node.js 18 or newer

- VS Code, Cursor, Windsurf, Claude Desktop, Goose, Junie or any other MCP client




### Getting started



First, install the Playwright MCP server with your client.

Standard config works in most of the tools:

{
"mcpServers" : {
"playwright" : {
"command" : "npx" ,
"args" : [
"@playwright/mcp@latest"
]
}
}
}


Amp
Add via the Amp VS Code extension settings screen or by updating your settings.json file:

"amp.mcpServers" : {
"playwright" : {
"command" : " npx " ,
"args" : [
" @playwright/mcp@latest "
]
}
}










Amp CLI Setup:

Add via the amp mcp add command below

amp mcp add playwright -- npx @playwright/mcp@latest












Antigravity
Add via the Antigravity settings or by updating your configuration file:

{
"mcpServers" : {
"playwright" : {
"command" : " npx " ,
"args" : [
" @playwright/mcp@latest "
]
}
}
}












Claude Code
Use the Claude Code CLI to add the Playwright MCP server:

claude mcp add playwright npx @playwright/mcp@latest












Claude Desktop
Follow the MCP install guide , use the standard config above.



Cline
Follow the instruction in the section Configuring MCP Servers

Example: Local Setup

Add the following to your cline_mcp_settings.json file:

{
"mcpServers" : {
"playwright" : {
"type" : " stdio " ,
"command" : " npx " ,
"timeout" : 30 ,
"args" : [
" -y " ,
" @playwright/mcp@latest "
],
"disabled" : false
}
}
}












Codex
Use the Codex CLI to add the Playwright MCP server:

codex mcp add playwright npx " @playwright/mcp@latest "










Alternatively, create or edit the configuration file ~/.codex/config.toml and add:

[ mcp_servers . playwright ]
command = " npx "
args = [ " @playwright/mcp@latest " ]










For more information, see the Codex MCP documentation .



Copilot
Use the Copilot CLI to interactively add the Playwright MCP server:

/mcp add










Alternatively, create or edit the configuration file ~/.copilot/mcp-config.json and add:

{
"mcpServers" : {
"playwright" : {
"type" : " local " ,
"command" : " npx " ,
"tools" : [
" * "
],
"args" : [
" @playwright/mcp@latest "
]
}
}
}










For more information, see the Copilot CLI documentation .



Cursor

#### Click the button to install:




#### Or install manually:

Go to Cursor Settings -> MCP -> Add new MCP Server . Name to your liking, use command type with the command npx @playwright/mcp@latest . You can also verify config or add command like arguments via clicking Edit .



Factory
Use the Factory CLI to add the Playwright MCP server:

droid mcp add playwright " npx @playwright/mcp@latest "










Alternatively, type /mcp within Factory droid to open an interactive UI for managing MCP servers.

For more information, see the Factory MCP documentation .



Gemini CLI
Follow the MCP install guide , use the standard config above.



Goose

#### Click the button to install:




#### Or install manually:

Go to Advanced settings -> Extensions -> Add custom extension . Name to your liking, use type STDIO , and set the command to npx @playwright/mcp . Click "Add Extension".



Junie
To add the Playwright MCP server in Junie CLI:


- Type /mcp

- Press Ctrl+A to add a new MCP server

- Select Playwright from the list


Alternatively, add to .junie/mcp/mcp.json :

{
"mcpServers" : {
"Playwright" : {
"command" : " npx " ,
"args" : [
" -y " ,
" @playwright/mcp@latest "
]
}
}
}










For more information, see the Junie MCP configuration documentation .



Kiro

Follow the MCP Servers documentation . For example in .kiro/settings/mcp.json :

{
"mcpServers" : {
"playwright" : {
"command" : " npx " ,
"args" : [
" @playwright/mcp@latest "
]
}
}
}












LM Studio

#### Click the button to install:


#### Or install manually:

Go to Program in the right sidebar -> Install -> Edit mcp.json . Use the standard config above.



opencode
Follow the MCP Servers documentation . For example in ~/.config/opencode/opencode.json :

{
"$schema" : " https://opencode.ai/config.json " ,
"mcp" : {
"playwright" : {
"type" : " local " ,
"command" : [
" npx " ,
" @playwright/mcp@latest "
],
"enabled" : true
}
}
}













Qodo Gen
Open Qodo Gen chat panel in VSCode or IntelliJ → Connect more tools → + Add new MCP → Paste the standard config above.

Click Save .



VS Code

#### Click the button to install:




#### Or install manually:

Follow the MCP install guide , use the standard config above. You can also install the Playwright MCP server using the VS Code CLI:

# For VS Code
code --add-mcp ' {"name":"playwright","command":"npx","args":["@playwright/mcp@latest"]} '










After installation, the Playwright MCP server will be available for use with your GitHub Copilot agent in VS Code.



Warp
Go to Settings -> AI -> Manage MCP Servers -> + Add to add an MCP Server . Use the standard config above.

Alternatively, use the slash command /add-mcp in the Warp prompt and paste the standard config from above:

{
"mcpServers" : {
"playwright" : {
"command" : "npx" ,
"args" : [
"@playwright/mcp@latest"
]
}
}
}












Windsurf
Follow Windsurf MCP documentation . Use the standard config above.



### Configuration

Playwright MCP server supports following arguments. They can be provided in the JSON configuration above, as a part of the "args" list:




Option
Description




--allowed-hosts <hosts...>
comma-separated list of hosts this server is allowed to serve from. Defaults to the host the server is bound to. Pass '*' to disable the host check.
env PLAYWRIGHT_MCP_ALLOWED_HOSTS


--allowed-origins
semicolon-separated list of TRUSTED origins to allow the browser to request. Default is to allow all. Important: does not serve as a security boundary and does not affect redirects.
env PLAYWRIGHT_MCP_ALLOWED_ORIGINS


--allow-unrestricted-file-access
allow access to files outside of the workspace roots. Also allows unrestricted access to file:// URLs. By default access to file system is restricted to workspace root directories (or cwd if no roots are configured) only, and navigation to file:// URLs is blocked.
env PLAYWRIGHT_MCP_ALLOW_UNRESTRICTED_FILE_ACCESS


--blocked-origins
semicolon-separated list of origins to block the browser from requesting. Blocklist is evaluated before allowlist. If used without the allowlist, requests not matching the blocklist are still allowed. Important: does not serve as a security boundary and does not affect redirects.
env PLAYWRIGHT_MCP_BLOCKED_ORIGINS


--block-service-workers
block service workers
env PLAYWRIGHT_MCP_BLOCK_SERVICE_WORKERS


--browser
browser or chrome channel to use, possible values: chrome, firefox, webkit, msedge.
env PLAYWRIGHT_MCP_BROWSER


--caps
comma-separated list of additional capabilities to enable, possible values: vision, pdf, devtools.
env PLAYWRIGHT_MCP_CAPS


--cdp-endpoint
CDP endpoint to connect to.
env PLAYWRIGHT_MCP_CDP_ENDPOINT


--cdp-header <headers...>
CDP headers to send with the connect request, multiple can be specified.
env PLAYWRIGHT_MCP_CDP_HEADER


--cdp-timeout
timeout in milliseconds for connecting to CDP endpoint, defaults to 30000ms
env PLAYWRIGHT_MCP_CDP_TIMEOUT


--codegen
specify the language to use for code generation, possible values: "typescript", "none". Default is "typescript".
env PLAYWRIGHT_MCP_CODEGEN


--config
path to the configuration file.
env PLAYWRIGHT_MCP_CONFIG


--console-level
level of console messages to return: "error", "warning", "info", "debug". Each level includes the messages of more severe levels.
env PLAYWRIGHT_MCP_CONSOLE_LEVEL


--device
device to emulate, for example: "iPhone 15"
env PLAYWRIGHT_MCP_DEVICE


--executable-path
path to the browser executable.
env PLAYWRIGHT_MCP_EXECUTABLE_PATH


--extension
Connect to a running browser instance (Edge/Chrome only). Requires the "Playwright Extension" to be installed.
env PLAYWRIGHT_MCP_EXTENSION


--endpoint
Bound browser endpoint to connect to.
env PLAYWRIGHT_MCP_ENDPOINT


--grant-permissions <permissions...>
List of permissions to grant to the browser context, for example "geolocation", "clipboard-read", "clipboard-write".
env PLAYWRIGHT_MCP_GRANT_PERMISSIONS


--headless
run browser in headless mode, headed by default
env PLAYWRIGHT_MCP_HEADLESS


--host
host to bind server to. Default is localhost. Use 0.0.0.0 to bind to all interfaces.
env PLAYWRIGHT_MCP_HOST


--ignore-https-errors
ignore https errors
env PLAYWRIGHT_MCP_IGNORE_HTTPS_ERRORS


--init-page <path...>
path to TypeScript file to evaluate on Playwright page object
env PLAYWRIGHT_MCP_INIT_PAGE


--init-script <path...>
path to JavaScript file to add as an initialization script. The script will be evaluated in every page before any of the page's scripts. Can be specified multiple times.
env PLAYWRIGHT_MCP_INIT_SCRIPT


--isolated
keep the browser profile in memory, do not save it to disk.
env PLAYWRIGHT_MCP_ISOLATED


--image-responses
whether to send image responses to the client. Can be "allow" or "omit", Defaults to "allow".
env PLAYWRIGHT_MCP_IMAGE_RESPONSES


--no-sandbox
disable the sandbox for all process types that are normally sandboxed.
env PLAYWRIGHT_MCP_NO_SANDBOX


--output-dir
path to the directory for output files.
env PLAYWRIGHT_MCP_OUTPUT_DIR


--output-mode
whether to save snapshots, console messages, network logs to a file or to the standard output. Can be "file" or "stdout". Default is "stdout".
env PLAYWRIGHT_MCP_OUTPUT_MODE


--port
port to listen on for SSE transport.
env PLAYWRIGHT_MCP_PORT


--proxy-bypass
comma-separated domains to bypass proxy, for example ".com,chromium.org,.domain.com"
env PLAYWRIGHT_MCP_PROXY_BYPASS


--proxy-server
specify proxy server, for example " http://myproxy:3128 " or "socks5://myproxy:8080"
env PLAYWRIGHT_MCP_PROXY_SERVER


--sandbox
enable the sandbox for all process types that are normally not sandboxed.
env PLAYWRIGHT_MCP_SANDBOX


--save-session
Whether to save the Playwright MCP session into the output directory.
env PLAYWRIGHT_MCP_SAVE_SESSION


--secrets
path to a file containing secrets in the dotenv format
env PLAYWRIGHT_MCP_SECRETS_FILE


--shared-browser-context
reuse the same browser context between all connected HTTP clients.
env PLAYWRIGHT_MCP_SHARED_BROWSER_CONTEXT


--snapshot-mode
when taking snapshots for responses, specifies the mode to use. Can be "full" or "none". Default is "full".
env PLAYWRIGHT_MCP_SNAPSHOT_MODE


--storage-state
path to the storage state file for isolated sessions.
env PLAYWRIGHT_MCP_STORAGE_STATE


--test-id-attribute
specify the attribute to use for test ids, defaults to "data-testid"
env PLAYWRIGHT_MCP_TEST_ID_ATTRIBUTE


--timeout-action
specify action timeout in milliseconds, defaults to 5000ms
env PLAYWRIGHT_MCP_TIMEOUT_ACTION


--timeout-navigation
specify navigation timeout in milliseconds, defaults to 60000ms
env PLAYWRIGHT_MCP_TIMEOUT_NAVIGATION


--user-agent
specify user agent string
env PLAYWRIGHT_MCP_USER_AGENT


--user-data-dir
path to the user data directory. If not specified, a temporary directory will be created.
env PLAYWRIGHT_MCP_USER_DATA_DIR


--viewport-size
specify browser viewport size in pixels, for example "1280x720"
env PLAYWRIGHT_MCP_VIEWPORT_SIZE





### User profile

You can run Playwright MCP with persistent profile like a regular browser (default), in isolated contexts for testing sessions, or connect to your existing browser using the browser extension.

Persistent profile

All the logged in information will be stored in the persistent profile, you can delete it between sessions if you'd like to clear the offline state.
Persistent profile is located at the following locations and you can override it with the --user-data-dir argument.

# Windows
%USERPROFILE% \A ppData \L ocal \m s-playwright \m cp-{channel}-{workspace-hash}

# macOS
- ~ /Library/Caches/ms-playwright/mcp-{channel}-{workspace-hash}

# Linux
- ~ /.cache/ms-playwright/mcp-{channel}-{workspace-hash}










{workspace-hash} is derived from the MCP client's workspace root, so different projects get separate profiles automatically.

Important

A persistent profile can only be used by one browser instance at a time, so concurrent MCP clients sharing the same workspace will conflict. To run several clients in parallel, start each additional client with --isolated or point it at a distinct --user-data-dir .

Isolated

In the isolated mode, each session is started in the isolated profile. Every time you ask MCP to close the browser,
the session is closed and all the storage state for this session is lost. You can provide initial storage state
to the browser via the config's contextOptions or via the --storage-state argument. Learn more about the storage
state here .

{
"mcpServers" : {
"playwright" : {
"command" : "npx" ,
"args" : [
"@playwright/mcp@latest" ,
"--isolated" ,
"--storage-state={path/to/storage.json}"
]
}
}
}










Browser Extension

The Playwright MCP Chrome Extension allows you to connect to existing browser tabs and leverage your logged-in sessions and browser state. See microsoft/playwright › packages/extension for installation and setup instructions.


### Initial state

There are multiple ways to provide the initial state to the browser context or a page.

For the storage state, you can either:


- Start with a user data directory using the --user-data-dir argument. This will persist all browser data between the sessions.

- Start with a storage state file using the --storage-state argument. This will load cookies and local storage from the file into an isolated browser context.


For the page state, you can use:


- --init-page to point to a TypeScript file that will be evaluated on the Playwright page object. This allows you to run arbitrary code to set up the page.


// init-page.ts
export default async ( { page } ) => {
await page . context ( ) . grantPermissions ( [ 'geolocation' ] ) ;
await page . context ( ) . setGeolocation ( { latitude : 37.7749 , longitude : - 122.4194 } ) ;
await page . setViewportSize ( { width : 1280 , height : 720 } ) ;
} ;











- --init-script to point to a JavaScript file that will be added as an initialization script. The script will be evaluated in every page before any of the page's scripts.
This is useful for overriding browser APIs or setting up the environment.


// init-script.js
window . isPlaywrightMCP = true ;











### Configuration file



The Playwright MCP server can be configured using a JSON configuration file. You can specify the configuration file
using the --config command line option:

npx @playwright/mcp@latest --config path/to/config.json











Configuration file schema

{
/**
* The browser to use.
*/
browser ?: {
/**
* The type of browser to use.
*/
browserName ?: 'chromium' | 'firefox' | 'webkit' ;

/**
* Keep the browser profile in memory, do not save it to disk.
*/
isolated ?: boolean ;

/**
* Path to a user data directory for browser profile persistence.
* Temporary directory is created by default.
*/
userDataDir ?: string ;

/**
* Launch options passed to
* @see https://playwright.dev/docs/api/class-browsertype#browser-type-launch-persistent-context
*
* This is useful for settings options like `channel`, `headless`, `executablePath`, etc.
*/
launchOptions ?: playwright . LaunchOptions ;

/**
* Context options for the browser context.
*
* This is useful for settings options like `viewport`.
*/
contextOptions ?: playwright . BrowserContextOptions ;

/**
* Chrome DevTools Protocol endpoint to connect to an existing browser instance in case of Chromium family browsers.
*/
cdpEndpoint ?: string ;

/**
* CDP headers to send with the connect request.
*/
cdpHeaders ?: Record ;

/**
* Timeout in milliseconds for connecting to CDP endpoint. Defaults to 30000 (30 seconds). Pass 0 to disable timeout.
*/
cdpTimeout ?: number ;

/**
* Remote endpoint to connect to an existing Playwright server.
*/
remoteEndpoint ?: string ;

/**
* Paths to TypeScript files to add as initialization scripts for Playwright page.
*/
initPage ?: string [ ] ;

/**
* Paths to JavaScript files to add as initialization scripts.
* The scripts will be evaluated in every page before any of the page's scripts.
*/
initScript ?: string [ ] ;
} ,

/**
* Connect to a running browser instance (Edge/Chrome only). If specified, `browser`
* config is ignored.
* Requires the "Playwright Extension" to be installed.
*/
extension ?: boolean ;

server?: {
/**
* The port to listen on for SSE or MCP transport.
*/
port ?: number ;

/**
* The host to bind the server to. Default is localhost. Use 0.0.0.0 to bind to all interfaces.
*/
host?: string ;

/**
* The hosts this server is allowed to serve from. Defaults to the host server is bound to.
* This is not for CORS, but rather for the DNS rebinding protection.
*/
allowedHosts?: string [ ] ;
} ,

/**
* List of enabled tool capabilities. Possible values:
* - 'core': Core browser automation features.
* - 'pdf': PDF generation and manipulation.
* - 'vision': Coordinate-based interactions.
* - 'devtools': Developer tools features.
*/
capabilities ?: ToolCapability [ ] ;

/**
* Whether to save the Playwright session into the output directory.
*/
saveSession?: boolean ;

/**
* Reuse the same browser context between all connected HTTP clients.
*/
sharedBrowserContext?: boolean ;

/**
* Secrets are used to replace matching plain text in the tool responses to prevent the LLM
* from accidentally getting sensitive data. It is a convenience and not a security feature,
* make sure to always examine information coming in and from the tool on the client.
*/
secrets?: Record ;

/**
* The directory to save output files.
*/
outputDir?: string ;

console?: {
/**
* The level of console messages to return. Each level includes the messages of more severe levels. Defaults to "info".
*/
level ?: 'error' | 'warning' | 'info' | 'debug' ;
} ,

network ?: {
/**
* List of origins to allow the browser to request. Default is to allow all. Origins matching both `allowedOrigins` and `blockedOrigins` will be blocked.
*
* Supported formats:
* - Full origin: `https://example.com:8080` - matches only that origin
* - Wildcard port: `http://localhost:*` - matches any port on localhost with http protocol
*/
allowedOrigins ?: string [ ] ;

/**
* List of origins to block the browser to request. Origins matching both `allowedOrigins` and `blockedOrigins` will be blocked.
*
* Supported formats:
* - Full origin: `https://example.com:8080` - matches only that origin
* - Wildcard port: `http://localhost:*` - matches any port on localhost with http protocol
*/
blockedOrigins ?: string [ ] ;
} ;

/**
* Specify the attribute to use for test ids, defaults to "data-testid".
*/
testIdAttribute?: string ;

timeouts?: {
/*
* Configures default action timeout: https://playwright.dev/docs/api/class-page#page-set-default-timeout. Defaults to 5000ms.
*/
action ?: number ;

/*
* Configures default navigation timeout: https://playwright.dev/docs/api/class-page#page-set-default-navigation-timeout. Defaults to 60000ms.
*/
navigation?: number ;

/**
* Configures default expect timeout: https://playwright.dev/docs/test-timeouts#expect-timeout. Defaults to 5000ms.
*/
expect?: number ;
} ;

/**
* Whether to send image responses to the client. Can be "allow", "omit", or "auto". Defaults to "auto", which sends images if the client can display them.
*/
imageResponses?: 'allow' | 'omit' ;

snapshot?: {
/**
* When taking snapshots for responses, specifies the mode to use.
*/
mode ?: 'full' | 'none' ;
} ;

/**
* allowUnrestrictedFileAccess acts as a guardrail to prevent the LLM from accidentally
* wandering outside its intended workspace. It is a convenience defense to catch unintended
* file access, not a secure boundary; a deliberate attempt to reach other directories can be
* easily worked around, so always rely on client-level permissions for true security.
*/
allowUnrestrictedFileAccess?: boolean ;

/**
* Specify the language to use for code generation.
*/
codegen?: 'typescript' | 'none' ;
}












### Standalone MCP server



When running headed browser on system w/o display or from worker processes of the IDEs,
run the MCP server from environment with the DISPLAY and pass the --port flag to enable HTTP transport.

npx @playwright/mcp@latest --port 8931










And then in MCP client config, set the url to the HTTP endpoint:

{
"mcpServers" : {
"playwright" : {
"url" : "http://localhost:8931/mcp"
}
}
}











## Security



Playwright MCP is not a security boundary. See MCP Security Best Practices for guidance on securing your deployment.


Docker
NOTE: The Docker implementation only supports headless chromium at the moment.

{
"mcpServers" : {
"playwright" : {
"command" : "docker" ,
"args" : [ "run" , "-i" , "--rm" , "--init" , "--pull=always" , "mcr.microsoft.com/playwright/mcp" ]
}
}
}










Or If you prefer to run the container as a long-lived service instead of letting the MCP client spawn it, use:

docker run -d -i --rm --init --pull=always \
--entrypoint node \
--name playwright \
-p 8931:8931 \
mcr.microsoft.com/playwright/mcp \
/app/cli.js --headless --browser chromium --no-sandbox --port 8931 --host 0.0.0.0











The server will listen on host port 8931 and can be reached by any MCP client.

You can build the Docker image yourself.

docker build -t mcr.microsoft.com/playwright/mcp .













Programmatic usage
import http from 'http' ;

import { createConnection } from '@playwright/mcp' ;
import { SSEServerTransport } from '@modelcontextprotocol/sdk/server/sse.js' ;

http . createServer ( async ( req , res ) => {
// ...

// Creates a headless Playwright MCP server with SSE transport
const connection = await createConnection ( { browser : { launchOptions : { headless : true } } } ) ;
const transport = new SSEServerTransport ( '/messages' , res ) ;
await connection . connect ( transport ) ;

// ...
} ) ;












### Tools




Core automation


- browser_click

Title: Click

- Description: Perform click on a web page

- Parameters:

element (string, optional): Human-readable element description used to obtain permission to interact with the element

- target (string): Exact target element reference from the page snapshot, or a unique element selector

- doubleClick (boolean, optional): Whether to perform a double click instead of a single click

- button (string, optional): Button to click, defaults to left

- modifiers (array, optional): Modifier keys to press



- Read-only: false






- browser_close

Title: Close browser

- Description: Close the page

- Parameters: None

- Read-only: false






- browser_console_messages

Title: Get console messages

- Description: Returns all console messages

- Parameters:

level (string): Level of the console messages to return. Each level includes the messages of more severe levels. Defaults to "info".

- all (boolean, optional): Return all console messages since the beginning of the session, not just since the last navigation. Defaults to false.

- filename (string, optional): Filename to save the console messages to. If not provided, messages are returned as text.



- Read-only: true






- browser_drag

Title: Drag mouse

- Description: Perform drag and drop between two elements

- Parameters:

startElement (string, optional): Human-readable source element description used to obtain the permission to interact with the element

- startTarget (string): Exact target element reference from the page snapshot, or a unique element selector

- endElement (string, optional): Human-readable target element description used to obtain the permission to interact with the element

- endTarget (string): Exact target element reference from the page snapshot, or a unique element selector



- Read-only: false






- browser_drop

Title: Drop files or data onto an element

- Description: Drop files or MIME-typed data onto an element, as if dragged from outside the page. At least one of "paths" or "data" must be provided.

- Parameters:

element (string, optional): Human-readable element description used to obtain permission to interact with the element

- target (string): Exact target element reference from the page snapshot, or a unique element selector

- paths (array, optional): Absolute paths to files to drop onto the element.

- data (object, optional): Data to drop, as a map of MIME type to string value (e.g. {"text/plain": "hello", "text/uri-list": " https://example.com"} ).



- Read-only: false






- browser_evaluate

Title: Evaluate JavaScript

- Description: Evaluate JavaScript expression on page or element

- Parameters:

element (string, optional): Human-readable element description used to obtain permission to interact with the element

- target (string, optional): Exact target element reference from the page snapshot, or a unique element selector

- function (string): () => { /* code / } or (element) => { / code */ } when element is provided

- filename (string, optional): Filename to save the result to. If not provided, result is returned as text.



- Read-only: false






- browser_file_upload

Title: Upload files

- Description: Upload one or multiple files

- Parameters:

paths (array, optional): The absolute paths to the files to upload. Can be single file or multiple files. If omitted, file chooser is cancelled.



- Read-only: false






- browser_fill_form

Title: Fill form

- Description: Fill multiple form fields

- Parameters:

fields (array): Fields to fill in



- Read-only: false






- browser_handle_dialog

Title: Handle a dialog

- Description: Handle a dialog

- Parameters:

accept (boolean): Whether to accept the dialog.

- promptText (string, optional): The text of the prompt in case of a prompt dialog.



- Read-only: false






- browser_hover

Title: Hover mouse

- Description: Hover over element on page

- Parameters:

element (string, optional): Human-readable element description used to obtain permission to interact with the element

- target (string): Exact target element reference from the page snapshot, or a unique element selector



- Read-only: false






- browser_navigate

Title: Navigate to a URL

- Description: Navigate to a URL

- Parameters:

url (string): The URL to navigate to



- Read-only: false






- browser_navigate_back

Title: Go back

- Description: Go back to the previous page in the history

- Parameters: None

- Read-only: false






- browser_network_request

Title: Show network request details

- Description: Returns full details (headers and body) of a single network request, or a single part if part is set. Use the number from browser_network_requests.

- Parameters:

index (integer): 1-based index of the request, as printed by browser_network_requests.

- part (string, optional): Return only this part of the request. Omit to return full details.

- filename (string, optional): Filename to save the result to. If not provided, output is returned as text.



- Read-only: true






- browser_network_requests

Title: List network requests

- Description: Returns a numbered list of network requests since loading the page. Use browser_network_request with the number to get full details.

- Parameters:

static (boolean): Whether to include successful static resources like images, fonts, scripts, etc. Defaults to false.

- filter (string, optional): Only return requests whose URL matches this regexp (e.g. "/api/.*user").

- filename (string, optional): Filename to save the network requests to. If not provided, requests are returned as text.



- Read-only: true






- browser_press_key

Title: Press a key

- Description: Press a key on the keyboard

- Parameters:

key (string): Name of the key to press or a character to generate, such as ArrowLeft or a



- Read-only: false






- browser_resize

Title: Resize browser window

- Description: Resize the browser window

- Parameters:

width (number): Width of the browser window

- height (number): Height of the browser window



- Read-only: false






- browser_run_code_unsafe

Title: Run Playwright code (unsafe)

- Description: Run a Playwright code snippet. Unsafe: executes arbitrary JavaScript in the Playwright server process and is RCE-equivalent.

- Parameters:

code (string, optional): A JavaScript function containing Playwright code to execute. It will be invoked with a single argument, page, which you can use for any page interaction. For example: async (page) => { await page.getByRole('button', { name: 'Submit' }).click(); return await page.title(); }

- filename (string, optional): Load code from the specified file. If both code and filename are provided, code will be ignored.



- Read-only: false






- browser_select_option

Title: Select option

- Description: Select an option in a dropdown

- Parameters:

element (string, optional): Human-readable element description used to obtain permission to interact with the element

- target (string): Exact target element reference from the page snapshot, or a unique element selector

- values (array): Array of values to select in the dropdown. This can be a single value or multiple values.



- Read-only: false






- browser_snapshot

Title: Page snapshot

- Description: Capture accessibility snapshot of the current page, this is better than screenshot

- Parameters:

target (string, optional): Exact target element reference from the page snapshot, or a unique element selector

- filename (string, optional): Save snapshot to markdown file instead of returning it in the response.

- depth (number, optional): Limit the depth of the snapshot tree

- boxes (boolean, optional): Include each element's bounding box as [box=x,y,width,height] in the snapshot. Coordinates are viewport-relative, in CSS pixels (Element.getBoundingClientRect)



- Read-only: true






- browser_take_screenshot

Title: Take a screenshot

- Description: Take a screenshot of the current page. You can't perform actions based on the screenshot, use browser_snapshot for actions.

- Parameters:

element (string, optional): Human-readable element description used to obtain permission to interact with the element

- target (string, optional): Exact target element reference from the page snapshot, or a unique element selector

- type (string): Image format for the screenshot. Default is png.

- filename (string, optional): File name to save the screenshot to. Defaults to page-{timestamp}.{png|jpeg} if not specified. Prefer relative file names to stay within the output directory.

- fullPage (boolean, optional): When true, takes a screenshot of the full scrollable page, instead of the currently visible viewport. Cannot be used with element screenshots.



- Read-only: true






- browser_type

Title: Type text

- Description: Type text into editable element

- Parameters:

element (string, optional): Human-readable element description used to obtain permission to interact with the element

- target (string): Exact target element reference from the page snapshot, or a unique element selector

- text (string): Text to type into the element

- submit (boolean, optional): Whether to submit entered text (press Enter after)

- slowly (boolean, optional): Whether to type one character at a time. Useful for triggering key handlers in the page. By default entire text is filled in at once.



- Read-only: false






- browser_wait_for

Title: Wait for

- Description: Wait for text to appear or disappear or a specified time to pass

- Parameters:

time (number, optional): The time to wait in seconds

- text (string, optional): The text to wait for

- textGone (string, optional): The text to wait for to disappear



- Read-only: false






Tab management


- browser_tabs

Title: Manage tabs

- Description: List, create, close, or select a browser tab.

- Parameters:

action (string): Operation to perform

- index (number, optional): Tab index, used for close/select. If omitted for close, current tab is closed.

- url (string, optional): URL to navigate to in the new tab, used for new.



- Read-only: false






Browser installation


Configuration (opt-in via --caps=config)


- browser_get_config

Title: Get config

- Description: Get the final resolved config after merging CLI options, environment variables and config file.

- Parameters: None

- Read-only: true






Network (opt-in via --caps=network)


- browser_network_state_set

Title: Set network state

- Description: Sets the browser network state to online or offline. When offline, all network requests will fail.

- Parameters:

state (string): Set to "offline" to simulate offline mode, "online" to restore network connectivity



- Read-only: false






- browser_route

Title: Mock network requests

- Description: Set up a route to mock network requests matching a URL pattern

- Parameters:

pattern (string): URL pattern to match (e.g., " /api/users", " /*.{png,jpg}")

- status (number, optional): HTTP status code to return (default: 200)

- body (string, optional): Response body (text or JSON string)

- contentType (string, optional): Content-Type header (e.g., "application/json", "text/html")

- headers (array, optional): Headers to add in "Name: Value" format

- removeHeaders (string, optional): Comma-separated list of header names to remove from request



- Read-only: false






- browser_route_list

Title: List network routes

- Description: List all active network routes

- Parameters: None

- Read-only: true






- browser_unroute

Title: Remove network routes

- Description: Remove network routes matching a pattern (or all routes if no pattern specified)

- Parameters:

pattern (string, optional): URL pattern to unroute (omit to remove all routes)



- Read-only: false






Storage (opt-in via --caps=storage)


- browser_cookie_clear

Title: Clear cookies

- Description: Clear all cookies

- Parameters: None

- Read-only: false






- browser_cookie_delete

Title: Delete cookie

- Description: Delete a specific cookie

- Parameters:

name (string): Cookie name to delete



- Read-only: false






- browser_cookie_get

Title: Get cookie

- Description: Get a specific cookie by name

- Parameters:

name (string): Cookie name to get



- Read-only: true






- browser_cookie_list

Title: List cookies

- Description: List all cookies (optionally filtered by domain/path)

- Parameters:

domain (string, optional): Filter cookies by domain

- path (string, optional): Filter cookies by path



- Read-only: true






- browser_cookie_set

Title: Set cookie

- Description: Set a cookie with optional flags (domain, path, expires, httpOnly, secure, sameSite)

- Parameters:

name (string): Cookie name

- value (string): Cookie value

- domain (string, optional): Cookie domain

- path (string, optional): Cookie path

- expires (number, optional): Cookie expiration as Unix timestamp

- httpOnly (boolean, optional): Whether the cookie is HTTP only

- secure (boolean, optional): Whether the cookie is secure

- sameSite (string, optional): Cookie SameSite attribute



- Read-only: false






- browser_localstorage_clear

Title: Clear localStorage

- Description: Clear all localStorage

- Parameters: None

- Read-only: false






- browser_localstorage_delete

Title: Delete localStorage item

- Description: Delete a localStorage item

- Parameters:

key (string): Key to delete



- Read-only: false






- browser_localstorage_get

Title: Get localStorage item

- Description: Get a localStorage item by key

- Parameters:

key (string): Key to get



- Read-only: true






- browser_localstorage_list

Title: List localStorage

- Description: List all localStorage key-value pairs

- Parameters: None

- Read-only: true






- browser_localstorage_set

Title: Set localStorage item

- Description: Set a localStorage item

- Parameters:

key (string): Key to set

- value (string): Value to set



- Read-only: false






- browser_sessionstorage_clear

Title: Clear sessionStorage

- Description: Clear all sessionStorage

- Parameters: None

- Read-only: false






- browser_sessionstorage_delete

Title: Delete sessionStorage item

- Description: Delete a sessionStorage item

- Parameters:

key (string): Key to delete



- Read-only: false






- browser_sessionstorage_get

Title: Get sessionStorage item

- Description: Get a sessionStorage item by key

- Parameters:

key (string): Key to get



- Read-only: true






- browser_sessionstorage_list

Title: List sessionStorage

- Description: List all sessionStorage key-value pairs

- Parameters: None

- Read-only: true






- browser_sessionstorage_set

Title: Set sessionStorage item

- Description: Set a sessionStorage item

- Parameters:

key (string): Key to set

- value (string): Value to set



- Read-only: false






- browser_set_storage_state

Title: Restore storage state

- Description: Restore storage state (cookies, local storage) from a file. This clears existing cookies and local storage before restoring.

- Parameters:

filename (string): Path to the storage state file to restore from



- Read-only: false






- browser_storage_state

Title: Save storage state

- Description: Save storage state (cookies, local storage) to a file for later reuse

- Parameters:

filename (string, optional): File name to save the storage state to. Defaults to storage-state-{timestamp}.json if not specified.



- Read-only: true






DevTools (opt-in via --caps=devtools)


- browser_annotate

Title: Annotate the current page

- Description: Open the Playwright Dashboard in annotation mode for the current page and wait for the user to draw annotations. Returns the annotated screenshot, ARIA snapshot, and the list of annotations.

- Parameters: None

- Read-only: true






- browser_hide_highlight

Title: Hide element highlight

- Description: Remove a highlight overlay previously added for the element.

- Parameters:

element (string, optional): Human-readable element description used when adding the highlight; must match the value passed to browser_highlight.

- target (string, optional): Exact target element reference from the page snapshot, or a unique element selector



- Read-only: true






- browser_highlight

Title: Highlight element

- Description: Show a persistent highlight overlay around the element on the page.

- Parameters:

element (string, optional): Human-readable element description used to obtain permission to interact with the element

- target (string): Exact target element reference from the page snapshot, or a unique element selector

- style (string, optional): Additional inline CSS applied to the highlight overlay, e.g. "outline: 2px dashed red".



- Read-only: true






- browser_resume

Title: Resume paused script execution

- Description: Resume script execution after it was paused. When called with step set to true, execution will pause again before the next action.

- Parameters:

step (boolean, optional): When true, execution will pause again before the next action, allowing step-by-step debugging.

- location (string, optional): Pause execution at a specific :, e.g. "example.spec.ts:42".



- Read-only: false






- browser_start_tracing

Title: Start tracing

- Description: Start trace recording

- Parameters: None

- Read-only: true






- browser_start_video

Title: Start video

- Description: Start video recording

- Parameters:

filename (string, optional): Filename to save the video.

- size (object, optional): Video size



- Read-only: true






- browser_stop_tracing

Title: Stop tracing

- Description: Stop trace recording

- Parameters: None

- Read-only: true






- browser_stop_video

Title: Stop video

- Description: Stop video recording

- Parameters: None

- Read-only: true






- browser_video_chapter

Title: Video chapter

- Description: Add a chapter marker to the video recording. Shows a full-screen chapter card with blurred backdrop.

- Parameters:

title (string): Chapter title

- description (string, optional): Chapter description

- duration (number, optional): Duration in milliseconds to show the chapter card



- Read-only: true






Coordinate-based (opt-in via --caps=vision)


- browser_mouse_click_xy

Title: Click

- Description: Click mouse button at a given position

- Parameters:

x (number): X coordinate

- y (number): Y coordinate

- button (string, optional): Button to click, defaults to left

- clickCount (number, optional): Number of clicks, defaults to 1

- delay (number, optional): Time to wait between mouse down and mouse up in milliseconds, defaults to 0



- Read-only: false






- browser_mouse_down

Title: Press mouse down

- Description: Press mouse down

- Parameters:

button (string, optional): Button to press, defaults to left



- Read-only: false






- browser_mouse_drag_xy

Title: Drag mouse

- Description: Drag left mouse button to a given position

- Parameters:

startX (number): Start X coordinate

- startY (number): Start Y coordinate

- endX (number): End X coordinate

- endY (number): End Y coordinate



- Read-only: false






- browser_mouse_move_xy

Title: Move mouse

- Description: Move mouse to a given position

- Parameters:

x (number): X coordinate

- y (number): Y coordinate



- Read-only: false






- browser_mouse_up

Title: Press mouse up

- Description: Press mouse up

- Parameters:

button (string, optional): Button to press, defaults to left



- Read-only: false






- browser_mouse_wheel

Title: Scroll mouse wheel

- Description: Scroll mouse wheel

- Parameters:

deltaX (number): X delta

- deltaY (number): Y delta



- Read-only: false






PDF generation (opt-in via --caps=pdf)


- browser_pdf_save

Title: Save as PDF

- Description: Save page as PDF

- Parameters:

filename (string, optional): File name to save the pdf to. Defaults to page-{timestamp}.pdf if not specified. Prefer relative file names to stay within the output directory.



- Read-only: true






Test assertions (opt-in via --caps=testing)


- browser_generate_locator

Title: Create locator for element

- Description: Generate locator for the given element to use in tests

- Parameters:

element (string, optional): Human-readable element description used to obtain permission to interact with the element

- target (string): Exact target element reference from the page snapshot, or a unique element selector



- Read-only: true






- browser_verify_element_visible

Title: Verify element visible

- Description: Verify element is visible on the page

- Parameters:

role (string): ROLE of the element. Can be found in the snapshot like this: - {ROLE} "Accessible Name":

- accessibleName (string): ACCESSIBLE_NAME of the element. Can be found in the snapshot like this: - role "{ACCESSIBLE_NAME}"



- Read-only: false






- browser_verify_list_visible

Title: Verify list visible

- Description: Verify list is visible on the page

- Parameters:

element (string): Human-readable list description

- target (string): Exact target element reference that points to the list

- items (array): Items to verify



- Read-only: false






- browser_verify_text_visible

Title: Verify text visible

- Description: Verify text is visible on the page. Prefer browser_verify_element_visible if possible.

- Parameters:

text (string): TEXT to verify. Can be found in the snapshot like this: - role "Accessible Name": {TEXT} or like this: - text: {TEXT}



- Read-only: false






- browser_verify_value

Title: Verify value

- Description: Verify element value

- Parameters:

type (string): Type of the element

- element (string): Human-readable element description

- target (string): Exact target eleme

…(truncated)
