"""Discover Taleo portal IDs for all configured tenant/section pairs.

Run this script once to populate the ``portal_id`` field in ``companies.yaml``.
Each entry emits a YAML snippet you can paste directly into the config file.

Usage::

    uv run scripts/discover_taleo_portals.py

Output is printed to stdout, one YAML-snippet block per company.
Companies that fail discovery print ``portal_id: null``.
"""

from __future__ import annotations

import asyncio
import re
import sys
from dataclasses import dataclass

import httpx

_PORTAL_ID_RE = re.compile(
    r'["\']?portalId["\']?\s*[=:]\s*["\']?(\d+)',
)

REQUEST_TIMEOUT = 20.0
CONCURRENCY = 10
"""Max simultaneous discovery requests; stay polite to Taleo infrastructure."""


@dataclass(frozen=True)
class TaleoEntry:
    """One row from the companies.yaml taleo_companies block."""

    display_name: str
    tenant_id: str
    career_section: str


# ---------------------------------------------------------------------------
# Full tenant/section reference — matches the taleo_companies block in
# config/companies.yaml.  Sorted by industry then display name.
# ---------------------------------------------------------------------------
ENTRIES: list[TaleoEntry] = [
    # ── Healthcare / Pharma ──────────────────────────────────────────────────
    TaleoEntry("Johnson & Johnson", "jnjc", "iam"),
    TaleoEntry("Abbott Laboratories", "abbott", "2"),
    TaleoEntry("Medtronic", "medtronic", "2"),
    TaleoEntry("Baxter International", "baxter", "2"),
    TaleoEntry("Edwards Lifesciences", "edwards", "edwards_external_cs"),
    TaleoEntry("HCA Healthcare", "hca", "0hca"),
    TaleoEntry("Tenet Healthcare", "tenet", "10100mb"),
    TaleoEntry("Merck", "merck", "internal_msd_10880"),
    TaleoEntry("AbbVie", "abbvie", "5"),
    TaleoEntry("Bristol Myers Squibb", "bms", "ejs+external+career+site+w2fprofile+ques+v20090518"),
    # ── Financial / Insurance ────────────────────────────────────────────────
    TaleoEntry("Morgan Stanley", "ms", "2"),
    TaleoEntry("Citigroup", "citi", "2"),
    TaleoEntry("US Bancorp", "usbank", "10000"),
    TaleoEntry("Prudential Financial", "pru", "pru_campus_core"),
    TaleoEntry("Aetna (CVS Health)", "acthealth", "external"),
    TaleoEntry("Cigna", "cigna", "cg_external"),
    TaleoEntry("Humana", "humana", "externalus"),
    TaleoEntry("Anthem (Elevance Health)", "antheminc", "10021"),
    TaleoEntry("Hartford Financial", "thehartford", "2"),
    TaleoEntry("JPMorgan Chase", "jpmchase", "10140"),
    # ── Manufacturing / Industrial ───────────────────────────────────────────
    TaleoEntry("Emerson Electric", "emerson", "ex"),
    TaleoEntry("Eaton Corporation", "eaton", "ex"),
    TaleoEntry("Textron", "textron", "textron"),
    TaleoEntry("Rexnord", "rexnord", "2"),
    TaleoEntry("Curtiss-Wright", "cwt", "ex"),
    TaleoEntry("TransDigm Group", "tgh", "ex"),
    TaleoEntry("Heico Corporation", "hccs", "6"),
    TaleoEntry("Moog Inc (External)", "moogrecruit", "ex"),
    TaleoEntry("Moog Inc (Internal)", "moogrecruit", "in"),
    # ── Energy / Chemicals ───────────────────────────────────────────────────
    TaleoEntry("ConocoPhillips", "cop", "10000"),
    TaleoEntry("Dow Chemical", "dow", "2"),
    TaleoEntry("BASF US", "basf", "2"),
    TaleoEntry("Linde (via Praxair)", "praxair", "2"),
    TaleoEntry("DCP Midstream", "dcpmidstream", "ex"),
    TaleoEntry("Baker Hughes", "bakerhughes", "bhiexternal"),
    TaleoEntry("BP US", "bt", "external"),
    # ── Retail / Tech / Telecom / Government Contractors ────────────────────
    TaleoEntry("AT&T (Main)", "att", "10161"),
    TaleoEntry("AT&T (Secondary)", "att", "10168"),
    TaleoEntry("T-Mobile", "tmm", "10020"),
    TaleoEntry("Charter Communications", "charter", "charter_external_career_site"),
    TaleoEntry("Oracle", "oracle", "2"),
    TaleoEntry("Leidos (External)", "leidos", "1leidos_ext"),
    TaleoEntry("Leidos (Security)", "leidos", "3leidos_sec"),
    TaleoEntry("SAIC", "saicjobs", "ex"),
    TaleoEntry("SAIC (Security)", "saicjobs", "3saic_sec"),
    TaleoEntry("CACI International", "caci", "2"),
    TaleoEntry("DXC Technology", "dxc", "2"),
    TaleoEntry("Target HQ", "target", "tgt_hq"),
    TaleoEntry("Target (Graduate)", "target", "tgt_hq_grad"),
    TaleoEntry("Cintas", "cintas", "10000"),
    TaleoEntry("ADT Security (External)", "adt", "external"),
    TaleoEntry("ADT Security (Mobile)", "adt", "exmobile"),
    TaleoEntry("Jacobs Engineering", "jacobs", "ex"),
    TaleoEntry("KBR", "kbr", "6"),
    TaleoEntry("Parsons Corporation", "parsons", "TCN"),
    TaleoEntry("Burns & McDonnell (External)", "burnsmcdonn", "external"),
    TaleoEntry("Burns & McDonnell (Campus)", "burnsmcdonn", "campus"),
    TaleoEntry("Booz Allen Hamilton", "bah", "10020"),
    TaleoEntry("Northrop Grumman (Professional)", "ngc", "ngc_pro"),
    TaleoEntry("Northrop Grumman (Campus)", "ngc", "ngc_coll"),
]


