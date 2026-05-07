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
from src.agents.apply_worker.schemas import SIMPLIFY_POLL_INTERVAL_MS
from src.agents.apply_worker.schemas import SIMPLIFY_POLL_TIMEOUT_MS

# Simplify Copilot v2.4.x injects a `<div class="simplify-jobs-shadow-root">`
# host with `attachShadow({mode:"open"})`. Buttons inside the shadow root use
# stable aria-labels (extracted from contentScript.bundle.js by static
# analysis on 2026-05-07): "Autofill", "Autofill all fields with AI", "Fill",
# "Continue filling", "Submit Application" (DO NOT CLICK), "Tailor Resume",
# etc. Verified behavior: full UI takes ~15s to render after page navigation
# completes.

# Aria-labels we WILL click on, in priority order. None of these submit.
_SIMPLIFY_AUTOFILL_LABELS = (
    "Autofill",
    "Autofill all fields with AI",
    "Fill",
    "Continue filling",
)

# Aria-labels we MUST NEVER click. Defense in depth — the button click helper
# refuses to click anything matching this list even if some future code path
# accidentally adds one.
_SIMPLIFY_FORBIDDEN_LABELS = (
    "Submit Application",
    "Submit",
)

# JavaScript that polls for the Simplify shadow roots AND searches all of
# them for the autofill button. Simplify v2.4.x creates MULTIPLE elements
# with `class="simplify-jobs-shadow-root"`: typically one for the inline
# resume score banner (small, only "Resume score banner" aria-label) and
# one for the side panel which holds the Autofill / Tailor Resume / Save
# Job Instead controls. We must querySelectorAll and walk every shadowRoot.
_JS_DETECT_SIMPLIFY = """
({ intervalMs, timeoutMs }) => new Promise(resolve => {
    const normalizedIntervalMs = Number(intervalMs) || 500;
    const normalizedTimeoutMs = Number(timeoutMs) || 30000;
    const autofillLabels = %(autofill_labels)s;
    const start = Date.now();
    function check() {
        const hosts = document.querySelectorAll('div.simplify-jobs-shadow-root');
        for (const host of hosts) {
            if (!host.shadowRoot) continue;
            for (const label of autofillLabels) {
                const btn = host.shadowRoot.querySelector(
                    '[aria-label="' + label + '"]'
                );
                if (btn) { resolve(true); return; }
            }
        }
        if (Date.now() - start > normalizedTimeoutMs) {
            resolve(false);
            return;
        }
        setTimeout(check, normalizedIntervalMs);
    }
    check();
})
""" % {"autofill_labels": list(_SIMPLIFY_AUTOFILL_LABELS)}

