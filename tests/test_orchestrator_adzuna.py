"""Cover the Adzuna orchestrator entry point's gating and fan-out semantics.

Purpose:
    Lock in the contract from issue #9: Adzuna stays silent when env keys
    or the YAML toggle are missing, profile defaults beat block-configured
    search terms, an empty location list collapses to a single sentinel
    crawl, and crawl-history rows are written for every search variant.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

import main as discovery_main
from src.database.db_manager import DatabaseManager
from src.utils.deduplicator import Deduplicator


# Env vars the orchestrator reads to decide whether Adzuna is configured.
ADZUNA_APP_ID_ENV = "ADZUNA_APP_ID"
ADZUNA_APP_KEY_ENV = "ADZUNA_APP_KEY"


class _StubAdzunaFetcher:
    """Deterministic stand-in for ``AdzunaFetcher`` used by orchestrator tests.

    Purpose:
        Capture every constructor call so happy-path tests can assert on
        ``search_term × location`` fan-out without exercising the real HTTP
        client.
    """

    init_calls: list[dict[str, Any]] = []

    def __init__(self, **kwargs: Any) -> None:
        """Record constructor kwargs for later assertion."""

        type(self).init_calls.append(kwargs)
        self._kwargs = kwargs

    async def __aenter__(self) -> "_StubAdzunaFetcher":
        """Return the stub for ``async with`` use."""

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """No-op cleanup for the stub fetcher."""

    async def fetch_jobs(self) -> list[object]:
        """Return an empty list so the success-accounting path runs cleanly."""

        return []


@pytest.fixture(autouse=True)
def reset_stub_calls() -> None:
    """Clear stub fetcher state between tests so each one starts isolated."""

    _StubAdzunaFetcher.init_calls = []


async def _fast_sleep(_: float) -> None:
    """Replace inter-crawl sleep with a no-op for fast deterministic tests."""


# ---------------------------------------------------------------------------
# Skip-without-side-effects paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disabled_block_returns_zero_and_skips_crawl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify a disabled Adzuna block returns ``(0, 0, 0, 0)`` and starts no crawls.

    Purpose:
        Operators rely on ``enabled: false`` to keep the source dormant
        without losing the rest of the YAML config.
    """

    monkeypatch.setenv(ADZUNA_APP_ID_ENV, "id-123")
    monkeypatch.setenv(ADZUNA_APP_KEY_ENV, "key-123")
    monkeypatch.setattr(discovery_main, "AdzunaFetcher", _StubAdzunaFetcher)

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            deduplicator = Deduplicator(db)

            counters = await discovery_main.fetch_adzuna_jobs(
                {"enabled": False, "search_terms": ["x"]},
                db,
                deduplicator,
            )

    assert counters == (0, 0, 0, 0)
    assert _StubAdzunaFetcher.init_calls == []


@pytest.mark.asyncio
async def test_missing_env_keys_return_zero_even_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify Adzuna is skipped when env credentials are missing.

    Purpose:
        Without API keys, the fetcher cannot succeed; the orchestrator must
        skip silently instead of writing a FAILED crawl row.
    """

    monkeypatch.delenv(ADZUNA_APP_ID_ENV, raising=False)
    monkeypatch.delenv(ADZUNA_APP_KEY_ENV, raising=False)
    monkeypatch.setattr(discovery_main, "AdzunaFetcher", _StubAdzunaFetcher)

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            deduplicator = Deduplicator(db)

            counters = await discovery_main.fetch_adzuna_jobs(
                {"enabled": True, "search_terms": ["x"], "locations": ["NYC"]},
                db,
                deduplicator,
            )

    assert counters == (0, 0, 0, 0)
    assert _StubAdzunaFetcher.init_calls == []


@pytest.mark.asyncio
async def test_only_app_id_set_still_skips(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify a half-configured environment (id only, no key) still skips.

    Purpose:
        Both env vars are required; an unset key would let the fetcher hit
        Adzuna and 401, which the orchestrator should avoid up-front.
    """

    monkeypatch.setenv(ADZUNA_APP_ID_ENV, "id-only")
    monkeypatch.delenv(ADZUNA_APP_KEY_ENV, raising=False)
    monkeypatch.setattr(discovery_main, "AdzunaFetcher", _StubAdzunaFetcher)

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            deduplicator = Deduplicator(db)

            counters = await discovery_main.fetch_adzuna_jobs(
                {"enabled": True, "search_terms": ["x"]},
                db,
                deduplicator,
            )

    assert counters == (0, 0, 0, 0)
    assert _StubAdzunaFetcher.init_calls == []


