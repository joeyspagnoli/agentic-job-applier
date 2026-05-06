"""Property-based and fuzz tests for WorkdayFetcher pure helpers.

Purpose:
    Cover invariants the testing handoff calls out under "Specific properties
    for property-based tests" — the parser tenant round-trip, total absence of
    angle brackets in cleaned descriptions, and crash-free behavior over
    arbitrary string input. Hypothesis is the only tool in this file; no
    network access is performed.
"""

from __future__ import annotations

import re

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from src.fetchers.workday_fetcher import WorkdayFetcher


PROPERTY_EXAMPLES = 200
"""Hypothesis run size for the parser/cleaner property tests."""

FUZZ_EXAMPLES = 500
"""Hypothesis run size for the arbitrary-string fuzz tests."""

TENANT_PATTERN = r"[a-z][a-z0-9]{2,15}"
"""Regex for a Workday tenant subdomain label."""

WD_HOST_PATTERN = r"wd[0-9]{1,3}"
"""Regex for the regional ``wdN`` host prefix Workday uses."""

SITE_PATTERN = r"[A-Za-z][A-Za-z0-9]{2,30}"
"""Regex for the trailing site path segment, matching live Workday boards."""



@given(
    tenant=st.from_regex(TENANT_PATTERN, fullmatch=True),
    wd_host=st.from_regex(WD_HOST_PATTERN, fullmatch=True),
    site=st.from_regex(SITE_PATTERN, fullmatch=True),
    locale=st.sampled_from(["", "/en", "/en-US", "/fr-FR", "/de", "/zh-CN"]),
)
@settings(max_examples=PROPERTY_EXAMPLES)
def test_parse_board_url_round_trips_tenant_and_site_for_well_formed_inputs(
    tenant: str, wd_host: str, site: str, locale: str
) -> None:
    """Verify the parser preserves tenant and site for well-formed Workday URLs.

    Purpose:
        Confirm the contract from the handoff: for any valid Workday URL the
        returned tenant equals the first subdomain label and the site equals
        the trailing non-locale path segment.
    Args:
        tenant: Generated tenant subdomain label.
        wd_host: Generated regional host label (e.g., ``wd5``).
        site: Generated trailing site path segment.
        locale: Optional locale segment between the host and the site.
    Output:
        Returns ``None``; passes when every generated URL round-trips cleanly.
    """

    url = f"https://{tenant}.{wd_host}.myworkdayjobs.com{locale}/{site}"

    origin, parsed_tenant, parsed_site = WorkdayFetcher._parse_board_url(url)

    assert parsed_tenant == tenant
    assert parsed_site == site
    assert origin == f"https://{tenant}.{wd_host}.myworkdayjobs.com"


@given(st.text(max_size=200))
@settings(max_examples=FUZZ_EXAMPLES, suppress_health_check=[HealthCheck.filter_too_much])
def test_parse_board_url_either_returns_three_strings_or_raises_value_error(
    arbitrary_input: str,
) -> None:
    """Verify the parser never produces a non-string or unexpected exception.

    Purpose:
        Onboarding configs are user-edited YAML; the parser must reject bad
        URLs cleanly via ``ValueError`` or return a fully-typed three-tuple
        with no other failure modes.
    Args:
        arbitrary_input: Random string drawn from the unbounded text strategy.
    Output:
        Returns ``None``; passes when every input either raises ``ValueError``
        or yields ``(str, str, str)``.
    """

    try:
        result = WorkdayFetcher._parse_board_url(arbitrary_input)
    except ValueError:
        return

    assert isinstance(result, tuple)
    assert len(result) == 3
    origin, tenant, site = result
    assert isinstance(origin, str)
    assert isinstance(tenant, str)
    assert isinstance(site, str)


@given(st.text(max_size=500))
@settings(max_examples=FUZZ_EXAMPLES)
def test_clean_html_never_emits_angle_brackets_for_any_input(
    raw_html: str,
) -> None:
    """Verify cleaned output never contains ``<`` or ``>`` for arbitrary input.

    Purpose:
        Pin the handoff property "for any HTML input, ``_clean_html(html)``
        contains no ``<`` or ``>`` characters" so unbalanced brackets cannot
        leak into hashed descriptions or downstream prompt context.
    Args:
        raw_html: Random text fed through the cleaner.
    Output:
        Returns ``None``; passes when no angle bracket remains in the output.
    """

    cleaned = WorkdayFetcher._clean_html(raw_html)

    assert "<" not in cleaned
    assert ">" not in cleaned


@given(st.text(max_size=500))
@settings(max_examples=FUZZ_EXAMPLES)
def test_clean_html_collapses_whitespace_runs_into_single_spaces(
    raw_html: str,
) -> None:
    """Verify cleaned output never contains consecutive whitespace runs.

    Purpose:
        ``_clean_html`` promises to collapse whitespace; multi-space runs would
        bloat description hashes and prompt-context tokens downstream.
    Args:
        raw_html: Random text fed through the cleaner.
    Output:
        Returns ``None``; passes when the cleaned text has no double spaces and
        no leading or trailing whitespace.
    """

    cleaned = WorkdayFetcher._clean_html(raw_html)

    assert "  " not in cleaned
    assert cleaned == cleaned.strip()
    assert re.search(r"\s\s", cleaned) is None


@given(st.text(max_size=500))
@settings(max_examples=FUZZ_EXAMPLES)
def test_is_blocked_response_returns_bool_for_arbitrary_body(
    arbitrary_body: str,
) -> None:
    """Verify the gate detector always returns a bool, never raises, for any body.

    Purpose:
        The block detector runs on every non-2xx and non-JSON 2xx response; it
        must not raise on a hostile body or return a non-bool sentinel.
    Args:
        arbitrary_body: Random string fed in as the body sample.
    Output:
        Returns ``None``; passes when the helper produces a bool result.
    """

    result = WorkdayFetcher._is_blocked_response(403, arbitrary_body)

    assert isinstance(result, bool)
