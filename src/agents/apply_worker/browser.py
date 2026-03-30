"""Browser orchestration for applying to jobs via Playwright CDP.

Purpose:
    Connect to a running Chrome instance over CDP, navigate to a job
    application page, trigger Simplify Copilot autofill, upload the
    tailored resume, and capture rich diagnostics for every attempt.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import httpx
from loguru import logger
from playwright.async_api import Page
from playwright.async_api import async_playwright

from src.agents.apply_worker.ats_detection import detect_ats_platform
from src.agents.apply_worker.confidence import compute_confidence
from src.agents.apply_worker.field_scanner import scan_unresolved_fields
from src.agents.apply_worker.resume_upload import upload_resume
from src.agents.apply_worker.schemas import ApplyOutcome
from src.agents.apply_worker.schemas import ApplyRunResult
from src.agents.apply_worker.schemas import ATSPlatform
from src.agents.apply_worker.schemas import DEFAULT_CDP_URL
from src.agents.apply_worker.schemas import DEFAULT_PAGE_LOAD_TIMEOUT_MS
from src.agents.apply_worker.schemas import FORM_STABILITY_WAIT_MS
from src.agents.apply_worker.schemas import SIMPLIFY_POLL_INTERVAL_MS
from src.agents.apply_worker.schemas import SIMPLIFY_POLL_TIMEOUT_MS

# JavaScript that waits for DOM stability by observing mutations.
# Resolves after the specified quiet period with no changes.
_JS_WAIT_FOR_STABILITY = """
(quietMs) => new Promise(resolve => {
    let timer;
    const observer = new MutationObserver(() => {
        clearTimeout(timer);
        timer = setTimeout(() => { observer.disconnect(); resolve(true); }, quietMs);
    });
    observer.observe(document.body, {
        childList: true,
        subtree: true,
        attributes: true,
    });
    // Start the initial timer in case no mutations happen at all
    timer = setTimeout(() => { observer.disconnect(); resolve(true); }, quietMs);
})
"""

# JavaScript that polls for Simplify extension DOM markers.
# Returns true if Simplify UI elements are detected within the timeout.
_JS_DETECT_SIMPLIFY = """
({ intervalMs, timeoutMs }) => new Promise(resolve => {
    const normalizedIntervalMs = Number(intervalMs) || 500;
    const normalizedTimeoutMs = Number(timeoutMs) || 30000;
    const start = Date.now();
    function check() {
        // Look for Simplify-injected elements by common markers
        const markers = document.querySelectorAll(
            '[class*="simplify" i], [id*="simplify" i], ' +
            '[data-simplify], [class*="Simplify" i]'
        );
        if (markers.length > 0) {
            resolve(true);
            return;
        }
        if (Date.now() - start > normalizedTimeoutMs) {
            resolve(false);
            return;
        }
        setTimeout(check, normalizedIntervalMs);
    }
    check();
})
"""

# Selector for the Simplify autofill trigger button.
_SIMPLIFY_BUTTON_SELECTOR = (
    '[class*="simplify" i] button, '
    '[id*="simplify" i] button, '
    'button[class*="simplify" i], '
    '[data-simplify] button'
)


async def check_chrome_reachable(cdp_url: str = DEFAULT_CDP_URL) -> bool:
    """Verify that Chrome is running and reachable over CDP.

    Args:
        cdp_url: The Chrome DevTools Protocol endpoint URL.

    Returns:
        True if Chrome responds to the version endpoint.
    """

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{cdp_url}/json/version",
                timeout=5.0,
            )
            return response.status_code == 200
    except (httpx.HTTPError, OSError):
        return False


async def apply_to_job(
    *,
    cdp_url: str = DEFAULT_CDP_URL,
    source_url: str,
    resume_pdf_path: Path,
    job_hash: str,
    artifact_dir: Path,
    dry_run: bool = True,
) -> ApplyRunResult:
    """Execute one browser-based job application attempt.

    Connects to Chrome via CDP, navigates to the application page,
    triggers Simplify autofill, uploads the resume, and captures
    diagnostics.  In dry-run mode (v1 default), stops before submit
    and marks the outcome as NEEDS_REVIEW.

    Args:
        cdp_url: Chrome DevTools Protocol endpoint URL.
        source_url: The job application page URL to navigate to.
        resume_pdf_path: Absolute path to the resume PDF to upload.
        job_hash: Job identifier for logging and artifact naming.
        artifact_dir: Directory to store screenshots and DOM snapshots.
        dry_run: When True, do not click submit. Defaults to True.

    Returns:
        An ApplyRunResult with success status, diagnostics, and captured
        artifact paths.
    """

    artifact_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = artifact_dir / "screenshot_pre_submit.png"
    dom_snapshot_path = artifact_dir / "dom_snapshot.html"
    unresolved_path = artifact_dir / "unresolved_fields.json"

    ats_platform = ATSPlatform.UNKNOWN

    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.connect_over_cdp(cdp_url)
        except Exception as exc:
            logger.error("Failed to connect to Chrome at {}: {}", cdp_url, exc)
            return ApplyRunResult(
                success=False,
                outcome=ApplyOutcome.FAILED_NAVIGATION,
                failure_reason=f"CDP connection failed: {exc}",
            )

        # Use the default (real) browser context
        context = browser.contexts[0] if browser.contexts else None
        if context is None:
            logger.error("No browser context available in Chrome at {}", cdp_url)
            return ApplyRunResult(
                success=False,
                outcome=ApplyOutcome.FAILED_NAVIGATION,
                failure_reason="No browser context available",
            )

        page = await context.new_page()
        try:
            result = await _run_application_flow(
                page=page,
                source_url=source_url,
                resume_pdf_path=resume_pdf_path,
                job_hash=job_hash,
                screenshot_path=screenshot_path,
                dom_snapshot_path=dom_snapshot_path,
                unresolved_path=unresolved_path,
                dry_run=dry_run,
            )
            return result

        except Exception as exc:
            logger.exception(
                "Unhandled error during apply for job_hash={}: {}",
                job_hash,
                exc,
            )
            # Attempt to capture diagnostics even on failure
            await _save_screenshot_safe(page, screenshot_path)
            await _save_dom_safe(page, dom_snapshot_path)

            return ApplyRunResult(
                success=False,
                outcome=ApplyOutcome.FAILED_OTHER,
                failure_reason=str(exc),
                ats_platform=ats_platform,
                page_url=page.url,
                screenshot_path=str(screenshot_path)
                if screenshot_path.exists()
                else None,
                dom_snapshot_path=str(dom_snapshot_path)
                if dom_snapshot_path.exists()
                else None,
            )

        finally:
            await page.close()


async def _run_application_flow(
    *,
    page: object,
    source_url: str,
    resume_pdf_path: Path,
    job_hash: str,
    screenshot_path: Path,
    dom_snapshot_path: Path,
    unresolved_path: Path,
    dry_run: bool,
) -> ApplyRunResult:
    """Execute the sequential application flow steps.

    This is separated from apply_to_job to keep the try/finally clean.

    Args:
        page: The Playwright page to use for the application.
        source_url: Application page URL.
        resume_pdf_path: Path to the resume PDF.
        job_hash: Job identifier for logging.
        screenshot_path: Where to save the screenshot.
        dom_snapshot_path: Where to save the DOM snapshot.
        unresolved_path: Where to save unresolved fields JSON.
        dry_run: Whether to skip the submit step.

    Returns:
        An ApplyRunResult with full diagnostics.
    """

    playwright_page = cast(Page, page)

    # Step 1: Navigate to the application page
    logger.info("Navigating to {} for job_hash={}", source_url, job_hash)
    try:
        await playwright_page.goto(source_url, timeout=DEFAULT_PAGE_LOAD_TIMEOUT_MS)
        await playwright_page.wait_for_load_state(
            "networkidle",
            timeout=DEFAULT_PAGE_LOAD_TIMEOUT_MS,
        )
    except Exception as exc:
        logger.error("Navigation failed for {}: {}", source_url, exc)
        await _save_screenshot_safe(playwright_page, screenshot_path)
        return ApplyRunResult(
            success=False,
            outcome=ApplyOutcome.FAILED_NAVIGATION,
            failure_reason=f"Navigation failed: {exc}",
            page_url=playwright_page.url,
            screenshot_path=str(screenshot_path)
            if screenshot_path.exists()
            else None,
        )

    page_url = playwright_page.url
    page_html = await playwright_page.content()

    # Step 2: Detect ATS platform (diagnostic only)
    ats_platform = detect_ats_platform(page_url, page_html)
    logger.info("Detected ATS platform: {} for job_hash={}", ats_platform, job_hash)

    # Step 3: Wait for Simplify extension to activate
    logger.info("Waiting for Simplify extension activation...")
    simplify_detected: bool = await playwright_page.evaluate(
        _JS_DETECT_SIMPLIFY,
        {
            "intervalMs": SIMPLIFY_POLL_INTERVAL_MS,
            "timeoutMs": SIMPLIFY_POLL_TIMEOUT_MS,
        },
    )

    if simplify_detected:
        logger.info("Simplify extension detected for job_hash={}", job_hash)
        # Try to click the Simplify autofill button
        await _trigger_simplify_autofill(playwright_page)
        # Wait for form to stabilize after autofill
        await playwright_page.evaluate(_JS_WAIT_FOR_STABILITY, FORM_STABILITY_WAIT_MS)
    else:
        logger.warning(
            "Simplify extension NOT detected for job_hash={}", job_hash,
        )

    # Step 4: Upload resume PDF (after Simplify, so it can't overwrite)
    logger.info("Uploading resume for job_hash={}...", job_hash)
    resume_uploaded = await upload_resume(playwright_page, resume_pdf_path)
    if resume_uploaded:
        logger.info("Resume uploaded successfully for job_hash={}", job_hash)
    else:
        logger.warning("Resume upload failed for job_hash={}", job_hash)

    # Step 5: Scan for unresolved fields (rich metadata for future agent)
    unresolved_fields = await scan_unresolved_fields(playwright_page)
    logger.info(
        "Found {} unresolved fields for job_hash={}",
        len(unresolved_fields),
        job_hash,
    )

    # Step 6: Compute confidence score
    confidence_report = await compute_confidence(
        playwright_page,
        resume_uploaded=resume_uploaded,
        simplify_detected=simplify_detected,
        ats_platform=ats_platform,
        original_url=source_url,
    )
    logger.info(
        "Confidence score: {:.4f} (hard_blockers={}) for job_hash={}",
        confidence_report.score,
        confidence_report.has_hard_blockers,
        job_hash,
    )

    # Step 7: Capture artifacts
    await _save_screenshot_safe(playwright_page, screenshot_path)
    await _save_dom_safe(playwright_page, dom_snapshot_path)

    # Save unresolved fields to JSON file
    unresolved_dicts = [f.model_dump() for f in unresolved_fields]
    unresolved_path.write_text(
        json.dumps(unresolved_dicts, indent=2, ensure_ascii=False),
    )

    # Step 8: Determine outcome
    if dry_run:
        outcome = ApplyOutcome.NEEDS_REVIEW
        logger.info(
            "Dry-run mode: skipping submit for job_hash={}", job_hash,
        )
    else:
        # Future: auto-submit when confidence is high and no hard blockers
        outcome = ApplyOutcome.NEEDS_REVIEW

    return ApplyRunResult(
        success=True,
        outcome=outcome,
        resume_pdf_path=str(resume_pdf_path),
        resume_source=None,  # Set by the caller from review verdict
        confidence_score=confidence_report.score,
        confidence_report=confidence_report,
        screenshot_path=str(screenshot_path),
        dom_snapshot_path=str(dom_snapshot_path),
        unresolved_fields=unresolved_fields,
        ats_platform=ats_platform,
        page_url=playwright_page.url,
    )


async def _trigger_simplify_autofill(page: Page) -> None:
    """Click the Simplify autofill button if visible.

    Args:
        page: The Playwright page to interact with.
    """

    try:
        button = page.locator(_SIMPLIFY_BUTTON_SELECTOR).first
        if await button.count() > 0 and await button.is_visible():
            await button.click()
            logger.info("Clicked Simplify autofill button")
        else:
            logger.info(
                "No visible Simplify button found; "
                "extension may auto-trigger",
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error clicking Simplify button: {}", exc)


async def _save_screenshot_safe(page: Page, path: Path) -> None:
    """Capture a full-page screenshot, ignoring errors.

    Args:
        page: The Playwright page to screenshot.
        path: File path to save the screenshot.
    """

    try:
        await page.screenshot(path=str(path), full_page=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to capture screenshot: {}", exc)


async def _save_dom_safe(page: Page, path: Path) -> None:
    """Save the page HTML content, ignoring errors.

    Args:
        page: The Playwright page whose content to save.
        path: File path to save the HTML content.
    """

    try:
        content = await page.content()
        path.write_text(content, encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to save DOM snapshot: {}", exc)


__all__ = [
    "ApplyRunResult",
    "SIMPLIFY_POLL_INTERVAL_MS",
    "SIMPLIFY_POLL_TIMEOUT_MS",
    "apply_to_job",
    "check_chrome_reachable",
]
