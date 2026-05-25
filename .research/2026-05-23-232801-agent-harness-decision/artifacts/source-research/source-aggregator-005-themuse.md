# source-aggregator-005-themuse.md
## The Muse: Landing Page + External ATS

### What `source_url` Resolves To
The Muse fetcher uses `refs.landing_page` from the API — this is a URL like:
`https://www.themuse.com/jobs/<company>/<role-slug>`

This is The Muse's own landing/branding page for the job, NOT a direct ATS link.

### Apply Flow
From The Muse landing page, the "Apply Now" button redirects to the **company's ATS** (Greenhouse, Lever, Workday, custom). The Muse documentation explicitly states: "When a candidate clicks Apply Now, they'll be redirected from your profile to your external ATS."

This means:
1. Navigate to `themuse.com/jobs/<company>/<role-slug>`  ← worker lands here
2. Click "Apply Now" button  ← opens new tab OR navigates current page to ATS
3. ATS form is the actual application destination

### New Tab vs Same-Tab Navigation
The Muse's "Apply Now" button behavior varies:
- Some listings: `<a href="..." target="_blank">` → new tab
- Others: JavaScript redirect in same tab

The worker needs to handle both cases. The safest approach is to intercept `context.on('page', ...)` to catch new-tab spawns, and also handle same-tab navigation.

### Dead URL Rate on The Muse
The Muse's API tends to return listings that remain live because The Muse partners with employers who maintain their profiles. However listings are not immediately removed when positions close. The liveness_checker will catch "no longer accepting applications" pages but The Muse itself may not show an expiry signal — the ATS URL reached from the landing page might 404 instead.

### Simplify Coverage
The Muse landing page itself has no form — Simplify doesn't trigger there. Once the worker reaches the ATS (Greenhouse/Lever/Workday), Simplify activates on that ATS form normally.

### Sources
- The Muse developer docs (PDF): "When a candidate clicks Apply Now, they'll be redirected from your profile to your external ATS"
- The Muse API returns `refs.landing_page` per the themuse_fetcher.py implementation
