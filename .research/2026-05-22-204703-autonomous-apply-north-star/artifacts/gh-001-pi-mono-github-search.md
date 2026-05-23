# gh-001: pi-mono GitHub search

**Date:** 2026-05-22
**Goal:** Use `gh search repos` and `gh search code` to map the pi-mono ecosystem and confirm canonical identity.

## Canonical repo metadata

`gh api repos/badlogic/pi-mono` → 301-redirects to `earendil-works/pi`.

`gh api repos/earendil-works/pi` highlights:
- `id`: 1035029907
- `created_at`: 2025-08-09T14:03:50Z
- `updated_at`: 2026-05-23T00:48:32Z (active this very week)
- `pushed_at`: 2026-05-22T22:16:25Z
- `stargazers_count`: **52,971**
- `forks_count`: 6,344
- `subscribers_count`: 188
- `open_issues_count`: 35
- `language`: TypeScript
- `license`: MIT
- `default_branch`: main
- `has_discussions`: true
- `description`: "AI agent toolkit: coding agent CLI, unified LLM API, TUI & web UI libraries, Slack bot, vLLM pods"
- `organization`: earendil-works (org id 207902832, created when the repo was renamed)
- `topics`: [] (none set on the renamed repo)

The Hugging Face dataset `badlogicgames/pi-mono` is the maintainer's published corpus of real coding sessions for training data.

## `gh search repos` results (filtered to the pi-mono ecosystem)

Highest-signal hits:

| Repo | One-line | Last update |
|---|---|---|
| `qualisero/awesome-pi-agent` | Awesome list of add-ons, hooks, tools, skills, and resources for pi (pi-mono) | 2026-05-22 |
| `ZhangHanDong/pi-book` | "Pi mono Book" | 2026-05-22 |
| `emanuelcasco/pi-mono-extensions` | Collection of pi-mono extensions | 2026-05-22 |
| `ruanqisevik/pi-mono-extensions` | Monorepo for pi extensions | 2026-05-04 |
| `sysid/pi-extensions` | Improved pi-mono extensions | 2026-05-08 |
| `kcosr/pi-extensions` | Extensions for badlogic/pi-mono coding agent | 2026-05-17 |
| `ben-vargas/pi-packages` | Packages for Pi — extensions, skills, prompt templates, themes | 2026-05-21 |
| `Dwsy/pi-session-manager` | Pi session manager for browsing/searching/resuming Pi AI sessions | 2026-05-21 |
| `m-sec-org/BreachWeave` | "Penetration-test Agent — Manager/Observer/Solver multi-role architecture, based on pi-mono SDK" | 2026-05-22 |
| `manaflow-ai/pi-mono-1` | Fork; same description as upstream | recent |
| `aebrer/dreb` | "Provider-agnostic agentic coding harness. Hard fork of pi-mono." | 2026-05-19 |
| `openxjarvis/pi-mono-python` | "Python port of pi-mono: fully-aligned coding agent with TUI, ai, agent, and coding-agent packages" | 2026-05-13 |
| `code-yeongyu/senpi` | "opinionated fork of badlogic/pi-mono with extension-first additions" | 2026-05-22 |
| `jshachm/pi-rs` | "Rust lightweight version of pi-mono" | 2026-05-18 |
| `can1357/oh-my-pi` | "AI Coding agent for the terminal — hash-anchored edits, optimized tool harness, LSP, Python, browser, subagents, and more" | recent |
| `kashodiya/pi-browser` | "Browser with Pi Agent" | recent |
| `Denveous/pimono-mcp` | (MCP server wrapping pi-mono) | 2026-05-17 |
| `Keke-nA/learn-pimono` | Learning notes on pi-mono | 2026-03-24 |

Noise filtered out: dozens of Raspberry-Pi-and-Mono .NET libraries, an unrelated Indonesian fintech called "Pimono" (`pimono-wallet*`, `pimono-mini-wallet`, etc.), and student MonoGame projects.

## `gh search code` — confirms ecosystem reach

