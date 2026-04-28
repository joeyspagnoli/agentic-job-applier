"""Job posting liveness checker.

Inspired by career-ops' check-liveness.mjs + liveness-core.mjs.
Verifies whether scraped job URLs are still active by checking for
expired signals, apply buttons, and content quality.

Uses httpx for lightweight checks (no Playwright required for basic
detection). Falls back to 'uncertain' when signals are ambiguous.
"""

from __future__ import annotations

import re
from enum import Enum

import httpx
from loguru import logger

LIVENESS_TIMEOUT_SECONDS = 10.0

# Patterns that indicate a job posting is no longer active.
EXPIRED_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"this job is no longer available",
        r"this position has been filled",
        r"this job posting has expired",
        r"this listing has been removed",
        r"no longer accepting applications",
        r"this role has been closed",
        r"job not found",
        r"page not found",
        r"404.*not found",
        r"this opportunity is no longer open",
        r"this position is no longer available",
    ]
]

# Patterns that indicate an active apply mechanism.
APPLY_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"<button[^>]*>.*?apply.*?</button>",
        r"<a[^>]*>.*?apply.*?</a>",
        r'class="[^"]*apply[^"]*"',
        r'id="[^"]*apply[^"]*"',
        r"apply\s+(now|here|today|for this)",
        r"submit\s+(your\s+)?application",
        r"(solicitar|bewerben|postuler)",
    ]
]

MINIMUM_CONTENT_LENGTH = 300


class LivenessResult(str, Enum):
    """Result of a job posting liveness check."""

    ACTIVE = "active"
    EXPIRED = "expired"
    UNCERTAIN = "uncertain"


async def check_liveness(
    url: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> tuple[LivenessResult, str]:
    """Check whether a job posting URL is still active.

    Makes a GET request and inspects the response body for expired
    signals, apply buttons, and minimum content length.

    Args:
        url: The job posting URL to check.
        client: Optional shared HTTP client. Creates one if not provided.

    Returns:
        A (result, reason) tuple with the liveness verdict and explanation.
    """
    should_close = client is None
    if client is None:
        client = httpx.AsyncClient(
            timeout=LIVENESS_TIMEOUT_SECONDS,
            follow_redirects=True,
        )

    try:
        return await _check_url(client, url)
    except httpx.TimeoutException:
        return LivenessResult.UNCERTAIN, "Request timed out"
    except httpx.RequestError as exc:
        return LivenessResult.UNCERTAIN, f"Connection error: {exc}"
    finally:
        if should_close:
            await client.aclose()


async def _check_url(
    client: httpx.AsyncClient,
    url: str,
) -> tuple[LivenessResult, str]:
    """Perform the actual liveness check against a URL.

    Args:
        client: HTTP client for the request.
        url: Job posting URL.

    Returns:
        A (result, reason) tuple.
    """
    response = await client.get(url)

    # Redirect to error page or generic page.
    if "error=true" in str(response.url) or "error" in str(response.url).split("?")[-1]:
        return LivenessResult.EXPIRED, "Redirected to error page"

    # 404 or 410 are clear expired signals.
    if response.status_code in (404, 410):
        return LivenessResult.EXPIRED, f"HTTP {response.status_code}"

    # Non-2xx responses are uncertain.
    if response.status_code >= 400:
        return LivenessResult.UNCERTAIN, f"HTTP {response.status_code}"

    body = response.text

    # Check for expired signal patterns (these win over apply buttons).
    for pattern in EXPIRED_PATTERNS:
        match = pattern.search(body)
        if match:
            return LivenessResult.EXPIRED, f"Expired signal: {match.group(0)[:80]}"

    # Check for apply button presence.
    has_apply = False
    for pattern in APPLY_PATTERNS:
        if pattern.search(body):
            has_apply = True
            break

    if has_apply:
        return LivenessResult.ACTIVE, "Apply mechanism found"

    # Fallback: check content length as a proxy for a real job page.
    # Pages with minimal content are likely redirects or empty shells.
    text_content = re.sub(r"<[^>]+>", "", body)
    text_content = re.sub(r"\s+", " ", text_content).strip()

    if len(text_content) > MINIMUM_CONTENT_LENGTH:
        return LivenessResult.UNCERTAIN, "Content present but no apply button found"

    return LivenessResult.UNCERTAIN, "Insufficient content to determine liveness"
