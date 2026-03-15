"""Pytest marker and CLI flag registration for optional live agent tests.

Purpose:
    Keep live model tests opt-in so deterministic suites remain fast and CI
    safe while still allowing explicit end-to-end validation when requested.
"""

from __future__ import annotations

import pytest

LIVE_E2E_MARKER = "live_agent_e2e"
LIVE_E2E_FLAG = "--run-live-agent-e2e"


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register custom CLI flags used by this repository's test suite.

    Purpose:
        Add an explicit opt-in switch for tests that call a live model API.
    Args:
        parser: Pytest parser used to register command-line options.
    Output:
        Returns `None` after registering the custom CLI option.
    """

    parser.addoption(
        LIVE_E2E_FLAG,
        action="store_true",
        default=False,
        help="Run live model end-to-end tests marked with live_agent_e2e.",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Register repository-specific markers so pytest lists them cleanly.

    Purpose:
        Avoid unknown-marker warnings and document optional marker semantics in
        `pytest --markers` output.
    Args:
        config: Active pytest config object for this test session.
    Output:
        Returns `None` after marker registration.
    """

    config.addinivalue_line(
        "markers",
        f"{LIVE_E2E_MARKER}: marks tests that require live model API calls",
    )


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """Skip live model tests unless the explicit opt-in flag is provided.

    Purpose:
        Keep default test runs deterministic and secret-free while still
        supporting intentional live-model verification.
    Args:
        config: Active pytest config object for this test session.
        items: Collected pytest items for this run.
    Output:
        Returns `None` after applying skip markers as needed.
    """

    if config.getoption(LIVE_E2E_FLAG):
        return

    skip_reason = f"requires {LIVE_E2E_FLAG}"
    skip_marker = pytest.mark.skip(reason=skip_reason)
    for item in items:
        if LIVE_E2E_MARKER in item.keywords:
            item.add_marker(skip_marker)
