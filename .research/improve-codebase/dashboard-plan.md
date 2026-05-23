# Dashboard Refactor Plan (SettingsPage.tsx + OnboardingPage.tsx)

## SettingsPage.tsx (3513 lines → <250)

```
dashboard/src/pages/settings/
  BudgetSettings.tsx           # ~250 — budgetQuery, updateBudget
  ApiKeysSettings.tsx          # ~350 — apiKeysQuery, upsert/delete + edit-row state
  ServiceTierSettings.tsx      # ~250 — tierQuery, updateServiceTier, missing-key check
  GeneralSettings.tsx          # ~80  — composes the 3 above (the "general" tab)
  AIProviderSettings.tsx       # already exists — no change
  ProfileSettings.tsx          # ~600 — guided + yaml + files sub-tabs + resume migration banner
  ResumeSettings.tsx           # ~700 — guided + yaml + tex + files sub-tabs
  CandidateSettings.tsx        # ~80  — sub-tab router for Profile/Resume
  FiltersSettings.tsx          # ~500 — guided + yaml editor
  SourcesSettings.tsx          # ~120
  FiltersAndSourcesSettings.tsx # ~80 — sub-tab router
  components/
    TabButton.tsx
    LabeledInput.tsx
    LabeledSelect.tsx
    LabeledTextarea.tsx
    SettingsFileCard.tsx
    YamlEditor.tsx
    InlineErrorText.tsx

dashboard/src/lib/settings/
  types.ts        # FiltersGuidedDraft, ApiKeyConfig, ServiceTierCard, FeedbackMessage, SelectOption, tab unions
  transforms.ts   # toProfileDraft, toResumeDraft, parseFiltersGuidedDraft, serializeFiltersGuidedToYaml, listToLines, linesToList, nextGeneratedId, buildDefaultEducationEntry, buildConfiguredKeyMap, getMissingKeysForTier, countListItems, getErrorMessage
  constants.ts    # JOB_TYPES, API_KEYS, TOP_LEVEL_TABS, EDITOR_HEIGHT_PX, service-tier card metadata
```

Migration order:
1. Move pure helpers + types + constants to `lib/settings/`. Zero behavior change.
2. Extract shared primitives.
3. Budget → ApiKeys → ServiceTier (independent queries).
4. Sources → Filters → FiltersAndSources.
5. Profile → Resume (most cross-state).

Risk: medium. Hot spots: shared `selectedServiceTier` + `queryClient.invalidateQueries` keys (keep keys identical).

## OnboardingPage.tsx (1999 lines → <250)

Step components are already inline functions — easy lift.

```
dashboard/src/pages/onboarding/
  StepProfile.tsx        # ~120
  StepRoles.tsx          # ~80
  StepResume.tsx         # ~80
  StepFilters.tsx        # ~140
  StepProvider.tsx       # ~200
  StepWatchlist.tsx      # ~50
  Field.tsx              # ~60
  ProgressIndicator.tsx  # ~70
  NavigationButtons.tsx  # ~90

dashboard/src/lib/onboarding/
  types.ts        # ProfileDraft, RolesDraft, FiltersDraft, ProviderDraft, WatchlistDraft, step props
  defaults.ts     # defaultProfileDraft, defaultRolesDraft, defaultFiltersDraft, defaultProviderDraft
  yaml-builders.ts # buildFiltersYaml, buildGithubReposBlock, extractDomainKeywords, deriveRequireTitlePatterns, detectSimplifyCategories, escapeYamlDoubleQuoted, toYamlDoubleQuoted, escapeYamlMappingKey, splitLines, role keyword constants
  watchlist.ts    # buildWatchlistWarning, validateGreenhouseSlug, resolveGreenhouseSlug, saveWatchlistCompanies, seedGithubRepos
  constants.ts    # STEP_COUNT, STEP_LABELS, WATCHLIST_WARNING_REDIRECT_DELAY_MS, KNOWN_SLUGS loader
```

State management: **Keep state in OnboardingPage.tsx parent**. No context, no zustand. The step components already accept draft+onChange props.

Test file split (OnboardingPage.test.ts is 1837 lines, mostly pure helpers):
```
dashboard/src/lib/onboarding/yaml-builders.test.ts
dashboard/src/lib/onboarding/watchlist.test.ts
```
Keep `OnboardingPage.integration.test.tsx` (293 lines) as the component test.

Migration order:
1. types/defaults/constants
2. yaml-builders + split that test file
3. watchlist + split that test file
4. Field/ProgressIndicator/NavigationButtons
5. Step components: Watchlist → Resume → Roles → Profile → Filters → Provider

Risk: low.
