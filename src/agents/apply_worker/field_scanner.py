"""Scan application forms for unresolved fields and capture rich metadata.

Purpose:
    Extract structured information about every form field that remains
    empty or invalid after Simplify autofill.  The captured metadata is
    detailed enough for a future agent repair pass to propose values
    without re-opening the browser.
"""

from __future__ import annotations

from loguru import logger
from playwright.async_api import Frame
from playwright.async_api import Page

from src.agents.apply_worker.schemas import UnresolvedField

# JavaScript executed in the browser to scan all form fields on the page.
# Returns a JSON-serializable array of field descriptors.
_FIELD_SCAN_JS = """
() => {
    /**
     * Scan every input, select, and textarea in the document and return
     * a descriptor array.  Only fields that are empty or have a visible
     * validation error are included.
     */
    function getLabelText(el) {
        // 1. Explicit <label for="...">
        if (el.id) {
            const label = document.querySelector('label[for="' + el.id + '"]');
            if (label) return label.textContent.trim();
        }
        // 2. aria-label
        if (el.getAttribute('aria-label')) {
            return el.getAttribute('aria-label').trim();
        }
        // 3. Enclosing <label>
        const parent = el.closest('label');
        if (parent) return parent.textContent.trim().substring(0, 200);
        // 4. Placeholder
        if (el.placeholder) return el.placeholder.trim();
        // 5. aria-labelledby
        const labelledBy = el.getAttribute('aria-labelledby');
        if (labelledBy) {
            const ref = document.getElementById(labelledBy);
            if (ref) return ref.textContent.trim();
        }
        return null;
    }

    function getValidationError(el) {
        // Check aria-describedby for error text
        const describedBy = el.getAttribute('aria-describedby');
        if (describedBy) {
            const ref = document.getElementById(describedBy);
            if (ref && ref.textContent.trim()) return ref.textContent.trim();
        }
        // Check adjacent .error or [role=alert] siblings
        const next = el.nextElementSibling;
        if (next) {
            if (next.classList.contains('error') ||
                next.getAttribute('role') === 'alert') {
                return next.textContent.trim();
            }
        }
        // Check parent for error class children
        const parentEl = el.parentElement;
        if (parentEl) {
            const errEl = parentEl.querySelector('.error, [role="alert"]');
            if (errEl && errEl.textContent.trim()) {
                return errEl.textContent.trim();
            }
        }
        return null;
    }

    function getOptions(el) {
        if (el.tagName === 'SELECT') {
            return Array.from(el.options)
                .filter(o => o.value !== '')
                .map(o => o.textContent.trim());
        }
        // Radio/checkbox groups
        if (el.type === 'radio' || el.type === 'checkbox') {
            const name = el.name;
            if (!name) return null;
            const group = document.querySelectorAll(
                'input[name="' + name + '"]'
            );
            const labels = [];
            group.forEach(inp => {
                const lbl = getLabelText(inp);
                if (lbl) labels.push(lbl);
            });
            return labels.length > 0 ? labels : null;
        }
        return null;
    }

    function isFieldRequired(el) {
        if (el.required || el.getAttribute('aria-required') === 'true') {
            return true;
        }
        // Check if label contains an asterisk
        const label = getLabelText(el);
        if (label && label.includes('*')) return true;
        return false;
    }

    function getUniqueSelector(el) {
        if (el.id) return el.tagName.toLowerCase() + '#' + el.id;
        if (el.name) {
            return el.tagName.toLowerCase() + '[name="' + el.name + '"]';
        }
        // Build a positional selector as last resort
        const parent = el.parentElement;
        if (!parent) return el.tagName.toLowerCase();
        const siblings = Array.from(
            parent.querySelectorAll(':scope > ' + el.tagName.toLowerCase())
        );
        const idx = siblings.indexOf(el);
        return el.tagName.toLowerCase() + ':nth-child(' + (idx + 1) + ')';
    }

    function getFormSelector(el) {
        const form = el.closest('form');
        if (!form) return null;
        if (form.id) return 'form#' + form.id;
        if (form.name) return 'form[name="' + form.name + '"]';
        return 'form';
    }

    const fields = [];
    const selectors = 'input, select, textarea';
    const elements = document.querySelectorAll(selectors);

    elements.forEach(el => {
        // Skip hidden and submit/button types
        if (el.type === 'hidden' || el.type === 'submit' ||
            el.type === 'button' || el.type === 'image') {
            return;
        }
        // Skip invisible elements
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden') {
            return;
        }

        const value = el.value || '';
        const isRequired = isFieldRequired(el);
        const validationError = getValidationError(el);
        const isEmpty = value.trim() === '';

        // Only capture fields that are empty or have validation errors
        if (!isEmpty && !validationError) return;

        fields.push({
            field_id: el.id || null,
            label: getLabelText(el),
            field_type: el.type || el.tagName.toLowerCase(),
            is_required: isRequired,
            current_value: value,
            validation_error: validationError,
            options: getOptions(el),
            selector: getUniqueSelector(el),
            parent_form_selector: getFormSelector(el),
            placeholder: el.placeholder || null,
        });
    });

    return fields;
}
"""


