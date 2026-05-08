"""Validate the user-facing domain taxonomy and the discovery-filter helpers.

Purpose:
    Lock the contract between the onboarding wizard, the candidate profile
    `profile.domains` field, the granular per-company `industry` tags in
    `config/companies.yaml`, and the discovery watchlist filter. The
    inference helper drives onboarding defaults; the matcher drives crawl
    decisions.
"""

from __future__ import annotations

import pytest

from src.orchestrator.domains import ALL_DOMAINS
from src.orchestrator.domains import DOMAIN_CIVIL_CONSTRUCTION
from src.orchestrator.domains import DOMAIN_FINANCE
from src.orchestrator.domains import DOMAIN_HARDWARE_SEMIS
from src.orchestrator.domains import DOMAIN_HEALTHCARE
from src.orchestrator.domains import DOMAIN_LIFE_SCIENCES
from src.orchestrator.domains import DOMAIN_SOFTWARE_TECH
from src.orchestrator.domains import DOMAIN_TO_INDUSTRIES
from src.orchestrator.domains import apply_domain_filter_to_config
from src.orchestrator.domains import company_matches_domains
from src.orchestrator.domains import filter_companies_by_domain
from src.orchestrator.domains import filter_list_section_by_domain
from src.orchestrator.domains import industries_for_domains
from src.orchestrator.domains import infer_domains_from_target_roles
from src.orchestrator.domains import resolve_user_domains


class TestInferDomainsFromTargetRoles:
    """Onboarding inference: target_roles strings → broad domain set."""

    def test_civil_engineering_target_roles_infer_civil_construction(self) -> None:
        roles = ["Civil Engineering Intern", "Structural Engineering Intern"]

        inferred = infer_domains_from_target_roles(roles)

        assert inferred == {DOMAIN_CIVIL_CONSTRUCTION}

    def test_software_target_roles_infer_software_tech(self) -> None:
        roles = ["Software Engineer Intern", "ML Engineer", "Backend Developer"]

        inferred = infer_domains_from_target_roles(roles)

        assert inferred == {DOMAIN_SOFTWARE_TECH}

    def test_nurse_roles_infer_healthcare(self) -> None:
        roles = ["Registered Nurse", "ICU Nurse", "Cardiac Nurse"]

        inferred = infer_domains_from_target_roles(roles)

        assert inferred == {DOMAIN_HEALTHCARE}

    def test_pharma_roles_infer_life_sciences(self) -> None:
        roles = ["Drug Discovery Scientist", "Biotech Research Intern"]

        inferred = infer_domains_from_target_roles(roles)

        assert inferred == {DOMAIN_LIFE_SCIENCES}

    def test_finance_roles_infer_finance(self) -> None:
        roles = ["Quantitative Trading Intern", "Investment Banking Analyst"]

        inferred = infer_domains_from_target_roles(roles)

        assert inferred == {DOMAIN_FINANCE}

    def test_hardware_roles_infer_hardware_semis(self) -> None:
        roles = ["Semiconductor Engineer", "FPGA Designer", "Embedded Software Intern"]

        inferred = infer_domains_from_target_roles(roles)

        # "Embedded Software" matches both software_tech (via "software")
        # and hardware_semis (via "embedded"). Both expectations are valid
        # — multi-domain inference is by design.
        assert DOMAIN_HARDWARE_SEMIS in inferred

    def test_mixed_roles_infer_multiple_domains(self) -> None:
        roles = ["Civil Engineering Intern", "Software Engineer Intern"]

        inferred = infer_domains_from_target_roles(roles)

        assert inferred == {DOMAIN_CIVIL_CONSTRUCTION, DOMAIN_SOFTWARE_TECH}

    def test_empty_roles_infer_empty_set(self) -> None:
        inferred = infer_domains_from_target_roles([])

        assert inferred == set()

    def test_unknown_role_infers_empty_set(self) -> None:
        roles = ["Spaceship Captain", "Wizard"]

        inferred = infer_domains_from_target_roles(roles)

        assert inferred == set()

    def test_inference_is_case_insensitive(self) -> None:
        lower = infer_domains_from_target_roles(["civil engineering intern"])
        upper = infer_domains_from_target_roles(["CIVIL ENGINEERING INTERN"])
        mixed = infer_domains_from_target_roles(["Civil Engineering Intern"])

        assert lower == upper == mixed == {DOMAIN_CIVIL_CONSTRUCTION}


class TestIndustriesForDomains:
    """Domain-to-industry expansion used by the discovery filter."""

    def test_civil_construction_expands_to_civil_industries(self) -> None:
        expanded = industries_for_domains({DOMAIN_CIVIL_CONSTRUCTION})

        assert "civil_engineering" in expanded
        assert "real_estate" in expanded
        assert "government_contractors" in expanded

    def test_multiple_domains_unioned(self) -> None:
        expanded = industries_for_domains(
            {DOMAIN_HEALTHCARE, DOMAIN_LIFE_SCIENCES}
        )

        assert "healthcare" in expanded
        assert "medical_devices" in expanded
        assert "pharma_biotech" in expanded
        assert "life_sciences" in expanded

    def test_unknown_domain_silently_ignored(self) -> None:
        expanded = industries_for_domains({"completely_made_up_domain"})

        assert expanded == frozenset()

    def test_empty_selection_empty_expansion(self) -> None:
        expanded = industries_for_domains(set())

        assert expanded == frozenset()


