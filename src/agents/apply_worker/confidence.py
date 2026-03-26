"""Deterministic confidence scoring for job application form completeness.

Purpose:
    Compute a weighted confidence score from DOM-level checks to decide
    whether an application is ready for submission.  All checks are
    executed via Playwright page.evaluate() and produce an auditable
    breakdown of each factor.
"""

from __future__ import annotations

from playwright.async_api import Page

from src.agents.apply_worker.schemas import ATSPlatform
from src.agents.apply_worker.schemas import ConfidenceCheck
from src.agents.apply_worker.schemas import ConfidenceReport

# ---------------------------------------------------------------------------
# Weights for each confidence check (must sum to ~1.0)
# ---------------------------------------------------------------------------

_WEIGHT_PAGE_LOADED = 0.10
_WEIGHT_SIMPLIFY_DETECTED = 0.15
_WEIGHT_RESUME_UPLOADED = 0.20
_WEIGHT_NAME_POPULATED = 0.10
_WEIGHT_EMAIL_POPULATED = 0.10
_WEIGHT_NO_UNRESOLVED_REQUIRED = 0.20
_WEIGHT_NO_ERROR_BANNERS = 0.10
_WEIGHT_CORRECT_DOMAIN = 0.05

# JavaScript snippets executed in the browser for each check.
_JS_CHECK_NAME = """
() => {
    const selectors = [
        'input[name*="name" i]',
        'input[autocomplete*="name" i]',
        'input[id*="name" i]',
        'input[placeholder*="name" i]',
    ];
    for (const sel of selectors) {
        const el = document.querySelector(sel);
        if (el && el.value && el.value.trim().length > 0) return true;
    }
    return false;
}
"""

_JS_CHECK_EMAIL = """
() => {
    const selectors = [
        'input[type="email"]',
        'input[name*="email" i]',
        'input[autocomplete*="email" i]',
    ];
    for (const sel of selectors) {
        const el = document.querySelector(sel);
        if (el && el.value && el.value.trim().length > 0) return true;
    }
    return false;
}
"""

_JS_CHECK_UNRESOLVED_REQUIRED = """
() => {
    const fields = document.querySelectorAll(
        'input[required], select[required], textarea[required], ' +
        '[aria-required="true"]'
    );
    let empty = 0;
    fields.forEach(el => {
        if (el.type === 'hidden' || el.type === 'submit') return;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden') return;
        if (!el.value || el.value.trim() === '') empty++;
    });
    return empty;
}
"""

_JS_CHECK_ERROR_BANNERS = """
() => {
    const errorEls = document.querySelectorAll(
        '.error, .field-error, .validation-error, [role="alert"]'
    );
    let visibleErrors = 0;
    errorEls.forEach(el => {
        const style = window.getComputedStyle(el);
        if (style.display !== 'none' && style.visibility !== 'hidden') {
            if (el.textContent && el.textContent.trim().length > 0) {
                visibleErrors++;
            }
        }
    });
    return visibleErrors;
}
"""


