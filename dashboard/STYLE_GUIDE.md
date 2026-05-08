# AutoApply Dashboard UI Style Guide (for Google Stitch)

## 1) Scope and Intent

This document is a **product UI style guide** for the current AutoApply dashboard implementation.
It is **not** a full design system.

Use this guide to keep generated UI consistent with the existing app, especially for the Settings experience and upcoming tabbed settings window.

Primary goals:

- Match current dashboard visual language exactly.
- Give Stitch concrete token and component rules that frontend engineers can implement directly.
- Prevent drift from mixed styles currently present in the codebase.

## 2) Existing Visual Language Baseline

Based on current implementation (`AppLayout`, `Sidebar`, `TopBar`, `SettingsPage`) and Playwright screenshots:

- App shell: fixed left sidebar + sticky top bar + scrolling main content.
- Global background: light neutral (`#f8f9fa`).
- Primary surfaces: white cards/sections with very light borders.
- Visual mood: clean, restrained, utility-first dashboard (not marketing/brand-heavy).
- Settings page is long-form and section-based; each section is a white rounded container with internal grouped controls.

## 3) Canonical Tokens

Source of truth: `dashboard/src/lib/design-tokens.ts`.

### Color tokens

- `COLOR_PRIMARY`: `#4648d4`
- `COLOR_PRIMARY_CONTAINER`: `#6063ee`
- `COLOR_PRIMARY_FIXED`: `#e1e0ff`
- `COLOR_ON_SURFACE`: `#191c1d`
- `COLOR_ON_SURFACE_VARIANT`: `#464554`
- `COLOR_OUTLINE`: `#767586`
- `COLOR_OUTLINE_VARIANT`: `#c7c4d7`
- `COLOR_SURFACE`: `#f8f9fa`
- `COLOR_SURFACE_CONTAINER_LOWEST`: `#ffffff`
- `COLOR_SURFACE_CONTAINER_LOW`: `#f3f4f5`
- `COLOR_SURFACE_CONTAINER`: `#edeeef`
- `COLOR_SURFACE_CONTAINER_HIGH`: `#e7e8e9`
- `COLOR_SECONDARY`: `#4953bc`
- `COLOR_ERROR`: `#ba1a1a`
- `COLOR_ERROR_CONTAINER`: `#ffdad6`
- `COLOR_ON_ERROR_CONTAINER`: `#93000a`
- `COLOR_JOBSPY_SEGMENT`: `#ffd4b8`

### Layout and z-index tokens

- `SIDEBAR_WIDTH_PX`: `220`
- `SETTINGS_PANEL_WIDTH_PX`: `480` (legacy slide-out width; still useful as a tabbed-window target width for constrained contexts)
- `Z_SIDEBAR`: `50`
- `Z_TOPBAR`: `40`
- `Z_SETTINGS_BACKDROP`: `60`
- `Z_SETTINGS_PANEL`: `70`

## 4) Typography Standards (Current + Normalized)

### Current usage observed

- `index.css` declares `Inter` for app font tokens/body.
- Tailwind inline theme remaps `--font-sans` to `Geist Variable`.
- Result: mixed `Inter` and `Geist` potential depending on class usage.

### Canonical decision for Settings work

- Use `Inter, system-ui, sans-serif` as the default font family for Settings UI.
- Keep visual hierarchy already used:
- Page title/topbar: bold, large (`text-2xl`).
- Section title: `text-xl font-bold`.
- Card title/subsection title: `text-sm` to `text-lg`, semibold/bold.
- Body/form text: `text-sm`.
- Assistive/meta labels: `text-xs`.

### Readability constraints

- Minimum body/field text target: **16px preferred for long text; never below 14px for critical controls**.
- Settings labels and helper text should remain clearly legible at 100% zoom and at 200% zoom.

## 5) Layout, Spacing, Radius, Elevation

### App shell

- Sidebar fixed left, width `220px`.
- Main content offset by sidebar width.
- Top bar sticky with subtle translucent background and bottom border.

### Settings page container

- Outer: `max-w-7xl`, centered, `p-8`, vertical rhythm `space-y-8`.
- Section blocks: white surface, `rounded-2xl`, light border, `p-6`, `space-y-5`.

### Internal spacing rhythm

- Primary gaps: 8, 12, 16, 24, 32 px equivalents (`gap-2`, `gap-3`, `gap-4`, `gap-6`, `space-y-8`).
- Form rows commonly use `grid` with `gap-3`/`gap-4` and responsive column collapse.