Search `pi-mono`:
- `castai/kimchi` AGENTS.md → "This repo extends `@earendil-works/pi-coding-agent` (pi-mono). Most..."
- `algopian/chromeclaw` CLAUDE.md → **"ChromeClaw is a Chrome extension that provides AI chat in the browser's side panel with multi-provider LLM support. Built with React 19, TypeScript, and pi-mono (`@mariozechner/pi-ai` + `@mariozechner/pi-agent-core`)."**
- `daydreamsai/daydreams` readme → "We recommend the **Pi agent harness** for building agents and incorporating lucid-agents in it."
- `clawmax/openclaw-docs-i18n` → OpenClaw is built on pi-coding-agent + pi-ai + pi-agent-core + pi-tui
- `polaris340/pi-discord` bot.js → references upstream RPC protocol doc
- `codeworksh/codework` NOTICE.md → "This project contains parts of code derived from Pi-Mono."
- `oratis/LISA` PITCH.md → positions itself as "capability superset of pi-mono / OpenClaw / hermes / claude-code / codex"
- `victor-software-house/pi-openai-proxy` → tracks pi-mono HEAD versions explicitly
- `OpenGithubs/github-monthly-rank` 2026/05 → "10 | badlogic/pi-mono | 43.2k | up 12,999 stars this month"

Search `@mariozechner/pi-agent-core` (the pre-rename npm scope, still very common):
- 20+ repos importing this package as their agent runtime: `Bitterbot-AI/bitterbot-desktop` (pinned 0.49.3), `earendil-works/absurd` (the org's own pattern docs), `xiaochong/hi-kid`, `oujingzhou/openmozi`, `pockebot/openpocket`, `skorokithakis/stavrobot`, `GeminiLight/MindOS` wiki, `pasky/muaddib`, `maotoumao/Cebian`, `BodhiSearch/BodhiApp` (chat migrated from custom hooks to pi-agent-core), `tinyfatco/troublemaker`, `telagod/pi-agent-colony`, `boozedog/pi-codemode`, `larsderidder/bryti`, `gregmercer/pi-agent-examples`, `zeflq/pi-reviewer`, `zuoc1993/oh-my-agentloop` (Rust port), `morewhyhan/AXIOM-Cognitive-OS`, `Jerryguan777/rolemesh` (Python port), `funtuan/pi-agent-cf` (Cloudflare Workers port).

Search `@earendil-works/pi-agent-core` (current scope):
- `openclaw/openclaw`, the source-of-truth README, `NixOS/nixpkgs` package, `companion-inc/feynman` extension loader, `backnotprop/plannotator`, `hewliyang/office-agents`, `tmustier/pi-for-excel`, `code-yeongyu/senpi`, `wincent/wincent` dotfiles, `nicobailon/pi-subagents`, `flora131/atomic`, `eforge-build/eforge`, `traceroot-ai/traceroot`, `cortexkit/magic-context` lock file pinning `^0.74.0`, `IgorWarzocha/howcode`, `shaftoe/pi-coding-agent-action` (GitHub Action), `megalithic/dotfiles`.
- `getsentry/vitest-evals` pnpm-lock notes: "deprecated: please use @earendil-works/pi-agent-core instead going forward" — confirms the namespace migration from `@mariozechner/*` to `@earendil-works/*`.

## Takeaways

- **52k stars, +13k in the last month alone, and 188 watchers** — pi-mono is currently the most talked-about open-source coding-agent harness in May 2026.
- The ecosystem includes Rust, Python, and Cloudflare Workers ports plus dozens of extension repos.
- Multiple production use cases already wire pi-mono into **non-coding** workflows: Chrome extension (chromeclaw), multi-channel messaging assistants (OpenClaw → WhatsApp/Telegram/Slack/Discord/Signal/iMessage/Teams), Slack bots, GitHub Actions, browser side panels, even penetration-testing agent stacks.
- The Chrome-extension precedent (`algopian/chromeclaw`) is the most directly relevant data point for the job-application use case: it already proves pi-mono can be embedded in a Chrome extension that uses a "Browser tool" backed by Chrome DevTools Protocol for DOM snapshots, click/type, screenshots, and JS evaluation.
