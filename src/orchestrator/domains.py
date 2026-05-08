"""User-facing domain taxonomy + mapping to per-company industry tags.

Two-level taxonomy:

- Companies in `config/companies.yaml` carry a granular `industry` field
  (e.g. `civil_engineering`, `pharma_biotech`, `semiconductor`). The set of
  granular tags grew organically over time and is too detailed to surface
  directly in the onboarding wizard.
- Users pick from 8 broad **domains** (`civil_construction`, `software_tech`,
  ...). Each broad domain expands to a set of granular industry tags via
  `DOMAIN_TO_INDUSTRIES`.

Discovery's company-watchlist crawl filters by domain overlap. A company
whose `industry` resolves to one of the user's domains is crawled; one
whose `industry` is missing is also crawled (catch-all for unmaintained
entries — see `company_matches_domains`).

Search-term-driven crawls (LinkedIn, JobSpy) are *not* filtered here —
they are already domain-relevant by construction.
"""

from __future__ import annotations

from typing import Final

# Broad user-facing domain identifiers. Stable; written to
# `candidate_profile.yaml`'s `profile.domains` list. Keep in lockstep
# with the multi-select chips rendered by the onboarding wizard.
DOMAIN_SOFTWARE_TECH: Final[str] = "software_tech"
DOMAIN_CIVIL_CONSTRUCTION: Final[str] = "civil_construction"
DOMAIN_HARDWARE_SEMIS: Final[str] = "hardware_semis"
DOMAIN_HEALTHCARE: Final[str] = "healthcare"
DOMAIN_LIFE_SCIENCES: Final[str] = "life_sciences"
DOMAIN_FINANCE: Final[str] = "finance"
DOMAIN_CONSUMER_RETAIL: Final[str] = "consumer_retail"
DOMAIN_ENERGY_INDUSTRIAL: Final[str] = "energy_industrial"

ALL_DOMAINS: Final[frozenset[str]] = frozenset(
    {
        DOMAIN_SOFTWARE_TECH,
        DOMAIN_CIVIL_CONSTRUCTION,
        DOMAIN_HARDWARE_SEMIS,
        DOMAIN_HEALTHCARE,
        DOMAIN_LIFE_SCIENCES,
        DOMAIN_FINANCE,
        DOMAIN_CONSUMER_RETAIL,
        DOMAIN_ENERGY_INDUSTRIAL,
    }
)

# Each user-facing domain expands to a set of granular `industry` values
# from `config/companies.yaml`. Cross-domain industries (e.g.
# `manufacturing_automotive` includes both heavy industrial and
# civil-adjacent firms) are intentionally listed in multiple domains.
DOMAIN_TO_INDUSTRIES: Final[dict[str, frozenset[str]]] = {
    DOMAIN_SOFTWARE_TECH: frozenset({"software_tech", "telecom"}),
    DOMAIN_CIVIL_CONSTRUCTION: frozenset(
        {"civil_engineering", "real_estate", "government_contractors"}
    ),
    DOMAIN_HARDWARE_SEMIS: frozenset(
        {"semiconductor", "manufacturing_automotive", "telecom"}
    ),
    DOMAIN_HEALTHCARE: frozenset({"healthcare", "medical_devices"}),
    DOMAIN_LIFE_SCIENCES: frozenset(
        {"life_sciences", "pharma_biotech", "medical_devices"}
    ),
    DOMAIN_FINANCE: frozenset({"finance_banking", "financial", "insurance"}),
    DOMAIN_CONSUMER_RETAIL: frozenset(
        {
            "consumer_goods",
            "retail",
            "retail_hq",
            "media",
            "logistics",
            "consulting",
            "higher_ed",
        }
    ),
    DOMAIN_ENERGY_INDUSTRIAL: frozenset(
        {"energy", "chemical", "manufacturing_automotive"}
    ),
}

