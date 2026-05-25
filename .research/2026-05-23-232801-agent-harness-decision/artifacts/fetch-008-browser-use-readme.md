# browser-use README

Source: https://github.com/browser-use/browser-use

- GitHub - browser-use/browser-use: 🌐 Make websites accessible for AI agents. Automate tasks online with ease. · GitHub

































































































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

































browser-use

/

browser-use


Public












Notifications
You must be signed in to change notification settings

- Fork
10.7k

- Star
95.3k












- Code

- Issues
65

- Pull requests
176

- Discussions

- Actions

- Projects

- Security and quality
1

- Insights







Additional navigation options







- Code

- Issues

- Pull requests

- Discussions

- Actions

- Projects

- Security and quality

- Insights































# browser-use/browser-use










main



520 Branches 134 Tags







Go to file

Code Open more actions menu



## Folders and files

Name Name Last commit message

Last commit date


## Latest commit

MagMueller



Trim HistoryItem freeze follow-up ( #4902 )

Open commit details failure

May 23, 2026

d21b3da  ·  May 23, 2026


## History

9,281 Commits Open commit details

9,281 Commits

.github

.github

chore(llm): recommend gemini-3-flash-preview in examples and tests

May 22, 2026

bin

bin

refactor: improve type checking and linting script

Nov 11, 2025

browser_use

browser_use

Merge branch 'main' into trim-pr-4890

May 23, 2026

docker

docker

fix: correct docker build context path in build-base-images.sh

Feb 3, 2026

examples

examples

chore(llm): rename flash-lite recommendation to gemini-3.1-flash-lite

May 22, 2026

skills

skills

chore(llm): rename flash-lite recommendation to gemini-3.1-flash-lite

May 22, 2026

static

static

update benchmark plot with bu-ultra result (78%)

Mar 24, 2026

tests

tests

Merge branch 'main' into trim-pr-4890

May 23, 2026

.dockerignore

.dockerignore

ignore .bak files in docker and git

Jun 25, 2025

.env.example

.env.example

env var to disable version check

Nov 26, 2025

.gitattributes

.gitattributes

Remove mp4 files and update gitattributes

Nov 18, 2024

.gitignore

.gitignore

docs: Add cleanup instructions to SKILL.md

Jan 21, 2026

.pre-commit-config.yaml

.pre-commit-config.yaml

fixed styling issues

Feb 23, 2026

.python-version

.python-version

bump dependency versions

Jun 3, 2025

AGENTS.md

AGENTS.md

chore(llm): recommend gemini-3-flash-preview in examples and tests

May 22, 2026

CLAUDE.md

CLAUDE.md

improve extract data

Aug 31, 2025

CLOUD.md

CLOUD.md

chore(llm): rename flash-lite recommendation to gemini-3.1-flash-lite

May 22, 2026

Dockerfile

Dockerfile

Refactor Dockerfile and update tests for improved functionality

Aug 26, 2025

Dockerfile.fast

Dockerfile.fast

speedup docker build to 20s

Jun 27, 2025

LICENSE

LICENSE

Added MIT license

Nov 5, 2024

README.md

README.md

docs: fix malformed HTML attributes in README picture/img tags

Apr 20, 2026

pyproject.toml

pyproject.toml

Bump version to 0.12.8

May 23, 2026

View all files




## Repository files navigation

- README
- Contributing
- MIT license
- Security



































🌤️ Want to skip the setup? Use our cloud for faster, scalable, stealth-enabled browser automation!


# 🤖 LLM Quickstart

- Direct your favorite coding agent (Cursor, Claude Code, etc) to Agents.md

- Prompt away!




# 👋 Human Quickstart



1. Create environment and install Browser-Use with uv (Python>=3.11):

uv init && uv add browser-use && uv sync
# uvx browser-use install # Run if you don't have Chromium installed










2. [Optional] Get your API key from Browser Use Cloud :

# .env
BROWSER_USE_API_KEY=your-key
# GOOGLE_API_KEY=your-key
# ANTHROPIC_API_KEY=your-key











3. Run your first agent:

from browser_use import Agent , Browser , ChatBrowserUse
# from browser_use import ChatGoogle # ChatGoogle(model='gemini-3-flash-preview')
# from browser_use import ChatAnthropic # ChatAnthropic(model='claude-sonnet-4-6')
import asyncio

async def main ():
browser = Browser (
# use_cloud=True, # Use a stealth browser on Browser Use Cloud
)

agent = Agent (
task = "Find the number of stars of the browser-use repo" ,
llm = ChatBrowserUse (),
# llm=ChatGoogle(model='gemini-3-flash-preview'),
# llm=ChatAnthropic(model='claude-sonnet-4-6'),
browser = browser ,
)
await agent . run ()

if __name__ == "__main__" :
asyncio . run ( main ())










Check out the library docs and the cloud docs for more!


# Open Source vs Cloud

We benchmark Browser Use across 100 real-world browser tasks. Full benchmark is open source: browser-use/benchmark .

Use the Open-Source Agent


- You need custom tools or deep code-level integration

- We recommend pairing with our cloud browsers for leading stealth, proxy rotation, and scaling

- Or self-host the open-source agent fully on your own machines


Use the Fully-Hosted Cloud Agent (recommended)


- Much more powerful agent for complex tasks (see plot above)

- Easiest way to start and scale

- Best stealth with proxy rotation and captcha solving

- 1000+ integrations (Gmail, Slack, Notion, and more)

- Persistent filesystem and memory




# Demos

### 📋 Form-Filling




#### Task = "Fill in this job application with my resume and information."




























Example code ↗


### 🍎 Grocery-Shopping

#### Task = "Put this list of items into my instacart."








grocery-use-large.mp4








Example code ↗


### 💻 Personal-Assistant.

#### Task = "Help me find parts for a custom PC."








pc-use-large.mp4








Example code ↗


### 💡See more examples here ↗ and give us a star!

# 🚀 Template Quickstart



Want to get started even faster? Generate a ready-to-run template:

uvx browser-use init --template default










This creates a browser_use_default.py file with a working example. Available templates:


- default - Minimal setup to get started quickly

- advanced - All configuration options with detailed comments

- tools - Examples of custom tools and extending the agent


You can also specify a custom output path:

uvx browser-use init --template default --output my_agent.py











# 💻 CLI



Fast, persistent browser automation from the command line:

browser-use open https://example.com # Navigate to URL
browser-use state # See clickable elements
browser-use click 5 # Click element by index
browser-use type " Hello " # Type text
browser-use screenshot page.png # Take screenshot
browser-use close # Close browser










The CLI keeps the browser running between commands for fast iteration. See CLI docs for all commands.


### Claude Code Skill

For Claude Code , install the skill to enable AI-assisted browser automation:

mkdir -p ~ /.claude/skills/browser-use
curl -o ~ /.claude/skills/browser-use/SKILL.md \
https://raw.githubusercontent.com/browser-use/browser-use/main/skills/browser-use/SKILL.md











## Integrations, hosting, custom tools, MCP, and more on our Docs ↗




# FAQ




What's the best model to use?
We optimized ChatBrowserUse() specifically for browser automation tasks. On avg it completes tasks 3-5x faster than other models with SOTA accuracy.

Pricing (per 1M tokens):


- Input tokens: $0.20

- Cached input tokens: $0.02

- Output tokens: $2.00


For other LLM providers, see our supported models documentation .



Should I use the Browser Use system prompt with the open-source preview model?
Yes. If you use ChatBrowserUse(model='browser-use/bu-30b-a3b-preview') with a normal Agent(...) , Browser Use still sends its default agent system prompt for you.

You do not need to add a separate custom "Browser Use system message" just because you switched to the open-source preview model. Only use extend_system_message or override_system_message when you intentionally want to customize the default behavior for your task.

If you want the best default speed/accuracy, we still recommend the newer hosted bu-* models. If you want the open-source preview model, the setup stays the same apart from the model= value.



Can I use custom tools with the agent?
Yes! You can add custom tools to extend the agent's capabilities:

from browser_use import Tools

tools = Tools ()

@ tools . action ( description = 'Description of what this tool does.' )
def custom_tool ( param : str ) -> str :
return f"Result: { param } "

agent = Agent (
task = "Your task" ,
llm = llm ,
browser = browser ,
tools = tools ,
)












Can I use this for free?
Yes! Browser-Use is open source and free to use. You only need to choose an LLM provider (like OpenAI, Google, ChatBrowserUse, or run local models with Ollama).



Terms of Service
This open-source library is licensed under the MIT License. For Browser Use services & data policy, see our Terms of Service and Privacy Policy .



How do I handle authentication?
Check out our authentication examples:


- Using real browser profiles - Reuse your existing Chrome profile with saved logins

- If you want to use temporary accounts with inbox, choose AgentMail

- To sync your auth profile with the remote browser, run curl -fsSL https://browser-use.com/profile.sh | BROWSER_USE_API_KEY=XXXX sh (replace XXXX with your API key)


These examples show how to maintain sessions and handle authentication seamlessly.



How do I solve CAPTCHAs?
For CAPTCHA handling, you need better browser fingerprinting and proxies. Use Browser Use Cloud which provides stealth browsers designed to avoid detection and CAPTCHA challenges.



How do I go into production?
Chrome can consume a lot of memory, and running many agents in parallel can be tricky to manage.

For production use cases, use our Browser Use Cloud API which handles:


- Scalable browser infrastructure

- Memory management

- Proxy rotation

- Stealth browser fingerprinting

- High-performance parallel execution





Tell your computer what to do, and it gets it done.



Made with ❤️ in Zurich and San Francisco












## About

🌐 Make websites accessible for AI agents. Automate tasks online with ease.



browser-use.com




### Topics




python


browser-automation


ai-agents


playwright


ai-tools


llm


browser-use






### Resources






Readme




### License






MIT license




### Contributing






Contributing




### Security policy






Security policy













### Uh oh!

There was an error while loading. Please reload this page .










Activity





Custom properties


### Stars





95.3k
stars


### Watchers





433
watching


### Forks





10.7k
forks



Report repository










## Releases
125







0.12.8

Latest


May 23, 2026




+ 124 releases












## Packages
0


No packages published












## Used by 2.6k



-

-

-

-

-

-

-

-



+ 2,557












## Contributors
319



-

-

-

-

-

-

-

-

-

-

-

-

-

-




+ 305 contributors









## Languages









- Python
98.2%

- Shell
1.3%

- Other
0.5%



































## Footer











© 2026 GitHub, Inc.





### Footer navigation



- Terms

- Privacy

- Security

- Status

- Community

- Docs

- Contact

- Manage cookies

- Do not share my personal information


















You can’t perform that action at this time.