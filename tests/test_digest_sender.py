"""Behavior tests for the email digest sender and its routing helpers.

Covers the correctness-critical paths that were previously untested: the
inclusive-by-default category filter, the business-category routing that keeps
non-CS roles out of the default digest, deduplication, and the HTML-escaping
applied to scraped (untrusted) company/title/URL text in outgoing email.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from src.digest import sender
from src.orchestrator.insert_pipeline import (
    resolve_digest_category,
    stamp_digest_category,
)


# ---------------------------------------------------------------------------
# Digest-category routing (the business-leak fix)
# ---------------------------------------------------------------------------


def test_resolve_digest_category_prefers_explicit_key() -> None:
    assert resolve_digest_category({"digest_category": "Business"}) == "Business"
    # Explicit key wins even when an industry is also present.
    assert (
        resolve_digest_category({"digest_category": "Business", "industry": "software_tech"})
        == "Business"
    )


def test_resolve_digest_category_derives_business_from_industry() -> None:
    for industry in ("finance_banking", "finance", "real_estate", "logistics"):
        assert resolve_digest_category({"industry": industry}) == "Business"


def test_resolve_digest_category_cs_sources_are_uncategorized() -> None:
    assert resolve_digest_category({"industry": "software_tech"}) is None
    assert resolve_digest_category({"industry": "semiconductor"}) is None
    assert resolve_digest_category({}) is None
    assert resolve_digest_category(None) is None


def test_stamp_digest_category_tags_untagged_jobs() -> None:
    jobs = [SimpleNamespace(raw_data={}), SimpleNamespace(raw_data={})]
    stamp_digest_category(jobs, "Business")
    assert all(j.raw_data["category"] == "Business" for j in jobs)


def test_stamp_digest_category_preserves_existing_category() -> None:
    job = SimpleNamespace(raw_data={"category": "Software"})
    stamp_digest_category([job], "Business")
    assert job.raw_data["category"] == "Software"


def test_stamp_digest_category_none_is_noop() -> None:
    job = SimpleNamespace(raw_data={})
    stamp_digest_category([job], None)
    assert "category" not in job.raw_data


# ---------------------------------------------------------------------------
# Category filter — inclusive-by-default (the critical June 29 fix)
# ---------------------------------------------------------------------------


def test_category_filter_inclusive_when_job_has_no_category() -> None:
    # ATS-sourced jobs carry no category; they must still reach a subscriber
    # who set field preferences — otherwise ~90% of postings vanish.
    assert sender._passes_category_filter(None, {"Software"}) is True
    assert sender._passes_category_filter(json.dumps({}), {"Software"}) is True


def test_category_filter_excludes_business_from_cs_subscriber() -> None:
    business = json.dumps({"category": "Business"})
    assert sender._passes_category_filter(business, {"Software", "AI/ML/Data"}) is False


def test_category_filter_allows_matching_category() -> None:
    software = json.dumps({"category": "Software"})
    assert sender._passes_category_filter(software, {"Software"}) is True


def test_category_filter_no_field_prefs_passes_everything() -> None:
    business = json.dumps({"category": "Business"})
    assert sender._passes_category_filter(business, set()) is True


# ---------------------------------------------------------------------------
# Role-level filter
# ---------------------------------------------------------------------------


def test_role_level_intern_matches_only_intern_titles() -> None:
    assert sender._passes_role_level_filter("Software Engineering Intern", "intern") is True
    assert sender._passes_role_level_filter("Senior Data Analyst", "intern") is False


def test_role_level_both_passes_everything() -> None:
    assert sender._passes_role_level_filter("Senior Data Analyst", "both") is True


# ---------------------------------------------------------------------------
# Dedup + HTML escaping (untrusted scraped text in outgoing email)
# ---------------------------------------------------------------------------


def test_dedup_keeps_one_per_company_title_preferring_longest_description() -> None:
    jobs = [
        {"company": "Acme", "title": "SWE Intern", "description": "short"},
        {"company": "acme", "title": "swe intern", "description": "a much longer description"},
    ]
    out = sender._dedup_by_company_title(jobs)
    assert len(out) == 1
    assert out[0]["description"] == "a much longer description"


def test_render_job_item_escapes_scraped_company_and_title() -> None:
    job = {
        "company": "Smith & <b>Co</b>",
        "title": "Intern <script>alert(1)</script>",
        "source_url": "https://jobs.example/1",
        "fetched_at": "2026-07-01T12:00:00",
    }
    html = sender._render_job_item(job, "tok", base_url="https://d")
    assert "&amp;" in html
    assert "&lt;b&gt;" in html
    assert "<script>" not in html


def test_render_job_item_rejects_non_http_apply_url() -> None:
    job = {
        "company": "X",
        "title": "Intern",
        "source_url": "javascript:alert(1)",
        "fetched_at": "2026-07-01",
    }
    html = sender._render_job_item(job, "tok")
    assert "javascript:alert" not in html
