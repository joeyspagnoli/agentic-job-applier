"""Property-based and fuzz tests for iCIMS fetcher pure functions.

Covers ``_strip`` and ``_resolve_base_url`` with Hypothesis-generated inputs,
and fuzzes ``_parse_page`` against arbitrary HTML to confirm it never raises.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from src.fetchers.icims_fetcher import ICIMSFetcher, _resolve_base_url, _strip


_FETCHER = ICIMSFetcher(
    company_name="Dollar General",
    icims_subdomain="jobs-dollargeneral.icims.com",
)


# ---------------------------------------------------------------------------
# _strip — property tests
# ---------------------------------------------------------------------------


@given(st.text())
@settings(max_examples=200)
def test_strip_always_returns_a_str(text: str) -> None:
    """Property: ``_strip`` always returns ``str`` for any input."""

    result = _strip(text)

    assert isinstance(result, str)


@given(st.text())
@settings(max_examples=200)
def test_strip_output_has_no_leading_or_trailing_whitespace(text: str) -> None:
    """Property: ``_strip`` output is always stripped of surrounding whitespace."""

    result = _strip(text)

    assert result == result.strip()


@given(st.text())
@settings(max_examples=200)
def test_strip_output_has_no_consecutive_spaces(text: str) -> None:
    """Property: ``_strip`` collapses all internal whitespace runs to single spaces."""

    result = _strip(text)

    assert "  " not in result


@given(st.text(alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z"))))
@settings(max_examples=200)
def test_strip_output_contains_no_html_open_tags_from_well_formed_input(
    text: str,
) -> None:
    """Property: well-formed HTML tags (with closing ``>``) are fully stripped."""

    wrapped = f"<span>{text}</span>"

    result = _strip(wrapped)

    assert "<span>" not in result
    assert "</span>" not in result


# ---------------------------------------------------------------------------
# _strip — fuzz tests (arbitrary external HTML payloads)
# ---------------------------------------------------------------------------


@given(st.text())
@settings(max_examples=1000)
def test_strip_never_raises_on_arbitrary_text(text: str) -> None:
    """Fuzz: ``_strip`` must never raise an unhandled exception on any input."""

    result = _strip(text)

    assert isinstance(result, str)


@given(st.binary())
@settings(max_examples=1000)
def test_strip_never_raises_on_arbitrary_bytes_decoded_as_latin1(data: bytes) -> None:
    """Fuzz: ``_strip`` survives arbitrary byte sequences decoded as latin-1."""

    text = data.decode("latin-1", errors="replace")

    result = _strip(text)

    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# _resolve_base_url — property tests
# ---------------------------------------------------------------------------


@given(
    st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N"),
            whitelist_characters="-.",
        ),
        min_size=1,
    )
)
@settings(max_examples=200)
def test_resolve_base_url_always_starts_with_https_for_bare_subdomain(
    subdomain: str,
) -> None:
    """Property: bare subdomains (no http prefix) always get ``https://`` prepended."""

    result = _resolve_base_url(subdomain)

    assert result.startswith("https://")


@given(
    st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789-.",
        min_size=1,
    )
)
@settings(max_examples=200)
def test_resolve_base_url_never_ends_with_trailing_slash_for_realistic_subdomain(
    subdomain: str,
) -> None:
    """Property: realistic subdomain characters never produce a trailing slash."""

    result = _resolve_base_url(subdomain)

    assert not result.endswith("/")


@given(st.text())
@settings(max_examples=200)
def test_resolve_base_url_always_returns_a_str(subdomain: str) -> None:
    """Property: ``_resolve_base_url`` always returns ``str`` for any input."""

    result = _resolve_base_url(subdomain)

    assert isinstance(result, str)


@given(
    st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N"),
            whitelist_characters="-.",
        ),
        min_size=1,
    )
)
@settings(max_examples=200)
def test_resolve_base_url_idempotent_on_already_resolved_url(
    subdomain: str,
) -> None:
    """Property: resolving an already-resolved URL produces the same result."""

    once = _resolve_base_url(subdomain)
    twice = _resolve_base_url(once)

    assert once == twice


# ---------------------------------------------------------------------------
# _parse_page — fuzz tests (arbitrary external HTML payloads)
# ---------------------------------------------------------------------------


@given(st.text())
@settings(max_examples=1000)
def test_parse_page_never_raises_on_arbitrary_html_text(html_text: str) -> None:
    """Fuzz: ``_parse_page`` must never raise on any HTML-shaped or arbitrary string."""

    result = _FETCHER._parse_page(html_text)

    assert isinstance(result, list)


@given(st.binary())
@settings(max_examples=1000)
def test_parse_page_never_raises_on_bytes_decoded_as_latin1(data: bytes) -> None:
    """Fuzz: ``_parse_page`` survives arbitrary byte payloads decoded as latin-1."""

    html_text = data.decode("latin-1", errors="replace")

    result = _FETCHER._parse_page(html_text)

    assert isinstance(result, list)