class TestCompanyMatchesDomains:
    """Watchlist crawl gate: does this company belong in this user's crawl?"""

    def test_civil_company_matches_civil_user(self) -> None:
        matched = company_matches_domains(
            company_industry="civil_engineering",
            user_domains={DOMAIN_CIVIL_CONSTRUCTION},
        )

        assert matched is True

    def test_healthcare_company_skipped_for_civil_user(self) -> None:
        matched = company_matches_domains(
            company_industry="healthcare",
            user_domains={DOMAIN_CIVIL_CONSTRUCTION},
        )

        assert matched is False

    def test_untagged_company_always_matches(self) -> None:
        matched = company_matches_domains(
            company_industry=None,
            user_domains={DOMAIN_CIVIL_CONSTRUCTION},
        )

        assert matched is True

    def test_empty_string_industry_treated_as_untagged(self) -> None:
        matched = company_matches_domains(
            company_industry="",
            user_domains={DOMAIN_CIVIL_CONSTRUCTION},
        )

        assert matched is True

    def test_empty_user_domains_matches_everything(self) -> None:
        matched = company_matches_domains(
            company_industry="healthcare",
            user_domains=set(),
        )

        assert matched is True

    def test_cross_domain_industry_matches_either_user_domain(self) -> None:
        # `manufacturing_automotive` lives in both hardware_semis and
        # energy_industrial — verify either user-domain selection picks
        # it up.
        matched_hardware = company_matches_domains(
            company_industry="manufacturing_automotive",
            user_domains={DOMAIN_HARDWARE_SEMIS},
        )
        matched_energy = company_matches_domains(
            company_industry="manufacturing_automotive",
            user_domains={"energy_industrial"},
        )

        assert matched_hardware is True
        assert matched_energy is True


class TestResolveUserDomains:
    """Reading the candidate profile to derive the user's domain selection."""

    def test_explicit_domains_take_precedence_over_inference(self) -> None:
        config: dict[str, object] = {
            "profile": {
                "domains": ["software_tech"],
                "target_roles": ["Civil Engineering Intern"],
            }
        }

        domains = resolve_user_domains(config)

        assert domains == {"software_tech"}

    def test_falls_back_to_inference_when_domains_missing(self) -> None:
        config: dict[str, object] = {
            "profile": {"target_roles": ["Civil Engineering Intern"]}
        }

        domains = resolve_user_domains(config)

        assert domains == {DOMAIN_CIVIL_CONSTRUCTION}

    def test_empty_domains_list_falls_back_to_inference(self) -> None:
        config: dict[str, object] = {
            "profile": {
                "domains": [],
                "target_roles": ["ML Engineer"],
            }
        }

        domains = resolve_user_domains(config)

        assert domains == {DOMAIN_SOFTWARE_TECH}

    def test_missing_profile_returns_empty(self) -> None:
        domains = resolve_user_domains({})

        assert domains == set()

    def test_non_dict_profile_returns_empty(self) -> None:
        config: dict[str, object] = {"profile": "not a dict"}

        domains = resolve_user_domains(config)

        assert domains == set()


class TestFilterCompaniesByDomain:
    """Section-level filtering used during discovery setup."""

    def test_keeps_matching_industry_drops_non_matching(self) -> None:
        section: dict[str, object] = {
            "AECOM": {"workday_url": "x", "industry": "civil_engineering"},
            "Pfizer": {"workday_url": "y", "industry": "pharma_biotech"},
        }

        filtered = filter_companies_by_domain(section, {DOMAIN_CIVIL_CONSTRUCTION})

        assert "AECOM" in filtered
        assert "Pfizer" not in filtered

    def test_untagged_company_kept(self) -> None:
        section: dict[str, object] = {
            "Stripe": {"greenhouse_id": "stripe"},
            "Pfizer": {"workday_url": "y", "industry": "pharma_biotech"},
        }

        filtered = filter_companies_by_domain(section, {DOMAIN_CIVIL_CONSTRUCTION})

        assert "Stripe" in filtered
        assert "Pfizer" not in filtered

    def test_empty_user_domains_returns_full_section(self) -> None:
        section: dict[str, object] = {
            "AECOM": {"industry": "civil_engineering"},
            "Pfizer": {"industry": "pharma_biotech"},
        }

        filtered = filter_companies_by_domain(section, set())

        assert filtered == section

    def test_filtering_does_not_mutate_input(self) -> None:
        section: dict[str, object] = {
            "AECOM": {"industry": "civil_engineering"},
            "Pfizer": {"industry": "pharma_biotech"},
        }
        snapshot = dict(section)

        filter_companies_by_domain(section, {DOMAIN_CIVIL_CONSTRUCTION})

        assert section == snapshot