### Radius conventions

- Section containers: `rounded-2xl`.
- Cards/edit panels: `rounded-xl`.
- Inputs/buttons (standard): `rounded-lg`.
- Pills/chips/tab toggles: `rounded-full`.

### Elevation conventions

- Settings sections: mostly border-defined, minimal shadow.
- Dashboard cards: light soft shadow (`ambient-shadow`) where needed.
- Avoid heavy/drop shadows that introduce a new visual language.

## 6) Component Patterns to Preserve

### Tab pills

Pattern from Settings internal tabs:

- Size: compact pill (`px-3 py-1.5`).
- Typography: `text-xs font-semibold`.
- Active: primary fill, white text, matching primary border.
- Inactive: white fill, muted text, light border.

### Cards and grouped panels

- Outer sections: white, rounded, light border.
- Nested groups: `bg-slate-50`-style light container, rounded-xl, light border.

### Buttons

- Primary action: solid `COLOR_PRIMARY`, white text, semibold.
- Secondary action: white/light surface with subtle border.
- Destructive text actions: error red tone.
- Save actions are right-aligned where appropriate.

### Text inputs and textareas

- Surface: muted light background.
- Border: light neutral border.
- Radius: `rounded-lg`.
- Label above field, semibold small text.

### YAML editor blocks

- Container: rounded-xl with light border and clipped overflow.
- Monospace editor content is allowed inside only the editor region.
- Preserve explicit loading/error text above/below editor.

### Alert banners

- Warning: amber-tinted background + border + dark amber text.
- Error: red-tinted background + border + dark red text.
- Success snippets: green text/soft green treatment for positive completion.

## 7) Interaction and State Standards

### Hover

- Nav and tertiary controls may shift to subtle surface tint on hover.
- Text links use underline-on-hover or color shift, not both heavy effects.

### Focus / keyboard

- All interactive controls must have visible keyboard focus.
- Prefer `:focus-visible` to avoid always-on mouse focus rings.
- Never remove focus ring without replacement.

Recommended focus style (token-aligned):

- Outer ring: `3px solid #4648d4` (`COLOR_PRIMARY`)
- Offset: `2px`
- Ensure at least 3:1 non-text contrast against adjacent colors.

### Active/pressed

- Keep current subtle pressed affordance (`scale-98-on-click` or slight translate) for buttons where used.
- Active tab state must be visually persistent and not hover-dependent.

### Disabled

- Use reduced opacity plus blocked interaction.
- Disabled controls should still be readable and discoverable.

### Loading, error, success messaging

- Loading: direct verb-first labels (`Saving...`, `Uploading...`, `Converting...`).
- Error: concise red inline/system banners with retry context.
- Success: concise confirmation text near related control.

## 8) Accessibility Baseline

- Text contrast: target WCAG AA minimums (normal text 4.5:1, large text 3:1).
- Non-text contrast: controls/focus indicators must meet 3:1 against adjacent colors.
- Focus indicators must be clearly visible, keyboard-triggered, and not obscured by sticky/fixed elements.
- Body copy should be comfortably readable; avoid dense tiny helper text for critical instructions.
- Minimum hit area: **24x24 CSS px absolute minimum**, **40-44px preferred** for touch-friendly controls.
- Do not rely on color alone for critical state communication (use label/icon/text support where needed).

## 9) Settings Tabbed Window Guidance (Upcoming)

Preserve current styling language. Do not visually rebrand.

### Top-level tabs

Use these top-level tabs in order:

1. Candidate Preferences
2. Edit Resume
3. Websites
4. Advanced / File Actions (optional)

### Information hierarchy

- Top-level tabs switch major domains only.
- Existing sub-modes stay inside each tab as secondary pills when needed (example: Guided / YAML / Files).
- Keep Save actions contextual to each tab’s panel content.

### Behavior

- Default open tab: `Candidate Preferences`.
- Persist active tab in URL query or local state per session.
- Preserve unsaved-change protection when switching tabs.
- Keep tab labels short and sentence-case.

### Responsive behavior

- Desktop: horizontal tab row at top of Settings content card.
- Tablet: allow horizontal scroll for tab row if needed.
- Mobile: transform tab row to segmented control or stacked selector while preserving tab order and states.

## 10) Current Inconsistencies and Canonical Decisions

