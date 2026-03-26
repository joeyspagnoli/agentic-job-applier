"""ATS platform detection from URL patterns and DOM markers.

Purpose:
    Classify the applicant tracking system hosting a job application for
    diagnostic logging and future platform-specific heuristics.  Detection
    is informational only and never drives form interaction.
"""

from __future__ import annotations

from src.agents.apply_worker.schemas import ATSPlatform

# Substring -> platform mapping applied against the page URL.
_URL_PATTERNS: list[tuple[str, ATSPlatform]] = [
    ("greenhouse.io", ATSPlatform.GREENHOUSE),
    ("boards.greenhouse", ATSPlatform.GREENHOUSE),
    ("lever.co", ATSPlatform.LEVER),
    ("jobs.lever", ATSPlatform.LEVER),
    ("myworkdayjobs.com", ATSPlatform.WORKDAY),
    ("workday.com", ATSPlatform.WORKDAY),
    ("icims.com", ATSPlatform.ICIMS),
    ("ashbyhq.com", ATSPlatform.ASHBY),
    ("smartrecruiters.com", ATSPlatform.SMARTRECRUITERS),
]

# Maximum number of leading characters to search in page HTML for
# DOM-based fallback detection when URL patterns do not match.
_DOM_SEARCH_LIMIT = 5_000


def detect_ats_platform(url: str, page_html: str) -> ATSPlatform:
    """Identify the ATS platform from the page URL and DOM content.

    Checks URL substrings first for speed, then falls back to a limited
    DOM search when no URL pattern matches.

    Args:
        url: The current page URL (after any redirects).
        page_html: Raw HTML content of the page for fallback detection.

    Returns:
        The detected ATSPlatform enum value, or ATSPlatform.UNKNOWN when
        no platform can be identified.
    """

    lower_url = url.lower()
    for pattern, platform in _URL_PATTERNS:
        if pattern in lower_url:
            return platform

    # Fallback: search a limited prefix of the DOM for platform markers.
    html_prefix = page_html[:_DOM_SEARCH_LIMIT].lower()
    if "greenhouse" in html_prefix:
        return ATSPlatform.GREENHOUSE
    if "lever" in html_prefix:
        return ATSPlatform.LEVER
    if "workday" in html_prefix:
        return ATSPlatform.WORKDAY

    return ATSPlatform.UNKNOWN


__all__ = [
    "detect_ats_platform",
]
