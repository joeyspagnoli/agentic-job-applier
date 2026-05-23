# search-004: pi-mono disambiguation

**Date:** 2026-05-22
**Goal:** Resolve the user's reference to "pi-mono agent" to a concrete public artifact.

## Queries run

WebSearch (results captured 2026-05-22):

| Query | Top hit |
|---|---|
| `"pi-mono" agent framework` | pyshine.com/Pi-Mono-Full-Stack-AI-Agent-Toolkit, decisioncrafters write-up (44k stars), deepwiki badlogic/pi-mono, hoangyell "Anti-Framework", dev.to "One OSS Project a Day No.53", nader.substack "Custom Agent Framework with PI" |
| `"pi-mono" llm small model` | hoangyell, deepwiki "Model Resolution & Thinking Levels", parallel.ai "free CLI agent with Pi, Ollama, Gemma 4" (URL 404'd on fetch) |
| `"pi-mono" repository github` | github.com/badlogic/pi-mono → redirects to **github.com/earendil-works/pi**, qualisero/awesome-pi-agent, hochej.github.io/pi-mono docs, manaflow-ai/pi-mono-1 (fork) |
| `"pi-mono" browser agent` | algopian/chromeclaw (Chrome extension built on pi-mono), kashodiya/pi-browser, deepwiki pi-web-ui, agent-safehouse.dev sandbox analysis |

`gh search repos` (relevance order, top results):

| Query | Notable matches |
|---|---|
| `pi-mono` | `qualisero/awesome-pi-agent`, `ZhangHanDong/pi-book`, `emanuelcasco/pi-mono-extensions`, `sysid/pi-extensions`, `Dwsy/pi-session-manager`, `m-sec-org/BreachWeave` (pentest agent on pi-mono SDK), `aebrer/dreb` (hard fork), `openxjarvis/pi-mono-python` (Python port), `code-yeongyu/senpi` (opinionated fork) |
| `pimono` | `Keke-nA/learn-pimono`, `Denveous/pimono-mcp`, plus many unrelated "Pimono" wallet/CRM repos (Indonesian fintech named Pimono — clearly not the target) |
| `phi-mono` | All hits unrelated (university monographs about phishing, MonoGame student projects). Not the target. |
| `--owner principal-labs` | Org does not exist (search returned "resources do not exist or you do not have permission"). Not the target. |

`gh search code` (relevance order, top results):

| Query | What it tells us |
|---|---|
| `pi-mono` | `castai/kimchi` AGENTS.md says "extends the pi-mono SDK (`@earendil-works/pi-coding-agent`)"; `daydreamsai/daydreams` recommends "Pi agent harness" for agent building; `algopian/chromeclaw` CLAUDE.md says Chrome extension is built with React + pi-mono (`@mariozechner/pi-ai` + `@mariozechner/pi-agent-core`); plus dozens of forks/wrappers |
| `@mariozechner/pi-agent-core` | 20+ third-party repos importing this package as their agent core (Bitterbot-AI/bitterbot-desktop, oujingzhou/openmozi, pasky/muaddib, larsderidder/bryti, BodhiSearch/BodhiApp, etc.) |
| `@earendil-works/pi-agent-core` | Newer published namespace (post-rename). Examples: `openclaw/openclaw`, `traceroot-ai/traceroot`, `hewliyang/office-agents`, `eforge-build/eforge`, `nicobailon/pi-subagents`. NixOS/nixpkgs even ships `pi-coding-agent/package.nix`. |

## Ranked candidates

| # | Candidate | Repo | Stars | Confidence | Notes |
|---|---|---|---|---|---|
| 1 | **Mario Zechner's `pi-mono` / `pi`** | `badlogic/pi-mono` → moved to `earendil-works/pi` | **52,971** | **HIGH** | Trending in OSS-monthly-rank for 2026-05. Direct match for the term "pi-mono agent". Dataset also published as `badlogicgames/pi-mono` on Hugging Face. Author = Mario Zechner (badlogic, libGDX). Description: "AI agent toolkit: coding agent CLI, unified LLM API, TUI & web UI libraries, Slack bot, vLLM pods". |
| 2 | Forks of #1 | `manaflow-ai/pi-mono-1`, `aebrer/dreb`, `code-yeongyu/senpi`, `openxjarvis/pi-mono-python`, `jshachm/pi-rs` | varies | HIGH | All explicitly cite badlogic/pi-mono as upstream. |
| 3 | Pimono wallet (Indonesian fintech) | many `pimono-wallet*` repos | low | LOW-NEGATIVE | Coincidental name collision. Unrelated to AI agents. |
| 4 | Microsoft Phi small models ("phi-mono"?) | n/a | n/a | NONE | No artifact called "phi-mono" exists. Phi is Microsoft's small-model family but there is no "phi-mono" monorepo. |
| 5 | `principal-labs/pi-mono` or `pi-labs/pi-mono` | does not exist | n/a | NONE | Org doesn't exist on GitHub. |
| 6 | Inflection's "Pi" personal-intelligence chatbot | n/a | n/a | NONE | Different product, no developer-facing "pi-mono" artifact. |

## Verdict

**HIGH confidence: the user is referring to `badlogic/pi-mono` (now `earendil-works/pi`), Mario Zechner's TypeScript monorepo for AI agent infrastructure.** 52k stars, actively developed (last push 2026-05-22), trending in May 2026 monthly rank. The ecosystem name is unambiguous — every third-party reference uses the term "pi-mono" interchangeably with "pi" or "@earendil-works/pi-*".

URLs verified:
- https://github.com/badlogic/pi-mono (canonical, redirects)
- https://github.com/earendil-works/pi (current home)
- https://deepwiki.com/badlogic/pi-mono (community wiki)
- https://huggingface.co/datasets/badlogicgames/pi-mono (training dataset of real coding sessions)
