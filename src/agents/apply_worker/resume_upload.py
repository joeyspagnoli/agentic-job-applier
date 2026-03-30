"""Resume PDF upload to ATS application forms via Playwright.

Purpose:
    Detect file-upload fields in the application page and upload the
    tailored (or base) resume PDF.  Handles visible file inputs, inputs
    hidden inside iframes, and programmatic file-chooser dialogs.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from loguru import logger
from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

# Selectors tried in priority order when looking for a file upload input.
_FILE_INPUT_SELECTORS: list[str] = [
    'input[type="file"]',
    'input[accept*="pdf"]',
    'input[accept*=".pdf"]',
    'input[accept*="application/pdf"]',
]

# Maximum time to wait for a file-chooser dialog triggered by a button click.
_FILE_CHOOSER_TIMEOUT_MS = 5_000

# Keywords in button/link text that suggest a resume upload trigger.
_UPLOAD_BUTTON_KEYWORDS: list[str] = [
    "upload",
    "resume",
    "cv",
    "attach",
    "choose file",
    "select file",
]


async def upload_resume(page: Page, pdf_path: Path) -> bool:
    """Upload a resume PDF to the application form on the page.

    Tries three strategies in order:
    1. Direct file-input elements visible in the main frame.
    2. File-input elements inside child iframes.
    3. Programmatic file-chooser triggered by clicking an upload button.

    Args:
        page: The Playwright page containing the application form.
        pdf_path: Absolute path to the resume PDF file to upload.

    Returns:
        True if the resume was successfully set on a file input, False
        if no suitable upload target could be found.
    """

    if not pdf_path.exists():
        logger.error("Resume PDF not found at {}", pdf_path)
        return False

    pdf_str = str(pdf_path)

    # Strategy 1: visible file inputs in main frame
    if await _try_direct_file_input(page, pdf_str):
        return True

    # Strategy 2: file inputs inside iframes
    if await _try_iframe_file_inputs(page, pdf_str):
        return True

    # Strategy 3: button click that triggers a file-chooser dialog
    if await _try_file_chooser_button(page, pdf_str):
        return True

    logger.warning("No resume upload target found on page {}", page.url)
    return False


async def _try_direct_file_input(page: object, pdf_path: str) -> bool:
    """Attempt upload via a visible file input in the main frame.

    Args:
        page: The Playwright page to search.
        pdf_path: String path to the resume PDF.

    Returns:
        True if a file input was found and the file was set.
    """

    page_handle = cast(Page, page)
    for selector in _FILE_INPUT_SELECTORS:
        try:
            locator = page_handle.locator(selector).first
            if await locator.count() > 0:
                await locator.set_input_files(pdf_path)
                logger.info("Uploaded resume via direct file input: {}", selector)
                return True
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed direct file-input upload strategy: selector={} error={}",
                selector,
                exc,
            )
            continue
    return False


async def _try_iframe_file_inputs(page: Page, pdf_path: str) -> bool:
    """Search child iframes for file inputs and attempt upload.

    Args:
        page: The Playwright page whose frames to search.
        pdf_path: String path to the resume PDF.

    Returns:
        True if a file input was found in an iframe and the file was set.
    """

    for frame in page.frames:
        if frame == page.main_frame:
            continue
        for selector in _FILE_INPUT_SELECTORS:
            try:
                locator = frame.locator(selector).first
                if await locator.count() > 0:
                    await locator.set_input_files(pdf_path)
                    logger.info(
                        "Uploaded resume via iframe file input: {} in {}",
                        selector,
                        frame.url,
                    )
                    return True
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed iframe file-input upload strategy: frame_url={} "
                    "selector={} error={}",
                    frame.url,
                    selector,
                    exc,
                )
                continue
    return False


async def _try_file_chooser_button(page: Page, pdf_path: str) -> bool:
    """Click upload-like buttons and intercept the file-chooser dialog.

    Looks for buttons or links whose text matches common upload keywords,
    then listens for the Playwright FileChooser event.

    Args:
        page: The Playwright page to search.
        pdf_path: String path to the resume PDF.

    Returns:
        True if a file-chooser dialog was triggered and the file was set.
    """

    for keyword in _UPLOAD_BUTTON_KEYWORDS:
        # Try button and anchor elements with matching text
        for tag in ("button", "a", "span", "div"):
            selector = f"{tag}:has-text('{keyword}')"
            try:
                locator = page.locator(selector).first
                if await locator.count() == 0:
                    continue
                if not await locator.is_visible():
                    continue

                async with page.expect_file_chooser(
                    timeout=_FILE_CHOOSER_TIMEOUT_MS,
                ) as fc_info:
                    await locator.click()

                file_chooser = await fc_info.value
                await file_chooser.set_files(pdf_path)
                logger.info(
                    "Uploaded resume via file-chooser button: {} '{}'",
                    tag,
                    keyword,
                )
                return True
            except PlaywrightTimeoutError:
                # Click did not trigger a file dialog; try next button.
                continue
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed file-chooser upload strategy: selector={} error={}",
                    selector,
                    exc,
                )
                continue

    return False


__all__ = [
    "logger",
    "_try_direct_file_input",
    "upload_resume",
]
