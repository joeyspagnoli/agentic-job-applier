# Amazon Bedrock AgentCore Browser Tool — https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/browser-tool.html

Fetched: 2026-05-24
Source: WebFetch of official AWS documentation (returned full content)

## What It Is

The Amazon Bedrock AgentCore Browser is a **fully managed, cloud-hosted browser environment** for AI agents. It provides an isolated, containerized Chromium instance running in AWS infrastructure. Agents interact with the browser through WebSocket-based streaming APIs.

This is **NOT a local browser tool**. It runs entirely in AWS data centers.

## How It Works (4-Step Workflow)

1. **Create a Browser Tool** — register either `aws.browser.v1` (managed, no config) or a custom browser with advanced settings
2. **Start a browser session** — launch isolated session with configurable timeout (default: 15 min, max: 8 hours)
3. **Interact with the browser** — WebSocket automation endpoint + optional Live View endpoint for human monitoring
4. **Monitor and record** — CloudWatch metrics, session recording to S3, DOM change capture, video replay

## Browser Interaction Libraries

Libraries that work with AgentCore Browser:
- **Strands** (AWS native integration)
- **Nova Act** (AWS browser automation agent)
- **Playwright** (standard automation — via WebSocket CDP connection to AgentCore session)

## Security Features

- **Session isolation**: containerized per-session, ephemeral
- **Automatic TTL termination**: session auto-terminates when timeout expires
- **CloudTrail logging**: all actions logged for audit
- **No local exposure**: browser runs in AWS, not on user's machine

## Observability Features

- **Live View**: real-time streaming of browser session to human observer (interactive)
- **Session recording**: captures DOM changes, user actions, console logs, network events
- **CloudWatch metrics**: performance dashboards
- **Session replay**: video playback, timeline navigation, user action tracking

---

## Why AgentCore Browser is NOT a Fit for This Project

**1. Mandatory AWS Account**

AgentCore Browser is an AWS service. It requires:
- An active AWS account
- IAM roles/permissions configured
- Bedrock AgentCore service enabled in a supported region
- Model access granted

Our target users are **non-technical Windows users** who receive the app via `dist/`. They cannot be expected to create AWS accounts, configure IAM, or enable AWS services.

**2. Ongoing Per-Session Cost**

AgentCore Browser charges per browser session. At $0.01-0.10/apply target cost, any per-session browser fee represents a significant or unbounded portion of the budget. AWS pricing for managed browser sessions is not disclosed on the docs page, but managed container services of this type typically cost $0.01-0.05+/minute.

**3. Network Dependency / Latency**

Each browser interaction traverses the internet to AWS and back (WebSocket round-trip). For a 20-turn apply loop with frequent DOM reads and field fills, this latency would meaningfully slow down the loop compared to a locally attached CDP session.

**4. Contradicts Self-Hosted Architecture**

The project distributes `dist/` so users run everything locally. A cloud-hosted browser directly contradicts this model. The user's data (form contents, credentials, etc.) would transit AWS infrastructure.

**5. CDP-Attached Chromium Already Solves the Problem**

The existing architecture already has a locally running Chromium with CDP attachment. This is functionally superior:
- Zero latency (loopback)
- No account/cost requirements
- Works offline
- User controls their own browser session
- Simplify Copilot extension already installed

**Conclusion: AgentCore Browser is firmly rejected** for the self-hosted, dist-distributed, non-technical user use case. The only scenario where it would be relevant is a future hosted SaaS version of the product, which is not the current roadmap.
