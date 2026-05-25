# source-aggregator-007-cloudflare.md
## Cloudflare Bot Detection: Risk Assessment for the Worker

### Core Question
Will aggregator pages (Indeed, Glassdoor, ZipRecruiter) block our worker's Playwright navigation?

### Why Headed Chrome with User Session is Different
Standard Playwright automation against Cloudflare-protected sites fails because:
1. **Headless detection**: `navigator.webdriver = true`, missing `window.chrome`, headless-specific UA strings
2. **Fingerprint mismatch**: Canvas fingerprint, WebGL renderer, font enumeration differ from real Chrome
3. **No cookies**: Cold sessions trigger Cloudflare's JS challenge

Our worker is different on all three counts:
- **Headed Chrome** (not headless) with `--remote-debugging-port` CDP attachment
- **User's real Chrome binary** (not Playwright's bundled Chromium)
- **Existing user profile with cookies**: Indeed, Glassdoor, LinkedIn sessions are pre-authenticated

### Cloudflare Detection Likelihood per Aggregator

| Site | CF Level | With User Chrome + Cookies | Risk |
|------|----------|---------------------------|------|
| Indeed | Medium | User is logged in, real Chrome | LOW |
| Glassdoor | Medium | User is logged in, real Chrome | LOW |
| ZipRecruiter | Low | No CF, rate limiting only | VERY LOW |
| LinkedIn | High CF + own detection | User logged in, real Chrome | LOW-MEDIUM |
| Adzuna listing pages | Low | Public redirect, no CF | VERY LOW |
| ATS destinations | Low | Greenhouse/Lever/Workday have minimal bot detection | VERY LOW |

### Exceptions and Edge Cases
1. **Navigation speed**: If the worker navigates to multiple Indeed/Glassdoor pages in rapid succession (< 2 seconds between page loads), behavioral analysis CAN trigger a soft block even with real cookies. The worker should enforce a minimum navigation delay between jobs.
2. **Glassdoor PerimeterX**: Glassdoor specifically uses PerimeterX (PX) in addition to Cloudflare. PX analyzes mouse movement patterns. Since we're attaching to the user's actual Chrome session, PX's JS-based fingerprinting sees the same profile it always has — but if Playwright's CDP commands generate non-human-like mouse events, PX could still flag it. Using Playwright's `page.mouse.move()` with random offsets mitigates this.
3. **IP-based throttling**: Glassdoor and Indeed track by IP. The Mac host → Docker container vpnkit proxy IP (172.66.0.243) issue is documented in project memory. If the worker runs in Docker, the outbound IP shows as the VPN gateway — this could trigger "unusual location" soft blocks if the user typically browses from a different IP.
4. **CAPTCHA fallthrough**: Even with all mitigations, ~1–3% of sessions will hit a CAPTCHA wall. These must route to NEEDS_REVIEW.

### Research Findings
- Browserless 2026 guide: "Playwright, stealth plugins... needed to bypass Cloudflare" — but those apply to headless/cold sessions, not headed+session
- Stack Overflow thread: "Works if I use regular urls but fails with headless Chrome" — confirms headed is the key differentiator
- Multiple community posts: headed Chrome with real user profile is the gold standard for avoiding CF detection

### Verdict
**LOW risk** for our specific architecture (headed Chrome + user cookies). The remaining risk is behavioral (mouse/keyboard timing) and IP-based. Both are manageable with navigation delays and human-like interaction patterns.

### Sources
- Browserless.io: "Bypass Cloudflare with Playwright BQL 2026 Guide"
- Medium: "How to bypass Cloudflare bot detection"
- Stack Overflow: "playwright cannot bypass cloudflare bot detection even adding cookies"
- GitHub issue #2198: "Improve bot-detection evasion techniques"
