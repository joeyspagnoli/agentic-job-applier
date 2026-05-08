/**
 * @packageDocumentation
 *
 * Role-domain keyword sets used by {@link ./yaml-builders.detectSimplifyCategories}
 * to map free-form target-role text to SimplifyJobs category labels.
 *
 * @remarks
 * The keyword lists are intentionally narrow: each list should only include
 * tokens that uniquely indicate the corresponding category. Tokens shared
 * between categories (e.g., "engineer") would cause false matches.
 */

/**
 * Keywords in target role strings that indicate a hardware or electrical engineering domain.
 *
 * @remarks
 * SimplifyJobs uses `"Hardware"` as the category label. We detect it from role
 * titles because EE/hardware students phrase roles very differently from software
 * students but need the same GitHub source to return results.
 */
export const HARDWARE_ROLE_KEYWORDS = [
  "electrical",
  "hardware",
  "embedded",
  "fpga",
  "rf",
  "vlsi",
  "ece",
  "circuit",
  "pcb",
  "firmware",
] as const;

/** Keywords in target role strings that indicate a software engineering domain. */
export const SOFTWARE_ROLE_KEYWORDS = [
  "software",
  "swe",
  "frontend",
  "backend",
  "fullstack",
  "full-stack",
  "web developer",
  "mobile",
  "ios developer",
  "android",
] as const;

/** Keywords in target role strings that indicate a product management domain. */
export const PM_ROLE_KEYWORDS = [
  "product manager",
  "product management",
  "program manager",
] as const;

/** Keywords in target role strings that indicate a quantitative finance domain. */
export const QUANT_ROLE_KEYWORDS = ["quant", "quantitative"] as const;

/**
 * Generic vocabulary that carries no domain signal — entry-level cues, role-
 * suffix nouns, structural articles, semester names, and degree levels.
 *
 * @remarks
 * Used by {@link ./yaml-builders.extractDomainKeywords} to strip non-
 * discriminating words from the candidate's target roles before deriving
 * title patterns. Anything left over after this filter is treated as the
 * candidate's domain vocabulary (e.g., "fpga", "hardware", "circuit").
 */
export const TITLE_KEYWORD_STOPWORDS: ReadonlySet<string> = new Set([
  "intern",
  "internship",
  "interns",
  "interns'",
  "coop",
  "co-op",
  "new",
  "grad",
  "grads",
  "graduate",
  "junior",
  "jr",
  "entry",
  "level",
  "early",
  "career",
  "rotational",
  "engineer",
  "engineers",
  "engineering",
  "developer",
  "developers",
  "scientist",
  "scientists",
  "specialist",
  "specialists",
  "technician",
  "technicians",
  "analyst",
  "analysts",
  "associate",
  "associates",
  "assistant",
  "assistants",
  "design",
  "designer",
  "designers",
  "the",
  "a",
  "an",
  "and",
  "or",
  "of",
  "in",
  "at",
  "for",
  "to",
  "with",
  "on",
  "summer",
  "fall",
  "spring",
  "winter",
  "season",
  "year",
  "round",
  "bachelor",
  "bachelors",
  "master",
  "masters",
  "phd",
  "mba",
]);

/**
 * Maximum character distance allowed between an entry-level signal and a
 * domain keyword in a job title. Generous enough to span "Internship: UWB
 * Validation Test Management Automotive UWB" but tight enough that the two
 * tokens really do refer to the same role.
 */
export const TITLE_PATTERN_MAX_GAP = 80;
