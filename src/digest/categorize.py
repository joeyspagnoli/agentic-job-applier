"""Classify job postings into the digest's user-facing field categories.

The email digest lets subscribers pick field chips (Software, AI/ML/Data,
Hardware, Product, Quant, Business, Design). Historically the category a
job carried depended on which fetcher found it: SimplifyJobs listings kept
Simplify's own label, two Indeed boards stamped a hard-coded
``digest_category``, and every ATS/LinkedIn job had none — so uncategorized
jobs bypassed subscribers' field filters entirely.

This module is the single authority the digest uses instead: a
deterministic title-based classifier with the source-provided category as a
recall fallback. It runs at digest-render time, so tuning a rule takes
effect on the next send without any backfill or fetcher changes.
"""

from __future__ import annotations

import re
from typing import Final

# Canonical digest categories. These are the values subscriber field chips
# map to (see ``_FIELD_TO_CATEGORY`` in src/digest/sender.py) and the values
# SimplifyJobs uses in listings.json, so source categories can be trusted
# as-is when they appear in this set.
CATEGORY_SOFTWARE: Final[str] = "Software"
CATEGORY_AI_ML_DATA: Final[str] = "AI/ML/Data"
CATEGORY_HARDWARE: Final[str] = "Hardware"
CATEGORY_PRODUCT: Final[str] = "Product"
CATEGORY_QUANT: Final[str] = "Quant"
CATEGORY_BUSINESS: Final[str] = "Business"
CATEGORY_DESIGN: Final[str] = "Design"
CATEGORY_OTHER: Final[str] = "Other"

# Render order for category sections in the digest email. ``Other`` is last
# because it only appears for subscribers with no field selection.
CANONICAL_CATEGORY_ORDER: Final[tuple[str, ...]] = (
    CATEGORY_SOFTWARE,
    CATEGORY_AI_ML_DATA,
    CATEGORY_HARDWARE,
    CATEGORY_DESIGN,
    CATEGORY_PRODUCT,
    CATEGORY_QUANT,
    CATEGORY_BUSINESS,
    CATEGORY_OTHER,
)

KNOWN_CATEGORIES: Final[frozenset[str]] = frozenset(CANONICAL_CATEGORY_ORDER)