# Keyword fragments matched against `target_roles` strings to infer a
# user's domains during onboarding. Order does not matter; the search is
# unanchored substring (case-insensitive). Each fragment maps to one
# domain. Fragments are conservative — when a role string contains
# none of these, the inferred set is empty and the wizard prompts the
# user to pick explicitly.
_INFERENCE_KEYWORDS: Final[dict[str, str]] = {
    "civil engineer": DOMAIN_CIVIL_CONSTRUCTION,
    "structural": DOMAIN_CIVIL_CONSTRUCTION,
    "construction": DOMAIN_CIVIL_CONSTRUCTION,
    "transportation engineer": DOMAIN_CIVIL_CONSTRUCTION,
    "geotechnical": DOMAIN_CIVIL_CONSTRUCTION,
    "land development": DOMAIN_CIVIL_CONSTRUCTION,
    "site engineer": DOMAIN_CIVIL_CONSTRUCTION,
    "bridge": DOMAIN_CIVIL_CONSTRUCTION,
    "water resources": DOMAIN_CIVIL_CONSTRUCTION,
    "software": DOMAIN_SOFTWARE_TECH,
    "developer": DOMAIN_SOFTWARE_TECH,
    "swe": DOMAIN_SOFTWARE_TECH,
    "backend": DOMAIN_SOFTWARE_TECH,
    "frontend": DOMAIN_SOFTWARE_TECH,
    "full-stack": DOMAIN_SOFTWARE_TECH,
    "fullstack": DOMAIN_SOFTWARE_TECH,
    "ml engineer": DOMAIN_SOFTWARE_TECH,
    "machine learning": DOMAIN_SOFTWARE_TECH,
    "data engineer": DOMAIN_SOFTWARE_TECH,
    "data scientist": DOMAIN_SOFTWARE_TECH,
    "devops": DOMAIN_SOFTWARE_TECH,
    "site reliability": DOMAIN_SOFTWARE_TECH,
    "platform engineer": DOMAIN_SOFTWARE_TECH,
    "hardware": DOMAIN_HARDWARE_SEMIS,
    "semiconductor": DOMAIN_HARDWARE_SEMIS,
    "chip": DOMAIN_HARDWARE_SEMIS,
    "asic": DOMAIN_HARDWARE_SEMIS,
    "fpga": DOMAIN_HARDWARE_SEMIS,
    "rf engineer": DOMAIN_HARDWARE_SEMIS,
    "robotics": DOMAIN_HARDWARE_SEMIS,
    "embedded": DOMAIN_HARDWARE_SEMIS,
    "electrical engineer": DOMAIN_HARDWARE_SEMIS,
    "nurse": DOMAIN_HEALTHCARE,
    "rn ": DOMAIN_HEALTHCARE,
    "physician": DOMAIN_HEALTHCARE,
    "doctor": DOMAIN_HEALTHCARE,
    "clinical": DOMAIN_HEALTHCARE,
    "patient": DOMAIN_HEALTHCARE,
    "icu": DOMAIN_HEALTHCARE,
    "pharmacy": DOMAIN_HEALTHCARE,
    "biotech": DOMAIN_LIFE_SCIENCES,
    "pharma": DOMAIN_LIFE_SCIENCES,
    "drug discovery": DOMAIN_LIFE_SCIENCES,
    "bioengineer": DOMAIN_LIFE_SCIENCES,
    "molecular": DOMAIN_LIFE_SCIENCES,
    "genomics": DOMAIN_LIFE_SCIENCES,
    "finance": DOMAIN_FINANCE,
    "trader": DOMAIN_FINANCE,
    "trading": DOMAIN_FINANCE,
    "quantitative": DOMAIN_FINANCE,
    "quant": DOMAIN_FINANCE,
    "investment banking": DOMAIN_FINANCE,
    "actuarial": DOMAIN_FINANCE,
    "insurance": DOMAIN_FINANCE,
    "retail": DOMAIN_CONSUMER_RETAIL,
    "marketing": DOMAIN_CONSUMER_RETAIL,
    "consumer goods": DOMAIN_CONSUMER_RETAIL,
    "supply chain": DOMAIN_CONSUMER_RETAIL,
    "logistics": DOMAIN_CONSUMER_RETAIL,
    "energy": DOMAIN_ENERGY_INDUSTRIAL,
    "oil and gas": DOMAIN_ENERGY_INDUSTRIAL,
    "utilities": DOMAIN_ENERGY_INDUSTRIAL,
    "chemical engineer": DOMAIN_ENERGY_INDUSTRIAL,
    "manufacturing": DOMAIN_ENERGY_INDUSTRIAL,
    "process engineer": DOMAIN_ENERGY_INDUSTRIAL,
}


def infer_domains_from_target_roles(target_roles: list[str]) -> set[str]:
    """Return the broad domains implied by a list of target-role strings.

    Purpose:
        Default-populate the `profile.domains` field during onboarding so a
        user who already typed e.g. "Civil Engineering Intern" does not also
        have to tick a checkbox saying "civil engineering."
    Args:
        target_roles: Free-text role strings the user typed in step 2 of the
            onboarding wizard, e.g. ``["Civil Engineering Intern",
            "Structural Engineering Intern"]``.
    Output:
        Returns a set of broad domain identifiers from `ALL_DOMAINS` that
        match any keyword in any role string. May be empty.
    """

    matched: set[str] = set()
    for role in target_roles:
        haystack = role.casefold()
        for keyword, domain in _INFERENCE_KEYWORDS.items():
            if keyword in haystack:
                matched.add(domain)
    return matched


def industries_for_domains(user_domains: set[str]) -> frozenset[str]:
    """Expand a user's broad domain selection to its granular industries.

    Purpose:
        Translate the domain field stored on the candidate profile into the
        per-company `industry` values the discovery filter actually
        compares against.
    Args:
        user_domains: Broad domain identifiers selected by the user.
    Output:
        Returns the union of granular industry tags covered by the
        selection. Unknown domain identifiers are silently ignored.
    """

    expanded: set[str] = set()
    for domain in user_domains:
        expanded.update(DOMAIN_TO_INDUSTRIES.get(domain, frozenset()))
    return frozenset(expanded)