async def scan_unresolved_fields(page: Page) -> list[UnresolvedField]:
    """Scan the page for form fields that are empty or have validation errors.

    Executes JavaScript in the main frame and all child iframes to find
    unresolved fields.  Each field is captured with enough metadata for a
    future agent to propose fill values without browser access.

    Args:
        page: The Playwright page to scan.

    Returns:
        A list of UnresolvedField models, one per empty or invalid field.
    """

    all_fields: list[UnresolvedField] = []

    # Scan the main frame
    raw_fields = await page.evaluate(_FIELD_SCAN_JS)
    all_fields.extend(_parse_raw_fields(raw_fields))

    # Scan child iframes
    for frame in page.frames:
        if frame == page.main_frame:
            continue
        try:
            iframe_fields = await frame.evaluate(_FIELD_SCAN_JS)
            all_fields.extend(_parse_raw_fields(iframe_fields))
        except Exception as exc:  # noqa: BLE001
            # Iframes may be cross-origin or detached; log and skip gracefully.
            logger.warning(
                "Skipping iframe unresolved-field scan due to evaluation error: "
                "frame_url={} error={}",
                frame.url,
                exc,
            )
            continue

    return all_fields


async def scan_unresolved_fields_in_frame(
    frame: Frame,
) -> list[UnresolvedField]:
    """Scan a single frame for unresolved form fields.

    Args:
        frame: The Playwright frame to scan.

    Returns:
        A list of UnresolvedField models found in this frame.
    """

    raw_fields = await frame.evaluate(_FIELD_SCAN_JS)
    return _parse_raw_fields(raw_fields)


def _parse_raw_fields(
    raw_fields: list[dict[str, object]],
) -> list[UnresolvedField]:
    """Convert raw JavaScript field descriptors to Pydantic models.

    Args:
        raw_fields: Array of plain dicts returned by the JS scan function.

    Returns:
        A list of validated UnresolvedField instances.
    """

    parsed: list[UnresolvedField] = []
    for raw in raw_fields:
        parsed.append(
            UnresolvedField(
                field_id=raw.get("field_id"),  # type: ignore[arg-type]
                label=raw.get("label"),  # type: ignore[arg-type]
                field_type=str(raw.get("field_type", "text")),
                is_required=bool(raw.get("is_required", False)),
                current_value=str(raw.get("current_value", "")),
                validation_error=raw.get("validation_error"),  # type: ignore[arg-type]
                options=raw.get("options"),  # type: ignore[arg-type]
                selector=str(raw.get("selector", "")),
                parent_form_selector=raw.get("parent_form_selector"),  # type: ignore[arg-type]
                placeholder=raw.get("placeholder"),  # type: ignore[arg-type]
            )
        )
    return parsed


__all__ = [
    "scan_unresolved_fields",
    "scan_unresolved_fields_in_frame",
]
