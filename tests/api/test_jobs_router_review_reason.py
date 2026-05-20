"""Unit tests for `api.routers.jobs._extract_review_reason`.

Purpose:
    The dashboard branches NO_IMPROVEMENT verdict copy on the structured
    `reason` field pulled out of `review_runs.review_report_json`. That
    helper must degrade gracefully to `None` for every malformed input
    so the UI never crashes on legacy rows or operator-edited payloads.
"""

from __future__ import annotations

import pytest

from api.routers.jobs import _extract_review_reason


@pytest.mark.parametrize(
    "raw_payload",
    [
        pytest.param(None, id="none_value"),
        pytest.param("", id="empty_string"),
        pytest.param("   ", id="whitespace_only"),
        pytest.param("not-json", id="non_json_text"),
        pytest.param("[1, 2]", id="json_array_not_object"),
        pytest.param('{"summary": "x"}', id="missing_reason_key"),
        pytest.param('{"reason": ""}', id="empty_reason_string"),
        pytest.param('{"reason": 42}', id="non_string_reason"),
    ],
)
def test_returns_none_for_malformed_or_missing_review_reason(
    raw_payload: object,
) -> None:
    """Every malformed/missing payload shape degrades to `None`."""

    result = _extract_review_reason(raw_payload)

    assert result is None


def test_returns_reason_string_for_valid_payload() -> None:
    """A well-formed JSON object with a non-empty string `reason` is returned verbatim."""

    raw_payload = '{"reason": "tailor_bailed"}'

    result = _extract_review_reason(raw_payload)

    assert result == "tailor_bailed"


def test_returns_reason_string_when_payload_has_extra_fields() -> None:
    """Surrounding keys (summary, edits_proposed, dropped_edits) are ignored."""

    raw_payload = (
        '{"reason": "all_edits_dropped", "summary": "two hallucinated ids", '
        '"edits_proposed": 2, "edits_applied": 0}'
    )

    result = _extract_review_reason(raw_payload)

    assert result == "all_edits_dropped"
