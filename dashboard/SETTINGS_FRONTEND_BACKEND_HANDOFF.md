# Settings Frontend -> Backend Handoff (2026-03-29)

## Frontend changes implemented

### 1) Core Context revamp in guided Candidate Profile

The old three-field Core Context (`summary`, `education`, `citizenship`) was replaced with a structured profile model:

- `summary` is now a multiline textarea with a character counter.
- `contact` section added:
  - `full_name`, `email`, `phone`, `city`, `state_or_region`
  - `country_code`, `country_label`
  - `linkedin_url`, `github_url`, `portfolio_url`
- `work_authorization` section added:
  - `citizenship_country_code`, `citizenship_country_label`
  - `authorized_to_work_us` (`yes | no | unknown`)
  - `requires_sponsorship_now_or_future` (`yes | no | unknown`)
- `education_summary` added.
- `education_entries[]` added as repeatable structured rows:
  - `id`, `school`, `degree_level`, `degree_name`, `field_of_study`
  - `start_month`, `start_year`, `end_month`, `end_year`, `is_current`
  - `gpa`, `location`, `highlights[]`

UI behavior:
- Education rows are add/remove editable cards.
- Citizenship is a dropdown sourced from an ISO-3166 country list with **United States pinned first**.

### 2) Resume editor gating behavior

- Candidate Profile remains always visible.
- Resume Editor remains conditional to service tier `latex` or `full`.

### 3) API keys and tier gating (frontend)

- Tier select behavior remains blocked for:
  - `latex` without `OPENAI_API_KEY`
  - `full` without `OPENAI_API_KEY`
- Base tier remains default and always selectable.

### 4) Frontend contract and schema updates

Updated frontend contract surfaces:
- `dashboard/src/lib/api/types.ts`
- `dashboard/src/lib/api/client.ts`
- `dashboard/src/lib/monaco/yaml-config.ts`
- `dashboard/src/pages/SettingsPage.tsx`
- Added country constants: `dashboard/src/lib/constants/countries.ts`

## Backend updates required

## 1) Update structured profile payload models

Current backend profile payload models still expect legacy fields:
- `profile.education: string`
- `profile.citizenship: string`

Backend now needs to accept and persist this new shape for `profile`:

```json
{
  "summary": "string",
  "contact": {
    "full_name": "string",
    "email": "string",
    "phone": "string",
    "city": "string",
    "state_or_region": "string",
    "country_code": "string",
    "country_label": "string",
    "linkedin_url": "string",
    "github_url": "string",
    "portfolio_url": "string"
  },
  "work_authorization": {
    "citizenship_country_code": "string",
    "citizenship_country_label": "string",
    "authorized_to_work_us": "yes|no|unknown",
    "requires_sponsorship_now_or_future": "yes|no|unknown"
  },
  "education_summary": "string",
  "education_entries": [
    {
      "id": "string",
      "school": "string",
      "degree_level": "string",
      "degree_name": "string",
      "field_of_study": "string",
      "start_month": "string",
      "start_year": "string",
      "end_month": "string",
      "end_year": "string",
      "is_current": true,
      "gpa": "string",
      "location": "string",
      "highlights": ["string"]
    }
  ],
  "target_roles": ["string"],
  "strongest_areas": ["string"],
  "experience_highlights": ["string"],
  "hard_filters": ["string"],
  "preferences": ["string"]
}
```

Affected backend pydantic models to update:
- `CandidateProfileSectionPayload`
- `CandidateProfileDocumentPayload`
- `ProfileStructuredUpdateRequest`

## 2) Update normalization/output payload

`GET /api/settings/profile` and structured update responses must return the new profile fields under `profile` so guided UI can hydrate without fallback.

Any normalization helper that currently emits `education`/`citizenship` strings should be switched to emit the new structured sections.

## 3) Update candidate profile YAML schema/file expectations

Persisted `config/candidate_profile.yaml` should now support:
- `profile.contact`
- `profile.work_authorization`
- `profile.education_summary`
- `profile.education_entries[]`

Legacy keys can be dropped in this forward-only phase.

## 4) Update downstream prompt/context builders

Any agent prompt assembly currently reading:
- `profile.education`
- `profile.citizenship`

must be migrated to use:
- `profile.education_summary`
- `profile.education_entries[]` (as needed)
- `profile.work_authorization.*`

Primary known surface:
- `src/agents/root_apply_decider/prompts.py`

## 5) Optional validation rules (recommended)

Add backend validation for:
- `authorized_to_work_us` enum values (`yes|no|unknown`)
- `requires_sponsorship_now_or_future` enum values
- `citizenship_country_code` and `contact.country_code` as ISO alpha-2 codes
- `education_entries[].id` uniqueness

## Endpoints impacted

- `GET /api/settings/profile`
- `PUT /api/settings/profile`
- `PUT /api/settings/profile/structured`

API key and service-tier endpoints remain as previously handed off.

## Verification run (frontend)

- `npm --prefix dashboard run typecheck`
- `cd dashboard && npx eslint src/pages/SettingsPage.tsx src/lib/api/types.ts src/lib/api/client.ts src/lib/monaco/yaml-config.ts src/lib/constants/countries.ts --max-warnings 0`

## Scope reminder

- This pass made **frontend-only** edits.
- No backend code was modified.