async def compute_confidence(
    page: Page,
    *,
    resume_uploaded: bool,
    simplify_detected: bool,
    ats_platform: ATSPlatform,
    original_url: str,
) -> ConfidenceReport:
    """Compute a deterministic confidence score from DOM-level checks.

    Each check contributes a weighted factor to the overall score.
    Hard blockers (unresolved required fields, missing resume) are
    flagged separately so future auto-submit logic can gate on them.

    Args:
        page: The Playwright page to evaluate checks against.
        resume_uploaded: Whether the resume PDF was successfully uploaded.
        simplify_detected: Whether Simplify extension activation was seen.
        ats_platform: The detected ATS platform for this application.
        original_url: The original job application URL for domain matching.

    Returns:
        A ConfidenceReport with the weighted score and per-check breakdown.
    """

    checks: list[ConfidenceCheck] = []

    # Check 1: Page loaded successfully (no error page)
    page_loaded = not _is_error_page(page.url)
    checks.append(
        ConfidenceCheck(
            name="page_loaded",
            passed=page_loaded,
            weight=_WEIGHT_PAGE_LOADED,
            detail=f"URL: {page.url}",
        )
    )

    # Check 2: Simplify autofill detected
    checks.append(
        ConfidenceCheck(
            name="simplify_autofill_detected",
            passed=simplify_detected,
            weight=_WEIGHT_SIMPLIFY_DETECTED,
        )
    )

    # Check 3: Resume uploaded
    checks.append(
        ConfidenceCheck(
            name="resume_uploaded",
            passed=resume_uploaded,
            weight=_WEIGHT_RESUME_UPLOADED,
        )
    )

    # Check 4: Name field populated
    name_filled = await page.evaluate(_JS_CHECK_NAME)
    checks.append(
        ConfidenceCheck(
            name="name_populated",
            passed=bool(name_filled),
            weight=_WEIGHT_NAME_POPULATED,
        )
    )

    # Check 5: Email field populated
    email_filled = await page.evaluate(_JS_CHECK_EMAIL)
    checks.append(
        ConfidenceCheck(
            name="email_populated",
            passed=bool(email_filled),
            weight=_WEIGHT_EMAIL_POPULATED,
        )
    )

    # Check 6: No unresolved required fields
    unresolved_required: int = await page.evaluate(_JS_CHECK_UNRESOLVED_REQUIRED)
    no_unresolved = unresolved_required == 0
    checks.append(
        ConfidenceCheck(
            name="no_unresolved_required",
            passed=no_unresolved,
            weight=_WEIGHT_NO_UNRESOLVED_REQUIRED,
            detail=f"{unresolved_required} required fields empty",
        )
    )

    # Check 7: No visible error banners
    error_count: int = await page.evaluate(_JS_CHECK_ERROR_BANNERS)
    no_errors = error_count == 0
    checks.append(
        ConfidenceCheck(
            name="no_error_banners",
            passed=no_errors,
            weight=_WEIGHT_NO_ERROR_BANNERS,
            detail=f"{error_count} visible error elements",
        )
    )

    # Check 8: Still on expected domain
    correct_domain = _domains_match(original_url, page.url)
    checks.append(
        ConfidenceCheck(
            name="correct_domain",
            passed=correct_domain,
            weight=_WEIGHT_CORRECT_DOMAIN,
            detail=f"Current: {page.url}",
        )
    )

    # Compute weighted score
    score = sum(c.weight for c in checks if c.passed)
    score = min(score, 1.0)

    # Hard blockers: conditions that must prevent auto-submit
    has_hard_blockers = (not resume_uploaded) or (unresolved_required > 0)

    # Count unresolved optional fields (fields empty but not required)
    # This is a lightweight estimate; the full scan is in field_scanner.
    unresolved_optional = 0

    return ConfidenceReport(
        score=round(score, 4),
        checks=checks,
        has_hard_blockers=has_hard_blockers,
        resume_uploaded=resume_uploaded,
        simplify_autofill_detected=simplify_detected,
        unresolved_required_count=unresolved_required,
        unresolved_optional_count=unresolved_optional,
        ats_platform=ats_platform,
    )


def _is_error_page(url: str) -> bool:
    """Check if the current URL indicates an error or redirect page.

    Args:
        url: The current page URL.

    Returns:
        True if the URL suggests an error state.
    """

    lower = url.lower()
    error_indicators = ["error", "404", "not-found", "access-denied", "blocked"]
    return any(indicator in lower for indicator in error_indicators)


def _domains_match(original_url: str, current_url: str) -> bool:
    """Check if two URLs share the same base domain.

    Args:
        original_url: The expected application page URL.
        current_url: The URL the page actually navigated to.

    Returns:
        True if the domains are compatible.
    """

    try:
        # Extract domain from URLs by splitting on ://  and /
        orig_domain = original_url.split("://", 1)[-1].split("/", 1)[0].lower()
        curr_domain = current_url.split("://", 1)[-1].split("/", 1)[0].lower()

        # Remove www. prefix for comparison
        orig_domain = orig_domain.removeprefix("www.")
        curr_domain = curr_domain.removeprefix("www.")

        # Check if one domain ends with the other (handles subdomains)
        return orig_domain.endswith(curr_domain) or curr_domain.endswith(
            orig_domain,
        )
    except (IndexError, AttributeError):
        return False


__all__ = [
    "compute_confidence",
]
