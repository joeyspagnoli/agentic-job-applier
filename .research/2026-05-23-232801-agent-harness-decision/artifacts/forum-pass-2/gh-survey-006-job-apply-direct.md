# GH Survey 006 — LinkedIn Easy Apply / Auto-Apply Repos

Date: 2026-05-24
Commands:
- `gh search repos "autoapply OR auto-apply OR linkedin-easy-apply" --language python --limit 10` → 0 results
- `gh search repos "linkedin easy apply" --language python --sort=stars --limit 10` → results below

| Repo | Stars | Last Updated | Stack |
|------|-------|--------------|-------|
| NathanDuma/LinkedIn-Easy-Apply-Bot | 256 | 2026-05-16 | Selenium + PyYAML (NO LLM) |
| aminblm/linkedin-application-bot | 201 | 2026-05-16 | Selenium |
| madingess/EasyApplyBot | 170 | 2026-05-11 | Selenium |
| pranavvkumar21/the_last_application | 4 | 2026-04-27 | **LangChain RAG + NoDriver + DuckDB** |
| pratikjadhav2726/LinkedInApplyAutomation | 9 | 2026-04-16 | Selenium + LiteLLM + Ollama |
| voidbydefault/linkedin-easyapply-ai | 8 | 2026-05-17 | Gemini AI + (Playwright implied) |
| Eezzeldin/LinkedinEasyApplybot | 8 | 2026-05-03 | Selenium |
| matthewalunni/easy-apply-bot | 10 | 2024-05-22 | Selenium |

## Analysis

### Dominant pattern in job-apply bots: Selenium + no LLM harness

The top 3 repos (256+201+170 stars) use Selenium + rules-based logic — no LLM harness at all. These predate the LLM browser-agent era but remain most-starred because they work.

### LLM-powered job-apply repos use:

1. **pranavvkumar21/the_last_application** — LangChain RAG (explicit harness choice: `langchain`)
   - Description: "LangChain RAG over your resume PDFs for smart form answers"
   - Uses NoDriver for stealth browsing

2. **pratikjadhav2726/LinkedInApplyAutomation** — LiteLLM + Selenium (custom loop, no harness framework)

3. **beatwad/LinkedIn-AI-Job-Applier-Ultimate** — browser-use + LangChain (see survey-005)

### Takeaway for our project

Our project (agentic-job-applier) is at the frontier: most existing job-apply bots either use no LLM at all, or use LangChain as the harness with browser-use as the browser layer. The Google ADK path we've adopted is not yet widely represented in the job-apply open-source ecosystem — we're ahead of the curve.