# JavaScript that walks every Simplify shadow root, finds the first visible
# autofill button (in label-priority order), and clicks it. Defense in
# depth: skips any element whose aria-label matches the forbidden list
# (Submit / Submit Application). Returns a status string for telemetry.
_JS_CLICK_SIMPLIFY_AUTOFILL = """
({ autofillLabels, forbiddenLabels }) => {
    const hosts = document.querySelectorAll('div.simplify-jobs-shadow-root');
    if (!hosts.length) return 'NO_SHADOW_HOST';
    function isForbidden(label) {
        if (!label) return false;
        return forbiddenLabels.some(f => label.indexOf(f) !== -1);
    }
    let anyShadow = false;
    for (const label of autofillLabels) {
        if (isForbidden(label)) continue;
        for (const host of hosts) {
            if (!host.shadowRoot) continue;
            anyShadow = true;
            const btn = host.shadowRoot.querySelector('[aria-label="' + label + '"]');
            if (!btn) continue;
            const rect = btn.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) continue;
            btn.click();
            return 'CLICKED:' + label;
        }
    }
    if (!anyShadow) return 'SHADOW_HOST_BUT_NO_ROOT';
    return 'NO_AUTOFILL_BUTTON';
}
"""


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

    # Step 1: Ensure we're on the application page. Skip goto if the page is
    # already at the target URL — re-navigating mid-flow disrupts Chrome
    # extensions (notably Simplify Copilot, whose content script will not
    # re-render its side panel after a programmatic navigation).
    current_url = playwright_page.url
    needs_navigate = source_url not in current_url and current_url not in source_url
    logger.info(
        "Apply flow start for job_hash={} source_url={} current_url={} "
        "needs_navigate={}",
        job_hash, source_url, current_url, needs_navigate,
    )
    try:
        if needs_navigate:
            await playwright_page.goto(
                source_url, timeout=DEFAULT_PAGE_LOAD_TIMEOUT_MS
            )
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

    # Step 4: Upload OUR tailored resume PDF BEFORE triggering Simplify.
    # Simplify's Autofill click typically navigates the tab to a preview of
    # the resume Simplify has on file (storage.googleapis.com/simplify-resumes/...).
    # Once that happens, the form is no longer visible to upload to. So we
    # always upload our tailored PDF to the form's file input first.
    logger.info("Uploading resume for job_hash={}...", job_hash)
    try:
        resume_uploaded = await upload_resume(playwright_page, resume_pdf_path)
        if resume_uploaded:
            logger.info("Resume uploaded successfully for job_hash={}", job_hash)
        else:
            logger.warning("Resume upload failed for job_hash={}", job_hash)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Resume upload step failed for job_hash={}: {}",
            job_hash,
            exc,
        )
        resume_uploaded = False

    # Step 5: Trigger Simplify Autofill AFTER our resume is in place. This
    # may navigate the tab away from the form (post-click_capture observed
    # storage.googleapis.com URLs), but our upload has already happened.
    if simplify_detected:
        logger.info("Simplify extension detected for job_hash={}", job_hash)
        autofill_click_status = await _trigger_simplify_autofill(playwright_page)
        logger.info(
            "Simplify autofill click status={} for job_hash={}",
            autofill_click_status,
            job_hash,
        )
        # Fixed sleep instead of wait_for_load_state("networkidle"): the
        # latter can hang indefinitely on pages with chatty extensions, and
        # the click may navigate the tab anyway.
        import asyncio

        await asyncio.sleep(8)
    else:
        logger.warning(
            "Simplify extension NOT detected for job_hash={}", job_hash,
        )

    # Step 5: Scan for unresolved fields (rich metadata for future agent)
    try:
        unresolved_fields = await scan_unresolved_fields(playwright_page)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Field scan failed for job_hash={}: {}", job_hash, exc,
        )
        unresolved_fields = []
    logger.info(
        "Found {} unresolved fields for job_hash={}",
        len(unresolved_fields),
        job_hash,
    )

    # Step 6: Compute confidence score (best-effort)
    try:
        confidence_report = await compute_confidence(
            playwright_page,
            resume_uploaded=resume_uploaded,
            simplify_detected=simplify_detected,
            ats_platform=ats_platform,
            original_url=source_url,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Confidence computation failed for job_hash={}: {}", job_hash, exc,
        )
        from src.agents.apply_worker.schemas import ConfidenceReport

        confidence_report = ConfidenceReport(
            score=0.0,
            checks=[],
            has_hard_blockers=True,
            resume_uploaded=resume_uploaded,
            simplify_autofill_detected=simplify_detected,
            unresolved_required_count=0,
            unresolved_optional_count=0,
            ats_platform=ats_platform,
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


async def _trigger_simplify_autofill(page: Page) -> str:
    """Pierce Simplify's shadow root and click the Autofill button.

    Purpose:
        Find an Autofill-style aria-label inside the open shadow root that
        Simplify Copilot v2.4.x injects, and click it. Defends against
        accidental Submit clicks via a forbidden-label list.
    Args:
        page: Playwright page already in the right context.
    Output:
        Status string for telemetry: e.g. "CLICKED:Autofill",
        "NO_SHADOW_HOST", "NO_AUTOFILL_BUTTON".
    """

    try:
        status: str = await page.evaluate(
            _JS_CLICK_SIMPLIFY_AUTOFILL,
            {
                "autofillLabels": list(_SIMPLIFY_AUTOFILL_LABELS),
                "forbiddenLabels": list(_SIMPLIFY_FORBIDDEN_LABELS),
            },
        )
        logger.info("Simplify autofill click status: {}", status)
        return status
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error clicking Simplify autofill button: {}", exc)
        return f"EXCEPTION:{exc}"


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
