# GH Survey 005 — Job Application Bot Python Repos

Date: 2026-05-24
Command: `gh search repos "job application bot" --language python --sort=stars --limit 10`

| Repo | Stars | Last Updated | Stack |
|------|-------|--------------|-------|
| beatwad/LinkedIn-AI-Job-Applier-Ultimate | 95 | 2026-05-23 | **browser-use + LangChain + Playwright + patchright** |
| koshini07122006-dot/job-application-bot | 22 | 2026-05-24 | Unknown |
| RayeesYousufGenAi/multi-platform-job-apply-bot | 7 | 2026-05-19 | Multi-platform (LinkedIn, Indeed, Naukri, Glassdoor) |
| Saraswat123/job-agent | 2 | 2026-05-17 | Gmail API + Playwright Easy Apply |
| it5prasoon/JobApplicationBot | 2 | 2024-07-17 | Old |
| Freddy-S3/Job-Application-Bot | 2 | 2024-07-17 | Old |
| Somvit09/Job_application_bot | 1 | 2021-09-24 | Old |
| Smaragdus7/job-application-bot | 1 | 2022-07-22 | Selenium |
| Warmachine019/Job-Application-bot | 1 | 2025-01-14 | Selenium |
| federico-dot/Job-Application-Bot | 1 | 2026-04-15 | Python (recent) |

## Deep Dive: beatwad/LinkedIn-AI-Job-Applier-Ultimate (95 stars, most-starred, active)

**requirements.txt analysis:**
```
browser-use==0.9.5          # browser layer
langchain==0.3.23            # AGENT HARNESS
langchain-anthropic==0.3.10
langchain-community==0.3.14
langchain-core==0.3.51
langchain-google-genai==2.1.2
langchain-ollama==0.3.1
langchain-openai==0.3.12
playwright==1.58.0
patchright==1.58.2           # stealth Playwright fork
```

**Key finding**: This is the most-starred recently-active job applier Python bot, and it uses:
- **Harness**: LangChain (multi-provider: Anthropic, Google, Ollama, OpenAI)
- **Browser layer**: browser-use (wrapping their own Playwright) + patchright for anti-detection

**Rationale inferred**: LangChain chosen for multi-provider support (single interface to OpenAI, Anthropic, Google, Ollama). browser-use handles the browser loop, LangChain handles the orchestration/chain logic.

## Deep Dive: pratikjadhav2726/LinkedInApplyAutomation (9 stars)

**requirements.txt analysis:**
```
selenium                # browser layer
litellm                 # model routing (NOT a harness, just model proxy)
ollama                  # local models
sentence-transformers   # embedding for RAG
faiss-cpu               # vector store
openai>=1.0.0
```

**Key finding**: Uses LiteLLM for model routing but NO agent harness framework — BYO loop with Selenium.

## Pattern from job-apply-bots

- Most job bots use Selenium (old approach, pre-LLM era)
- Newer LLM-powered ones: browser-use for browser layer + either LangChain (multi-provider use case) or pure custom loop
- No job-apply bot uses Google ADK, OpenAI Agents SDK, or Pydantic AI as the harness