def resolve_user_domains(candidate_profile_config: dict[str, object]) -> set[str]:
    """Return the user's domain selection, falling back to inference.

    Purpose:
        Centralize the candidate-profile lookup used by discovery so the
        explicit `profile.domains` list (set during onboarding) takes
        precedence over the keyword inference, while a profile without a
        domains field still gets a sensible default.
    Args:
        candidate_profile_config: Parsed `candidate_profile.yaml` mapping.
            Schema is permissive: this helper tolerates missing `profile`
            sections and missing `target_roles`/`domains` fields.
    Output:
        Returns a set of broad domain identifiers. Empty when no domains
        are configured and no target_roles are present — discovery treats
        the empty set as "no filter."
    """

    profile = candidate_profile_config.get("profile") or {}
    if not isinstance(profile, dict):
        return set()

    explicit = profile.get("domains")
    if isinstance(explicit, list) and explicit:
        return {str(d) for d in explicit if isinstance(d, str)}

    target_roles_raw = profile.get("target_roles") or []
    if not isinstance(target_roles_raw, list):
        return set()
    target_roles = [str(role) for role in target_roles_raw if isinstance(role, str)]
    return infer_domains_from_target_roles(target_roles)


def filter_companies_by_domain(
    companies_section: dict[str, object],
    user_domains: set[str],
) -> dict[str, object]:
    """Drop company entries whose `industry` does not match any user domain.

    Purpose:
        Apply the per-section domain gate to the watchlist before discovery
        spawns fetcher tasks, keeping search-term-driven crawl families
        (LinkedIn, JobSpy, GitHub repos) untouched.
    Args:
        companies_section: One section of `companies.yaml` (e.g. the
            `workday_companies` mapping). Each value is a per-company
            config dict that may carry an `industry` field.
        user_domains: Broad domains the user picked. Empty = no filter.
    Output:
        Returns a new mapping containing only the entries that pass
        `company_matches_domains`. Untagged entries always pass.
    """

    if not user_domains:
        return dict(companies_section)

    filtered: dict[str, object] = {}
    for name, cfg in companies_section.items():
        industry: str | None = None
        if isinstance(cfg, dict):
            raw = cfg.get("industry")
            if isinstance(raw, str):
                industry = raw
        if company_matches_domains(industry, user_domains):
            filtered[name] = cfg
    return filtered


# Sections of `companies.yaml` that are watchlist-style (one entry per
# company, each crawled wholesale). These are the ones the domain filter
# applies to. Search-term-driven sections like `linkedin`, `job_boards`,
# `github_repos`, and `watched_pages` are intentionally excluded — their
# results are already domain-relevant by construction.
WATCHLIST_SECTIONS: Final[tuple[str, ...]] = (
    "greenhouse_companies",
    "workday_companies",
    "icims_companies",
    "taleo_companies",
    "lever_companies",
    "ashby_companies",
)


def apply_domain_filter_to_config(
    companies_config: dict[str, object],
    user_domains: set[str],
) -> dict[str, object]:
    """Return a new `companies_config` with watchlist sections domain-filtered.

    Purpose:
        Single entry point used by the discovery cycle to scope the
        company watchlist before fetcher tasks are dispatched. Non-watchlist
        sections pass through unchanged.
    Args:
        companies_config: Parsed `companies.yaml`.
        user_domains: Broad domains the user picked. Empty = no filter
            (full watchlist crawled).
    Output:
        Returns a new config dict structurally identical to the input but
        with each watchlist section replaced by its domain-filtered subset.
    """

    if not user_domains:
        return companies_config

    filtered_config: dict[str, object] = dict(companies_config)
    for section in WATCHLIST_SECTIONS:
        section_value = companies_config.get(section)
        if isinstance(section_value, dict):
            filtered_config[section] = filter_companies_by_domain(
                section_value, user_domains
            )
    return filtered_config


def company_matches_domains(
    company_industry: str | None,
    user_domains: set[str],
) -> bool:
    """Return True when a company should be crawled for the user's domains.

    Purpose:
        Centralize the watchlist crawl gate so discovery code does not need
        to know about the granular industry taxonomy.
    Args:
        company_industry: Granular tag from `config/companies.yaml`. May be
            None or empty when the entry has not been classified yet.
        user_domains: Broad domains the user picked at onboarding. May be
            empty (e.g. a fresh profile where inference produced nothing);
            the empty set is treated as "no preference" and matches every
            company.
    Output:
        Returns True when the company should be crawled, False otherwise.
        Untagged companies (`company_industry` falsy) always match — the
        deliberate catch-all that prevents unmaintained entries from
        disappearing from every user's view.
    """

    if not user_domains:
        return True
    if not company_industry:
        return True
    return company_industry in industries_for_domains(user_domains)
