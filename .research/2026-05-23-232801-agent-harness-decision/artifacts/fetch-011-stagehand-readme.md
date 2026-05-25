# Stagehand README

Source: https://github.com/browserbase/stagehand

- GitHub - browserbase/stagehand: The SDK For Browser Agents · GitHub

































































































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

































browserbase

/

stagehand


Public












Notifications
You must be signed in to change notification settings

- Fork
1.5k

- Star
22.8k












- Code

- Issues
91

- Pull requests
135

- Discussions

- Actions

- Projects

- Security and quality
0

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































# browserbase/stagehand










main



1299 Branches 71 Tags







Go to file

Code Open more actions menu



## Folders and files

Name Name Last commit message

Last commit date


## Latest commit

miguelg719



feat(verifier): add verifier evaluator shell and types ( #2157 )

success

May 22, 2026

2cd60a3  ·  May 22, 2026


## History

1,297 Commits Open commit details

1,297 Commits

.changeset

.changeset

feat(verifier): add verifier evaluator shell and types ( #2157 )

May 22, 2026

.github

.github

Workflow: publish eval results ( #2093 )

May 21, 2026

.husky

.husky

STG-1671: chore: add prettier pre-commit hook via husky + lint-staged ( …

Mar 27, 2026

.vscode

.vscode

add settings.json (prettier formatter turned on by default) ( #83 )

Oct 1, 2024

media

media

[chore]: update readme ( #1971 )

Apr 6, 2026

packages

packages

feat(verifier): add verifier evaluator shell and types ( #2157 )

May 22, 2026

.cursorrules

.cursorrules

Update docs to remove zod pinning ( #1743 )

Feb 24, 2026

.env.example

.env.example

chore: remove retired Claude 3.5 and 3.7 Sonnet models ( #1775 )

Mar 3, 2026

.gitignore

.gitignore

Evals v2 ( #2011 )

May 1, 2026

.prettierignore

.prettierignore

[chore]: refactor & fix lint for browse CLI ( #1821 )

Mar 12, 2026

.prettierrc

.prettierrc

add blank prettier rc so vscode does not override ( #34 )

Jun 7, 2024

CHANGELOG.md

CHANGELOG.md

Fm/stg 956 make ci faster ( #1246 )

Nov 17, 2025

LICENSE

LICENSE

Update README and License with missing/incorrect info ( #223 )

Nov 25, 2024

README.md

README.md

remove default temp ( #2076 )

May 6, 2026

claude.md

claude.md

default agent to hybrid mode ( #2047 )

Apr 30, 2026

eslint.config.mjs

eslint.config.mjs

[chore]: refactor & fix lint for browse CLI ( #1821 )

Mar 12, 2026

package.json

package.json

[chore]: bump more deps ( #2114 )

May 13, 2026

pnpm-lock.yaml

pnpm-lock.yaml

[chore]: rm langchain deps ( #2123 )

May 14, 2026

pnpm-workspace.yaml

pnpm-workspace.yaml

[feat]: add browse CLI package ( #1793 )

Mar 9, 2026

stainless.yml

stainless.yml

[STG-1808] Deprecate Browserbase project ID ( #2039 )

May 6, 2026

tsconfig.base.json

tsconfig.base.json

[STG-1232] Speed up PR Github Actions checks, add code coverage, fix …

Feb 17, 2026

tsconfig.json

tsconfig.json

[STG-1232] Speed up PR Github Actions checks, add code coverage, fix …

Feb 17, 2026

turbo.json

turbo.json

[STG-1808] Use STAGEHAND_API_URL for Stagehand API client ( #2040 )

May 4, 2026

View all files




## Repository files navigation

- README
- MIT license













The AI Browser Automation Framework

Read the Docs

If you're looking for the Python implementation, you can find it
here


Vibe code
Stagehand with

Director


## What is Stagehand?



Stagehand is a browser automation framework used to control web browsers with natural language and code. By combining the power of AI with the precision of code, Stagehand makes web automation flexible, maintainable, and actually reliable.


## Why Stagehand?

Most existing browser automation tools either require you to write low-level code in a framework like Selenium, Playwright, or Puppeteer, or use high-level agents that can be unpredictable in production. By letting developers choose what to write in code vs. natural language (and bridging the gap between the two) Stagehand is the natural choice for browser automations in production.


- Choose when to write code vs. natural language : use AI when you want to navigate unfamiliar pages, and use code when you know exactly what you want to do.

- Go from AI-driven to repeatable workflows : Stagehand lets you preview AI actions before running them, and also helps you easily cache repeatable actions to save time and tokens.

- Write once, run forever : Stagehand's auto-caching combined with self-healing remembers previous actions, runs without LLM inference, and knows when to involve AI whenever the website changes and your automation breaks.



## Getting Started

Start with Stagehand with one line of code, or check out our Quickstart Guide for more information:

npx create-browser-app











## Example



Here's how to build a sample browser automation with Stagehand:

// Stagehand's CDP engine provides an optimized, low level interface to the browser built for automation
const page = stagehand . context . pages ( ) [ 0 ] ;
await page . goto ( "https://github.com/browserbase" ) ;

// Use act() to execute individual actions
await stagehand . act ( "click on the stagehand repo" ) ;

// Use agent() for multi-step tasks
const agent = stagehand . agent ( ) ;
await agent . execute ( "Get to the latest PR" ) ;

// Use extract() to get structured data from the page
const { author , title } = await stagehand . extract (
"extract the author and title of the PR" ,
z . object ( {
author : z . string ( ) . describe ( "The username of the PR author" ) ,
title : z . string ( ) . describe ( "The title of the PR" ) ,
} ) ,
) ;











## Documentation



Visit docs.stagehand.dev to view the full documentation.


### Build and Run from Source

git clone https://github.com/browserbase/stagehand.git
cd stagehand
pnpm install
pnpm run build
pnpm run example # run the blank script at ./examples/example.ts










Stagehand is best when you have an API key for an LLM provider and Browserbase credentials. To add these to your project, run:

cp .env.example .env
nano .env # Edit the .env file to add API keys











### Installing from a branch



You can install and build Stagehand directly from a github branch using gitpkg

In your project's package.json set:

"@browserbasehq/stagehand" : " https://gitpkg.now.sh/browserbase/stagehand/packages/core? " ,











## Contributing



Note

We highly value contributions to Stagehand! For questions or support, please join our Discord community .

At a high level, we're focused on improving reliability, extensibility, speed, and cost in that order of priority. If you're interested in contributing, bug fixes and small improvements are the best way to get started . For more involved features, we strongly recommend reaching out to Miguel Gonzalez or Paul Klein in our Discord community before starting to ensure that your contribution aligns with our goals.


## Acknowledgements

We'd like to thank the following people for their major contributions to Stagehand:


- Paul Klein

- Sean McGuire

- Miguel Gonzalez

- Sameel Arif

- Thomas Katwan

- Filip Michalsky

- Anirudh Kamath

- Jeremy Press

- Navid Pour



## License

Licensed under the MIT License.

Copyright 2025 Browserbase, Inc.












## About

The SDK For Browser Agents



stagehand.dev




### Topics




ai


selenium


agents


puppeteer


playwright


llms






### Resources






Readme




### License






MIT license













### Uh oh!

There was an error while loading. Please reload this page .








Activity





Custom properties


### Stars





22.8k
stars


### Watchers





95
watching


### Forks





1.5k
forks



Report repository










## Releases
65







stagehand/server-v3 v3.6.10

Latest


May 20, 2026




+ 64 releases












## Packages
0


No packages published




















### Uh oh!

There was an error while loading. Please reload this page .















## Contributors
72



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




+ 58 contributors









## Languages









- TypeScript
80.5%

- MDX
18.4%

- Other
1.1%



































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