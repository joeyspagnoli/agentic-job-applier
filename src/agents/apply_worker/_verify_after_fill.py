"""Post-Simplify verification helper — telemetry only, no control flow.

Reads 2-3 known input values per ATS after Simplify autofill settles so
`finisher_diagnostics_json.simplify_no_op` can be set when Simplify
silently did nothing. V1 is observational; the finisher behaves
identically regardless.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from src.agents.apply_worker.schemas import ATSPlatform

VERIFY_SELECTORS_BY_ATS: dict[ATSPlatform, list[str]] = {
    ATSPlatform.GREENHOUSE: ["#first_name", "#last_name", "#email"],
    ATSPlatform.LEVER: ["input[name=name]", "input[name=email]"],
    ATSPlatform.ASHBY: ["#_systemfield_name", "#_systemfield_email"],
}


async def verify_after_fill(page: Any, ats: ATSPlatform) -> dict[str, Any]:
    """Read known input values after Simplify settles and detect no-op.

    Purpose:
        Telemetry-only check so the finisher_diagnostics_json payload can
        flag silent Simplify failures. Returns a dict the caller can merge
        into the diagnostics blob.
    Args:
        page: Playwright Page-like object with async `locator(...).input_value()`.
        ats: Detected ATS platform.
    Returns:
        Dict with keys: `selectors_checked: list[str]`,
        `values_seen: dict[str, str]`, `simplify_no_op: bool`.
    """

    selectors = VERIFY_SELECTORS_BY_ATS.get(ats, [])
    values: dict[str, str] = {}
    for selector in selectors:
        try:
            value = await page.locator(selector).first.input_value(timeout=1500)
        except Exception as exc:  # noqa: BLE001
            logger.debug("verify_after_fill: {} not readable ({})", selector, exc)
            value = ""
        values[selector] = (value or "").strip()
    all_empty = bool(values) and all(v == "" for v in values.values())
    return {
        "selectors_checked": selectors,
        "values_seen": values,
        "simplify_no_op": all_empty,
    }


__all__ = [
    "VERIFY_SELECTORS_BY_ATS",
    "verify_after_fill",
]