Addressing observed drift directly:

1. Font inconsistency (`Inter` vs `Geist Variable`)

- Decision: Settings UI uses `Inter` as canonical face for now.

2. Tokenized colors vs hardcoded Tailwind indigo/slate

- Decision: prefer design token colors for primary semantic roles (`primary`, text, outline, error).
- Tailwind neutrals may remain for utility backgrounds/borders when visually equivalent, but no new arbitrary indigo shades.

3. Focus styling inconsistency

- Decision: standardize on explicit `:focus-visible` treatment for all custom controls in Settings.

4. Mixed card emphasis (shadow-heavy vs border-only)

- Decision: Settings remains low-elevation, border-first; ambient shadow is optional and sparse.

5. Varying border opacities and ad-hoc hex alpha

- Decision: keep subtle borders but normalize to token-derived outline variants for new Settings work.

## 11) Stitch Implementation Constraints

### Do

- Reuse the exact token palette listed above.
- Keep sidebar/topbar/main shell structure unchanged.
- Use rounded-2xl section containers, rounded-xl nested panels, rounded-lg fields/buttons.
- Keep tab pills compact and clear (`text-xs`, semibold, rounded-full).
- Include clear loading/error/success states in each editable tab.
- Apply explicit keyboard focus-visible styles on all interactive controls.

### Don’t

- Don’t introduce new brand colors, gradients, glassmorphism, or dark theme variants for this task.
- Don’t replace shell/navigation structure.
- Don’t mix multiple visual languages (e.g., Material-heavy widgets inside otherwise minimal cards).
- Don’t remove labels and rely on placeholders alone.
- Don’t hide focus styles.

## 12) Copy/Paste Prompt for Google Stitch

```text
Create a tabbed Settings window for the AutoApply dashboard that matches the existing dashboard styling exactly (no rebrand).

Design constraints:
- Use Inter, system-ui, sans-serif.
- Keep existing shell assumptions: fixed 220px left sidebar, sticky top bar, light app background (#f8f9fa), white card surfaces.
- Section container style: white background, rounded-2xl, subtle 1px border using outline-variant tone (#c7c4d7 with low opacity), padding ~24px.
- Nested panel style: rounded-xl, light border, muted background (#f3f4f5 or #edeeef family).
- Primary color token: #4648d4.
- Secondary color token: #4953bc.
- Text tokens: #191c1d (primary), #464554 (secondary).
- Error tokens: #ba1a1a, #ffdad6, #93000a.

Build top-level tabs (in order):
1) Candidate Preferences
2) Edit Resume
3) Websites
4) Advanced / File Actions

Tabbed behavior:
- Top-level tabs switch major settings domains.
- Optional secondary pills allowed within a tab (e.g., Guided / YAML / Files).
- Preserve unsaved-change warning behavior when switching tabs.
- Desktop: horizontal tabs.
- Tablet/mobile: horizontally scrollable or compact segmented tabs preserving same order.

Component styling:
- Tab pills: rounded-full, text-xs semibold, compact spacing.
- Active tab: #4648d4 background, white text, matching border.
- Inactive tab: white background, muted text, light border.
- Inputs/textareas: rounded-lg, subtle border, light neutral fill, labels above controls.
- Primary buttons: solid #4648d4, white text, semibold.
- Secondary buttons: white/light fill, subtle border.
- Alert banners: amber warning and red error variants consistent with current settings page patterns.
- YAML/code blocks: bordered rounded-xl container with monospaced editor area.

Interaction/accessibility requirements:
- Define hover, active, disabled states for all controls.
- Use :focus-visible styles for keyboard users; do not remove focus indicators.
- Focus ring must be clearly visible and high-contrast (target >= 3:1 non-text contrast).
- Text contrast should meet WCAG AA.
- Control hit areas: minimum 24x24px, target 40-44px for touch.

Output expectation:
- Produce implementation-ready UI markup/style suggestions that match existing dashboard spacing/radius/typography rhythm and avoid introducing new visual themes.
```

## References

- USWDS Typography: https://designsystem.digital.gov/components/typography/
- Focus indicators (WCAG-oriented practical guidance): https://www.sarasoueidan.com/blog/focus-indicators/
- Design system vs style guide distinction (scope framing): https://www.nngroup.com/articles/design-systems-vs-style-guides/
- Optional checklist support: https://www.uxpin.com/studio/blog/user-interface-style-guides/
