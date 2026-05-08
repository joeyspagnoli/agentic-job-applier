/**
 * @packageDocumentation
 *
 * Derive `hard_filters.require_title_patterns` regex set from the
 * candidate's free-form target-role text.
 *
 * @remarks
 * Lives in its own module because the title-pattern derivation is the
 * single most rule-heavy piece of the wizard's pure-helper layer:
 * stopword filtering, intern/co-op/new-grad detection, and the gap-distance
 * pairing of domain keywords with entry-level signals all live here. The
 * resulting regex array is then dropped verbatim into `filters.yaml` by
 * {@link ./yaml-builders.buildFiltersYaml}.
 */

import { TITLE_KEYWORD_STOPWORDS, TITLE_PATTERN_MAX_GAP } from "./role-keywords";

/**
 * Tokenize candidate target roles and return discriminating domain keywords.
 *
 * @remarks
 * Splits on whitespace and common punctuation, lower-cases each token, and
 * drops tokens that appear in the internal stopword set. The remaining
 * tokens (e.g., "fpga", "embedded", "circuit") form the domain vocabulary
 * used to require role-relevance in the title filter.
 *
 * @param targetRolesText - Raw multi-line target roles text from the wizard.
 * @returns De-duplicated lower-case domain keywords; empty when the user
 *   only listed generic role nouns.
 */
export function extractDomainKeywords(targetRolesText: string): string[] {
  const seen = new Set<string>();
  const ordered: string[] = [];
  for (const raw of targetRolesText.toLowerCase().split(/[\s/\-,()]+/)) {
    const cleaned = raw.replace(/[^a-z0-9]/g, "");
    if (cleaned.length < 3) continue;
    if (TITLE_KEYWORD_STOPWORDS.has(cleaned)) continue;
    if (seen.has(cleaned)) continue;
    seen.add(cleaned);
    ordered.push(cleaned);
  }
  return ordered;
}

/**
 * Derive `hard_filters.require_title_patterns` from the candidate's target roles.
 *
 * @remarks
 * The pre-gate filter has to do role-relevance triage on its own: discovery
 * fetches every "Intern" title across 90+ ATS tenants, and the LLM gate
 * worker may not be running yet (no API key on first install). A naive
 * `\bintern\b` requirement lets through Nursing, Pharmacy, IT-Billing,
 * Marketing, and Accounting interns — none of which an electrical-
 * engineering candidate cares about.
 *
 * To gate properly we require **both** an entry-level signal AND a domain
 * keyword extracted from the candidate's own target roles, in either
 * order, within {@link TITLE_PATTERN_MAX_GAP} characters. The output is
 * two regex patterns (one per ordering) which the JobFilter ORs together —
 * net effect: titles must contain a domain keyword AND an intern/co-op/
 * new-grad term. "Nursing Intern" is rejected; "Electrical Engineering
 * Intern" passes; "Hardware Engineer Intern" passes; "Internship: UWB
 * Validation" with "uwb" or "validation" in target_roles passes.
 *
 * Fallback: when no entry-level signal is detected (candidate targeting
 * senior roles), no patterns are emitted and all titles pass through. When
 * entry-level signals exist but no domain keywords could be extracted
 * (target_roles say only "Intern"), we fall back to the broad intern-only
 * pattern — better than rejecting everything.
 *
 * @param targetRolesText - Raw multi-line target roles text from the wizard.
 * @returns Regex patterns to populate `hard_filters.require_title_patterns`.
 */
export function deriveRequireTitlePatterns(targetRolesText: string): string[] {
  const lowered = targetRolesText.toLowerCase();
  const internAlts: string[] = [];
  if (/\bintern(ship)?\b/.test(lowered)) internAlts.push("intern(ship)?");
  if (/\bco-?op\b/.test(lowered)) internAlts.push("co-?op");
  if (/\bnew\s+grad(uate)?\b/.test(lowered)) internAlts.push("new\\s+grad(uate)?");
  if (/\bearly\s+career\b/.test(lowered)) internAlts.push("early\\s+career");
  if (/\b(junior|jr\.?|entry[\s-]level)\b/.test(lowered)) {
    internAlts.push("junior", "jr\\.?", "entry[\\s-]level");
  }

  if (internAlts.length === 0) return [];

  const internPart = `\\b(?:${internAlts.join("|")})\\b`;
  const domainKeywords = extractDomainKeywords(targetRolesText);

  if (domainKeywords.length === 0) {
    // No discriminating domain words — keep the broad intern-only filter so
    // the candidate at least gets entry-level results.
    return [`(?i)${internPart}`];
  }

  const domainPart = `\\b(?:${domainKeywords.join("|")})\\b`;
  return [
    `(?i)${domainPart}.{0,${TITLE_PATTERN_MAX_GAP}}${internPart}`,
    `(?i)${internPart}.{0,${TITLE_PATTERN_MAX_GAP}}${domainPart}`,
  ];
}