class TestFilterListSectionByDomain:
    """Per-entry filtering for list-shaped sections like `github_repos`."""

    def test_entry_with_matching_domain_kept(self) -> None:
        entries: list[object] = [
            {"owner": "civeng", "repo": "x", "domains": ["civil_construction"]},
            {"owner": "tech", "repo": "y", "domains": ["software_tech"]},
        ]

        kept = filter_list_section_by_domain(entries, {DOMAIN_CIVIL_CONSTRUCTION})

        assert len(kept) == 1
        assert kept[0] == entries[0]

    def test_entry_without_domains_kept_as_catchall(self) -> None:
        entries: list[object] = [
            {"owner": "neutral", "repo": "z"},
            {"owner": "tech", "repo": "y", "domains": ["software_tech"]},
        ]

        kept = filter_list_section_by_domain(entries, {DOMAIN_CIVIL_CONSTRUCTION})

        # only the untagged entry survives
        assert len(kept) == 1
        assert kept[0] == entries[0]

    def test_empty_user_domains_returns_all(self) -> None:
        entries: list[object] = [
            {"owner": "tech", "repo": "y", "domains": ["software_tech"]},
        ]

        kept = filter_list_section_by_domain(entries, set())

        assert kept == entries

    def test_multi_domain_entry_matches_any_user_domain(self) -> None:
        entries: list[object] = [
            {
                "owner": "mixed",
                "repo": "x",
                "domains": ["software_tech", DOMAIN_CIVIL_CONSTRUCTION],
            },
        ]

        kept_civil = filter_list_section_by_domain(
            entries, {DOMAIN_CIVIL_CONSTRUCTION}
        )
        kept_tech = filter_list_section_by_domain(entries, {DOMAIN_SOFTWARE_TECH})
        kept_other = filter_list_section_by_domain(entries, {DOMAIN_HEALTHCARE})

        assert kept_civil == entries
        assert kept_tech == entries
        assert kept_other == []


class TestApplyDomainFilterToConfig:
    """Top-level apply that handles every watchlist section at once."""

    def test_filters_each_watchlist_section(self) -> None:
        config: dict[str, object] = {
            "greenhouse_companies": {
                "Stripe": {"greenhouse_id": "stripe"},
            },
            "workday_companies": {
                "AECOM": {"industry": "civil_engineering"},
                "Pfizer": {"industry": "pharma_biotech"},
            },
            "taleo_companies": {
                "Merck": {"industry": "pharma_biotech"},
            },
            "linkedin": {"enabled": True, "search_terms": ["intern"]},
            "github_repos": [
                {"owner": "tech", "repo": "x", "domains": ["software_tech"]},
                {"owner": "neutral", "repo": "y"},
            ],
        }

        filtered = apply_domain_filter_to_config(
            config, {DOMAIN_CIVIL_CONSTRUCTION}
        )

        greenhouse_section = filtered["greenhouse_companies"]
        workday_section = filtered["workday_companies"]
        github_section = filtered["github_repos"]
        assert isinstance(greenhouse_section, dict)
        assert isinstance(workday_section, dict)
        assert isinstance(github_section, list)
        # tech-tagged repo dropped, neutral one preserved
        assert len(github_section) == 1
        first_entry = github_section[0]
        assert isinstance(first_entry, dict)
        assert first_entry["owner"] == "neutral"
        # untagged greenhouse entry preserved
        assert "Stripe" in greenhouse_section
        # civil-tagged kept, pharma dropped
        assert "AECOM" in workday_section
        assert "Pfizer" not in workday_section
        # entire pharma-only Taleo section becomes empty
        assert filtered["taleo_companies"] == {}
        # search-term-driven section untouched
        assert filtered["linkedin"] == config["linkedin"]

    def test_empty_user_domains_returns_input_unchanged(self) -> None:
        config: dict[str, object] = {
            "workday_companies": {
                "Pfizer": {"industry": "pharma_biotech"},
            },
        }

        filtered = apply_domain_filter_to_config(config, set())

        assert filtered is config


class TestTaxonomyIntegrity:
    """Static checks that guard against silent regressions of the taxonomy."""

    def test_all_domains_appear_in_mapping(self) -> None:
        assert ALL_DOMAINS == frozenset(DOMAIN_TO_INDUSTRIES.keys())

    @pytest.mark.parametrize(
        "domain, expected_industry",
        [
            (DOMAIN_SOFTWARE_TECH, "software_tech"),
            (DOMAIN_CIVIL_CONSTRUCTION, "civil_engineering"),
            (DOMAIN_HARDWARE_SEMIS, "semiconductor"),
            (DOMAIN_HEALTHCARE, "healthcare"),
            (DOMAIN_LIFE_SCIENCES, "life_sciences"),
            (DOMAIN_FINANCE, "finance_banking"),
        ],
    )
    def test_each_domain_covers_its_anchor_industry(
        self, domain: str, expected_industry: str
    ) -> None:
        assert expected_industry in DOMAIN_TO_INDUSTRIES[domain]