async def _discover_one(
    entry: TaleoEntry,
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
) -> tuple[TaleoEntry, str | None]:
    """Discover the portal ID for one tenant/section pair.

    Purpose:
        GET the career section landing page, extract the ``portalId`` from the
        embedded JavaScript, and return it alongside the entry for reporting.
    Args:
        entry: Tenant/section pair to probe.
        client: Shared async HTTP client.
        semaphore: Semaphore limiting concurrent outbound requests.
    Output:
        Returns a tuple of ``(entry, portal_id_or_None)``.
    """
    async with semaphore:
        url = (
            f"https://{entry.tenant_id}.taleo.net"
            f"/careersection/{entry.career_section}/jobsearch.ftl?lang=en"
        )
        try:
            resp = await client.get(url, follow_redirects=True)
        except httpx.RequestError as exc:
            print(f"  # ERROR: {exc}", file=sys.stderr)
            return entry, None

        if resp.status_code != 200:
            print(
                f"  # HTTP {resp.status_code} for {entry.tenant_id}/{entry.career_section}",
                file=sys.stderr,
            )
            return entry, None

        m = _PORTAL_ID_RE.search(resp.text)
        return entry, m.group(1) if m else None


def _yaml_key(display_name: str) -> str:
    """Return the YAML key for a display name, quoting when needed."""
    needs_quotes = any(c in display_name for c in ":#&'")
    return f'  "{display_name}"' if needs_quotes else f"  {display_name}"


async def main() -> None:
    """Discover portal IDs for all entries and print a YAML snippet.

    Purpose:
        Iterate over all known Taleo Enterprise tenant/section pairs,
        fetch each portal ID concurrently, and emit a ``taleo_companies:``
        YAML block ready to paste into ``config/companies.yaml``.
    Args:
        None.
    Output:
        Returns ``None`` after printing the YAML block to stdout.
    """
    semaphore = asyncio.Semaphore(CONCURRENCY)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, headers=headers) as client:
        tasks = [_discover_one(entry, client, semaphore) for entry in ENTRIES]
        results: list[tuple[TaleoEntry, str | None]] = await asyncio.gather(*tasks)

    print("taleo_companies:")
    for entry, portal_id in results:
        key = _yaml_key(entry.display_name)
        pid = f'"{portal_id}"' if portal_id else "null"
        print(f"{key}:")
        print(f"    tenant_id: {entry.tenant_id}")
        print(f"    career_section: {entry.career_section}")
        print(f"    portal_id: {pid}")

    found = sum(1 for _, pid in results if pid)
    print(
        f"\n# Discovery complete: {found}/{len(results)} portal IDs found.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    asyncio.run(main())
