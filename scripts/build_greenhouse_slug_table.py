#!/usr/bin/env python3
"""
Build the Greenhouse slug lookup table at dashboard/src/data/greenhouse_known_slugs.json.

Fetches company names from the SimplifyJobs Summer Internships and New-Grad
listings, deduplicates them, then probes each name against the Greenhouse
boards API using up to four slug patterns. The
result JSON contains:
  - string value: the verified slug for that company
  - null value:   confirmed absent from Greenhouse (uses a different ATS)
  - missing key:  not yet probed (first run may not cover every long-tail name)

The script is idempotent: companies already in the JSON are skipped so
re-running only probes new names.
"""

import json
import re
import sys
import time
from pathlib import Path
from typing import Optional

import httpx  # httpx==0.27.2


OUTPUT_PATH = (
    Path(__file__).parent.parent / "dashboard" / "src" / "data" / "greenhouse_known_slugs.json"
)

SIMPLIFY_INTERNSHIPS_URL = (
    "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships"
    "/dev/.github/scripts/listings.json"
)
SIMPLIFY_NEWGRAD_URL = (
    "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions"
    "/dev/.github/scripts/listings.json"
)

# Polite delay between Greenhouse probe requests to avoid triggering rate limits.
PROBE_DELAY_SECONDS = 0.2

# Additional delay after each pattern attempt within a single company resolution.
INTER_PATTERN_DELAY_SECONDS = 0.1


def fetch_simplify_companies(client: httpx.Client, url: str) -> list[str]:
    """
    Fetch unique company names from a Simplify-shaped listings JSON.

    Both the Summer Internships and New-Grad-Positions repos publish the
    same JSON shape, so a single fetcher serves both.

    @param client: Shared httpx client for connection reuse.
    @param url: Raw URL of the Simplify listings JSON.
    @returns: Deduplicated list of company name strings.
    """
    try:
        resp = client.get(url, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: Could not fetch {url} — {exc}", file=sys.stderr)
        return []

    if not isinstance(data, list):
        return []

    names: list[str] = []
    for item in data:
        if isinstance(item, dict):
            company = item.get("company_name") or item.get("name") or item.get("company")
            if company and isinstance(company, str):
                names.append(company.strip())
        elif isinstance(item, str):
            names.append(item.strip())
    return list(dict.fromkeys(n for n in names if n))


def probe_greenhouse_slug(client: httpx.Client, slug: str) -> bool:
    """
    Return True if the Greenhouse boards API resolves the given slug.

    Uses the public /departments endpoint which requires no authentication
    and is CORS-safe. A 200 response means the board exists.

    @param client: Shared httpx client for connection reuse.
    @param slug: Candidate Greenhouse board identifier.
    @returns: True if the slug is valid, False otherwise.
    """
    if not slug:
        return False
    try:
        resp = client.get(
            f"https://boards-api.greenhouse.io/v1/boards/{slug}/departments",
            timeout=10.0,
        )
        return resp.status_code == 200
    except Exception:  # noqa: BLE001
        return False


def build_slug_patterns(name: str) -> list[str]:
    """
    Generate candidate Greenhouse slug strings for a company display name.

    Produces up to four transforms (some may be duplicates for short names):
    1. lowercase, spaces removed
    2. lowercase, spaces replaced with hyphens
    3. first word only
    4. lowercase with legal suffix stripped, then spaces removed

    @param name: Company display name.
    @returns: List of candidate slug strings (may contain duplicates).
    """
    base = name.lower()
    no_space = base.replace(" ", "")
    hyphenated = base.replace(" ", "-")
    first_word = base.split()[0] if base.split() else base
    stripped = re.sub(r"\s+(inc|corp|llc|ltd|co)\.?\s*$", "", base, flags=re.IGNORECASE)
    stripped_no_space = stripped.replace(" ", "")
    return [no_space, hyphenated, first_word, stripped_no_space]


def resolve_slug(client: httpx.Client, name: str) -> Optional[str]:
    """
    Find the working Greenhouse slug for a company name, or return None.

    Tries each pattern in order and stops at the first 200. Returns None
    when no pattern resolves, indicating the company is not on Greenhouse.

    @param client: Shared httpx client for connection reuse.
    @param name: Company display name.
    @returns: The working slug string, or None if not found.
    """
    seen: set[str] = set()
    for slug in build_slug_patterns(name):
        if slug in seen:
            continue
        seen.add(slug)
        if probe_greenhouse_slug(client, slug):
            return slug
        time.sleep(INTER_PATTERN_DELAY_SECONDS)
    return None


def load_existing_table() -> dict[str, Optional[str]]:
    """
    Load the current contents of the slug table JSON, or return an empty dict.

    @returns: Mapping of company name to slug (str) or None (confirmed absent).
    """
    if not OUTPUT_PATH.exists():
        return {}
    try:
        data = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        return dict(data.get("companies", {}))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"WARNING: Could not read existing table — {exc}", file=sys.stderr)
        return {}


def main() -> None:
    """Fetch company lists, probe each against Greenhouse, write the JSON table."""
    existing = load_existing_table()

    with httpx.Client() as client:
        names_internships = fetch_simplify_companies(client, SIMPLIFY_INTERNSHIPS_URL)
        names_newgrad = fetch_simplify_companies(client, SIMPLIFY_NEWGRAD_URL)

    all_names = list(dict.fromkeys(names_internships + names_newgrad))
    print(f"Total unique companies to consider: {len(all_names)}")

    companies: dict[str, Optional[str]] = dict(existing)
    probed = 0

    with httpx.Client() as client:
        for i, name in enumerate(all_names, start=1):
            existing_key = next(
                (k for k in companies if k.lower() == name.lower()), None
            )
            if existing_key is not None:
                print(f"[{i}/{len(all_names)}] {name} → cached ({companies[existing_key]!r})")
                continue

            slug = resolve_slug(client, name)
            companies[name] = slug
            label = f"✓ {slug}" if slug is not None else "✗ not on Greenhouse"
            print(f"[{i}/{len(all_names)}] {name} → {label}")
            probed += 1
            time.sleep(PROBE_DELAY_SECONDS)

    output = {"version": 1, "companies": companies}
    OUTPUT_PATH.write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"\nWrote {len(companies)} entries to {OUTPUT_PATH} ({probed} newly probed)")


if __name__ == "__main__":
    main()