@pytest.mark.asyncio
async def test_returns_zero_when_no_search_terms_anywhere(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify the orchestrator skips when neither defaults nor config provide terms.

    Purpose:
        Running Adzuna with an empty ``what`` would return generic results;
        the orchestrator's contract is to skip rather than fall back.
    """

    monkeypatch.setenv(ADZUNA_APP_ID_ENV, "id-123")
    monkeypatch.setenv(ADZUNA_APP_KEY_ENV, "key-123")
    monkeypatch.setattr(discovery_main, "AdzunaFetcher", _StubAdzunaFetcher)

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            deduplicator = Deduplicator(db)

            counters = await discovery_main.fetch_adzuna_jobs(
                {"enabled": True},
                db,
                deduplicator,
                default_search_terms=None,
            )

    assert counters == (0, 0, 0, 0)
    assert _StubAdzunaFetcher.init_calls == []


# ---------------------------------------------------------------------------
# Happy-path fan-out and accounting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_terms_times_locations_fan_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify each ``search_term × location`` produces one crawl record.

    Purpose:
        The orchestrator's value vs. a single broad query is per-variant
        accounting; regressions that loop only on terms (or only locations)
        would erase this signal from the dashboard.
    """

    monkeypatch.setenv(ADZUNA_APP_ID_ENV, "id-123")
    monkeypatch.setenv(ADZUNA_APP_KEY_ENV, "key-123")
    monkeypatch.setattr(discovery_main, "AdzunaFetcher", _StubAdzunaFetcher)
    monkeypatch.setattr(discovery_main.asyncio, "sleep", _fast_sleep)

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            deduplicator = Deduplicator(db)

            counters = await discovery_main.fetch_adzuna_jobs(
                {
                    "enabled": True,
                    "search_terms": ["software engineer", "fpga intern"],
                    "locations": ["New York", "San Francisco"],
                },
                db,
                deduplicator,
            )

            assert db.conn is not None
            rows = await (
                await db.conn.execute(
                    "SELECT source, company, status FROM crawl_history ORDER BY id"
                )
            ).fetchall()

    materialized_rows = list(rows)
    # 2 search terms × 2 locations = 4 successful crawls, 0 failures.
    assert counters == (0, 0, 4, 0)
    assert len(materialized_rows) == 4
    assert all(row[0] == "adzuna_us" and row[2] == "SUCCESS" for row in materialized_rows)
    assert {row[1] for row in materialized_rows} == {
        "software engineer@New York",
        "software engineer@San Francisco",
        "fpga intern@New York",
        "fpga intern@San Francisco",
    }


@pytest.mark.asyncio
async def test_default_search_terms_override_block_terms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify candidate-profile defaults take precedence over YAML search terms.

    Purpose:
        Mirrors the JobSpy orchestrator: an onboarded user's role-derived
        defaults must beat the seed config's placeholder terms.
    """

    monkeypatch.setenv(ADZUNA_APP_ID_ENV, "id-123")
    monkeypatch.setenv(ADZUNA_APP_KEY_ENV, "key-123")
    monkeypatch.setattr(discovery_main, "AdzunaFetcher", _StubAdzunaFetcher)
    monkeypatch.setattr(discovery_main.asyncio, "sleep", _fast_sleep)

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            deduplicator = Deduplicator(db)

            await discovery_main.fetch_adzuna_jobs(
                {
                    "enabled": True,
                    "search_terms": ["seed-default"],
                    "locations": ["Remote"],
                },
                db,
                deduplicator,
                default_search_terms=["profile-term"],
            )

    issued_terms = [call["search_term"] for call in _StubAdzunaFetcher.init_calls]
    assert issued_terms == ["profile-term"]


@pytest.mark.asyncio
async def test_block_search_terms_used_when_no_profile_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify configured ``search_terms`` are honored when no defaults exist.

    Purpose:
        Operators editing companies.yaml should still drive the crawl when
        the candidate has no role-derived defaults yet.
    """

    monkeypatch.setenv(ADZUNA_APP_ID_ENV, "id-123")
    monkeypatch.setenv(ADZUNA_APP_KEY_ENV, "key-123")
    monkeypatch.setattr(discovery_main, "AdzunaFetcher", _StubAdzunaFetcher)
    monkeypatch.setattr(discovery_main.asyncio, "sleep", _fast_sleep)

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            deduplicator = Deduplicator(db)

            await discovery_main.fetch_adzuna_jobs(
                {
                    "enabled": True,
                    "search_terms": ["embedded engineer"],
                    "locations": ["Boston"],
                },
                db,
                deduplicator,
                default_search_terms=None,
            )

    issued_terms = [call["search_term"] for call in _StubAdzunaFetcher.init_calls]
    assert issued_terms == ["embedded engineer"]


@pytest.mark.asyncio
async def test_empty_locations_collapse_to_country_scope_sentinel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify omitting locations collapses to one country-scope crawl per term.

    Purpose:
        The orchestrator promises an empty-string sentinel — exactly one
        crawl per search term against the whole country — so users with no
        location preference still get a run.
    """

    monkeypatch.setenv(ADZUNA_APP_ID_ENV, "id-123")
    monkeypatch.setenv(ADZUNA_APP_KEY_ENV, "key-123")
    monkeypatch.setattr(discovery_main, "AdzunaFetcher", _StubAdzunaFetcher)
    monkeypatch.setattr(discovery_main.asyncio, "sleep", _fast_sleep)

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            deduplicator = Deduplicator(db)

            await discovery_main.fetch_adzuna_jobs(
                {
                    "enabled": True,
                    "search_terms": ["embedded engineer"],
                    # locations omitted entirely.
                },
                db,
                deduplicator,
            )

            assert db.conn is not None
            rows = await (
                await db.conn.execute(
                    "SELECT company FROM crawl_history ORDER BY id"
                )
            ).fetchall()

    # The empty-string sentinel renders as ``any`` in the crawl label.
    assert [row[0] for row in rows] == ["embedded engineer@any"]
    assert len(_StubAdzunaFetcher.init_calls) == 1
    # Empty-string sentinel must reach the fetcher as ``location=None`` so
    # the constructor omits the ``where`` query param entirely.
    assert _StubAdzunaFetcher.init_calls[0]["location"] is None


@pytest.mark.asyncio
async def test_country_override_propagates_to_fetcher_and_crawl_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify the ``country`` field flows into both fetcher kwargs and crawl source.

    Purpose:
        Country selection drives both Adzuna's URL routing and the crawl
        label; both must agree so the dashboard split-by-country works.
    """

    monkeypatch.setenv(ADZUNA_APP_ID_ENV, "id-123")
    monkeypatch.setenv(ADZUNA_APP_KEY_ENV, "key-123")
    monkeypatch.setattr(discovery_main, "AdzunaFetcher", _StubAdzunaFetcher)
    monkeypatch.setattr(discovery_main.asyncio, "sleep", _fast_sleep)

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            deduplicator = Deduplicator(db)

            await discovery_main.fetch_adzuna_jobs(
                {
                    "enabled": True,
                    "search_terms": ["x"],
                    "locations": ["London"],
                    "country": "gb",
                },
                db,
                deduplicator,
            )

            assert db.conn is not None
            row = await (
                await db.conn.execute(
                    "SELECT source FROM crawl_history ORDER BY id DESC LIMIT 1"
                )
            ).fetchone()

    assert row is not None
    assert row[0] == "adzuna_gb"
    assert _StubAdzunaFetcher.init_calls[0]["country"] == "gb"


# ---------------------------------------------------------------------------
# Failure accounting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_exception_records_failed_crawl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify a fetch exception writes a FAILED crawl row and a failure counter.

    Purpose:
        Aligns with the JobSpy/Workday orchestrators: per-variant failures
        must be both visible in the return tuple and persisted to history.
    """

    class BrokenAdzuna:
        """Raise from ``fetch_jobs`` so the orchestrator records the failure."""

        def __init__(self, **_: Any) -> None:
            """Accept production kwargs without storing them."""

        async def __aenter__(self) -> "BrokenAdzuna":
            """Return self for ``async with``."""

            return self

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc_val: BaseException | None,
            exc_tb: object,
        ) -> None:
            """No-op exit."""

        async def fetch_jobs(self) -> list[object]:
            """Raise a deterministic upstream failure."""

            raise RuntimeError("simulated adzuna outage")

    monkeypatch.setenv(ADZUNA_APP_ID_ENV, "id-123")
    monkeypatch.setenv(ADZUNA_APP_KEY_ENV, "key-123")
    monkeypatch.setattr(discovery_main, "AdzunaFetcher", BrokenAdzuna)
    monkeypatch.setattr(discovery_main.asyncio, "sleep", _fast_sleep)

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            deduplicator = Deduplicator(db)

            counters = await discovery_main.fetch_adzuna_jobs(
                {
                    "enabled": True,
                    "search_terms": ["x"],
                    "locations": ["Remote"],
                },
                db,
                deduplicator,
            )

            assert db.conn is not None
            row = await (
                await db.conn.execute(
                    "SELECT status, error_message FROM crawl_history ORDER BY id DESC LIMIT 1"
                )
            ).fetchone()

    assert counters == (0, 0, 0, 1)
    assert row is not None
    assert row[0] == "FAILED"
    assert "simulated adzuna outage" in row[1]