# Ordered classification rules — the first category whose pattern matches
# the title wins. Order is load-bearing:
#
# 1. The ``Other`` rule runs first so clearly non-target disciplines
#    (civil, warranty, technicians, clerical, healthcare) never reach the
#    broad catch-alls below, even when the source labeled them Software or
#    AI/ML/Data (Simplify's own labels are loose).
# 2. Hardware precedes Design so "ASIC Design Engineer" is Hardware while
#    "Product Designer" still lands in Design.
# 3. Design precedes Product so "Product Designer" is Design and
#    "Product Manager" is Product.
# 4. AI/ML/Data precedes Business so "Business Intelligence Intern" and
#    "Operations Analytics" resolve to data work, and Business precedes
#    Software so bank programs never fall into the bare-"engineer" rule.
# 5. Software runs last with the broadest patterns, ending in a bare
#    "engineer(ing)" catch-all — at the companies this pipeline watches,
#    an otherwise-unclassified engineering title is far more likely SWE
#    than anything else, and recall matters more than precision here.
_CATEGORY_RULES: Final[tuple[tuple[str, re.Pattern[str]], ...]] = tuple(
    (category, re.compile(pattern, re.IGNORECASE))
    for category, pattern in (
        (
            CATEGORY_OTHER,
            r"\bcivil\b|\bstructural\b|geotech|\bhvac\b|\bchemical\b"
            r"|\benvironmental\b|\bwarranty\b|\bmanufacturing\b"
            r"|industrial engineer|process engineer|\btechnician\b"
            r"|\binstaller\b|\badministrative\b|\bclerical\b|\bnurse\b"
            r"|\bclinical\b|\bmechanic\b|\bhelper\b|\bcustodian\b"
            r"|\bwarehouse\b|\bdriver\b",
        ),
        (
            CATEGORY_QUANT,
            r"\bquant(itative)?\b|\btrader\b|\btrading\b",
        ),
        (
            CATEGORY_HARDWARE,
            r"\bhardware\b|\basic\b|\bfpga\b|\bsilicon\b|semiconductor"
            r"|analog design|chip design|physical design|\brtl\b"
            r"|\bembedded\b|\bfirmware\b|electrical engineer|\bcircuit\b"
            r"|\bpcb\b|\bmechanical\b|\bphotonics\b|\brf\b|\bmixed.signal\b",
        ),
        (
            CATEGORY_DESIGN,
            r"\bdesigner\b|\bux\b|\bui\b|user experience|user interface"
            r"|product design|interaction design|visual design"
            r"|graphic design|brand design|design systems?\b",
        ),
        (
            CATEGORY_AI_ML_DATA,
            r"machine learning|\bml\b|mlops|\bai\b|artificial intelligence"
            r"|deep learning|computer vision|\bnlp\b|\bllm\b|genai"
            r"|generative|data scien|data engineer|data analyst"
            r"|data analytics|\banalytics\b|business intelligence"
            r"|research scientist|research engineer|research intern"
            r"|applied scientist|\bgis\b",
        ),
        (
            CATEGORY_PRODUCT,
            r"product manager|product management|program manager"
            r"|technical program|product owner|\bapm\b|product analyst"
            r"|product operations|product intern",
        ),
        (
            CATEGORY_BUSINESS,
            r"\bfinance\b|\bfinancial\b|\baccounting\b|\baccountant\b"
            r"|\bcredit\b|\binvestment\b|\bbank(ing)?\b|asset management"
            r"|\bwealth\b|\bacquisitions\b|capital markets|fp&a"
            r"|underwrit|supply chain|\blogistics\b|\bprocurement\b"
            r"|\boperations\b|\bconsult(ing|ant)\b|\bmarketing\b"
            r"|\bsales\b(?!\s+engineer)|human resources|\bhr\b"
            r"|real estate|\btreasury\b|\baudit\b|\btax\b|\btrainee\b"
            r"|leadership development|summer analyst|analyst program"
            r"|\beconomics\b|\beconomist\b|\bactuar|\banalyst\b",
        ),
        (
            CATEGORY_SOFTWARE,
            r"\bsoftware\b|\bswe\b|\bdeveloper\b|\bprogrammer\b"
            r"|full.?stack|\bbackend\b|back.?end|\bfrontend\b|front.?end"
            r"|\bweb\b|\bmobile\b|\bios\b|\bandroid\b|\bdevops\b"
            r"|site reliability|\bsre\b|\bplatform\b|\binfrastructure\b"
            r"|\bcloud\b|\bsecurity\b|\bcyber|solutions engineer"
            r"|solutions architect|sales engineer|forward deployed"
            r"|computer science|systems engineer|\bengineer(ing)?\b",
        ),
    )
)


def categorize_job(title: str | None, source_category: str | None = None) -> str:
    """Return the canonical digest category for a job.

    Purpose:
        Give the digest one authoritative category per job so subscriber
        field chips filter every source uniformly, instead of only the few
        sources that happened to ship a category label.
    Args:
        title: The job posting title. ``None``/empty titles skip straight
            to the fallback logic.
        source_category: Category label carried by the source, if any
            (e.g. Simplify's ``category`` field). Used only when no title
            rule matches, and only when it is one of the canonical
            categories — this keeps recall for vague titles like
            "HLS Intern" that a curated source has already classified.
    Output:
        Returns one of the ``CATEGORY_*`` constants; ``CATEGORY_OTHER``
        when neither the title nor the source category resolves.
    """
    if title:
        for category, pattern in _CATEGORY_RULES:
            if pattern.search(title):
                return category

    if source_category in KNOWN_CATEGORIES:
        return str(source_category)

    return CATEGORY_OTHER
