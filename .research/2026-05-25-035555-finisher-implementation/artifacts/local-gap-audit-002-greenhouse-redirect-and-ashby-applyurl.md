# local-gap-audit-002 — Greenhouse host redirect + Ashby applyUrl coverage

**Source:** `src/agents/apply_worker/browser.py:_normalize_apply_url` (lines 122-138), `_run_application_flow` path-compare logic (lines 261-329), `src/fetchers/ashby_fetcher.py:_parse_job` (lines 114-164), and a live API probe of Notion's Ashby board on 2026-05-25.
**Trigger:** Commit `1145c5c` "fix(apply): normalize Lever apply URL and prefer Ashby applyUrl" — gap audit confirms the new logic against the 3 Ashby target URLs in `.research/simplify-loop/targets.txt`.

## 1. `_normalize_apply_url` covers Lever only

```python
def _normalize_apply_url(source_url: str) -> str:
    parsed = urlparse(source_url)
    if parsed.netloc == "jobs.lever.co":
        path = parsed.path.rstrip("/")
        if path and not path.endswith("/apply"):
            return f"{parsed.scheme}://{parsed.netloc}{path}/apply"
    return source_url
```

**Greenhouse is NOT rewritten** — and intentionally so. Greenhouse uses a server-side 301 redirect from `boards.greenhouse.io/cloudflare/jobs/7729700` → `job-boards.greenhouse.io/cloudflare/jobs/7729700`. Path is identical; only netloc changes. Confirmed live on 2026-05-25:

```
HTTP/2 301
location: https://job-boards.greenhouse.io/cloudflare/jobs/7729700
```

## 2. `_run_application_flow` path-only compare handles the GH redirect correctly

Lines 305-318 of `browser.py`:

```python
current_url = playwright_page.url
needs_navigate = (
    urlparse(current_url).path.rstrip("/")
    != urlparse(normalized_url).path.rstrip("/")
)
```

This compares only `path` (not netloc + path), so when the browser has already followed the GH redirect and `current_url` is `https://job-boards.greenhouse.io/cloudflare/jobs/7729700` while `normalized_url` is `https://boards.greenhouse.io/cloudflare/jobs/7729700`, `needs_navigate=False` — correct.

**Caveat:** this is more permissive than strict equality. Two URLs with identical paths but different netlocs are treated as the same page. For Lever (host stable, path changes via `/apply`) and Greenhouse (host changes via redirect, path stable) this is the right call. **There is no scenario today where two different actual job pages share the same path on different hosts**, so the false-positive risk is negligible.

**Potential blind spot:** if a future ATS uses sub-paths on the same domain (e.g., `acme.com/jobs/123` vs `acme.com/board/123`), this comparator would treat them as different — fine. But if two domains use `/apply` as the path for unrelated workflows (e.g., `boards.greenhouse.io/apply` vs `jobs.lever.co/{co}/apply`), the comparator would say "no navigate" when navigating is needed. For v1 with only GH + Ashby in scope, this is a non-issue. Worth a code comment noting the assumption.

## 3. Ashby `applyUrl` coverage on all 3 target jobs

Live API probe of `https://api.ashbyhq.com/posting-api/job-board/Notion` (board has 131 jobs total) on 2026-05-25:

| Target ID | Role | `applyUrl` | `jobUrl` |
|---|---|---|---|
| `05e14247-…` | Outbound BDR | ✅ present (`/application` suffix) | ✅ present |
| `e3944777-…` | App Sec Engineer, AI Security | ✅ present (`/application` suffix) | ✅ present |
| `91156750-…` | SWE, Data Platform | ✅ present (`/application` suffix) | ✅ present |

`applyUrl` is `<jobUrl>/application` for all three. The fetcher's `applyUrl or jobUrl` preference (line 145) lands directly on the form. **Fallback path at lines 146-149 (manual `f"https://jobs.ashbyhq.com/{self.board_id}/{posting_id}/application"`) is unreachable for these targets** because both fields are populated.

## 4. Implications

- **The epic's "wait for stable DOM" gate (300ms idle)** does not need to also re-resolve URLs — `_run_application_flow` already handles the post-redirect resolution before the finisher is invoked.
- **The Ashby finisher** can assume URL ends in `/application` and the form is the visible content. No additional click-Apply step required.
- **No additional URL-normalization helper needed** for Greenhouse or Ashby in v1.

## 5. Locked decisions to sanity-check

- The epic body lists targets at `.research/simplify-loop/targets.txt`. All 3 Ashby URLs use `/application` directly (these are the canonical applyUrl values). **The epic acceptance criteria for Phase C reference "the Notion BDR URL" but should explicitly note `/application` suffix** — otherwise a tester running `https://jobs.ashbyhq.com/Notion/05e14247-…` (no suffix) will land on the listing page, which has different content and DOM. Minor doc clarification.
