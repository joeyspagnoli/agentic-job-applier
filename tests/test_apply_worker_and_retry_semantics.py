"""Validate apply worker browser flow, retry scheduling, and fallback logging.

Purpose:
    Cover the new apply stack with deterministic tests for Simplify polling,
    SQLite-compatible retry scheduling, claim eligibility, and diagnostic
    logging in fallback paths.
"""

from __future__ import annotations

import re
import tempfile
from collections.abc import Awaitable
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path
from typing import Any

import pytest

from scripts import process_apply_jobs
from src.agents.apply_worker import browser
from src.agents.apply_worker import field_scanner
from src.agents.apply_worker import resume_upload
from src.agents.apply_worker.schemas import ATSPlatform
from src.agents.apply_worker.schemas import ApplyOutcome
from src.agents.apply_worker.schemas import ConfidenceReport
from src.database.db_manager import DatabaseManager
from src.models.job_posting import JobPosting


class FakeBrowserPage:
    """Provide a small async Playwright-like page surface for unit tests.

    Purpose:
        Keep browser-flow tests deterministic without requiring a live browser
        by emulating only the async methods used by `_run_application_flow`.
    """

    def __init__(self, *, simplify_detected: bool = False, fail_on_goto: bool = False):
        """Store deterministic behavior flags for page method responses.

        Purpose:
            Configure whether Simplify detection succeeds and whether navigation
            fails to drive specific control-flow branches under test.
        Args:
            simplify_detected: Whether the Simplify polling call returns True.
            fail_on_goto: Whether `goto()` should raise to simulate nav failure.
        Output:
            Returns `None` after storing constructor values.
        """

        self.url = "about:blank"
        self.main_frame = object()
        self.frames: list[object] = [self.main_frame]
        self.simplify_detected = simplify_detected
        self.fail_on_goto = fail_on_goto
        self.simplify_poll_args: dict[str, int] | None = None

    async def goto(self, source_url: str, timeout: int) -> None:
        """Record navigation and optionally raise to emulate page load errors.

        Purpose:
            Drive success/failure navigation branches in the flow under test.
        Args:
            source_url: Destination URL requested by the flow.
            timeout: Navigation timeout value; accepted for signature parity.
        Output:
            Returns `None` unless configured to raise.
        Raises:
            RuntimeError: When `fail_on_goto` was enabled for this page.
        """

        _ = timeout
        if self.fail_on_goto:
            raise RuntimeError("navigation failed")
        self.url = source_url

    async def wait_for_load_state(self, state: str, timeout: int) -> None:
        """Accept load-state waits for compatibility with production flow.

        Purpose:
            Provide API compatibility while keeping tests deterministic.
        Args:
            state: Load-state string from the production call site.
            timeout: Timeout value supplied by production logic.
        Output:
            Returns `None`.
        """

        _ = (state, timeout)

    async def content(self) -> str:
        """Return deterministic HTML content for ATS detection.

        Purpose:
            Keep ATS detection input stable in browser-flow tests.
        Args:
            None.
        Output:
            Returns static HTML content.
        """

        return "<html><body><form></form></body></html>"

    async def evaluate(self, script: str, arg: Any | None = None) -> bool:
        """Return deterministic results for known JS snippets.

        Purpose:
            Emulate Playwright `evaluate()` behavior for Simplify polling and
            DOM stability waits while capturing polling argument payloads.
        Args:
            script: JavaScript payload identifier used by the flow.
            arg: Optional argument passed from the flow.
        Output:
            Returns deterministic boolean responses by script identity.
        Raises:
            RuntimeError: When an unexpected script string is passed.
        """

        if script == browser._JS_DETECT_SIMPLIFY:
            if not isinstance(arg, dict):
                raise RuntimeError("Simplify poll argument must be a dict")
            self.simplify_poll_args = arg
            return self.simplify_detected

        if script == browser._JS_WAIT_FOR_STABILITY:
            return True

        raise RuntimeError("Unexpected evaluate script")


class FakeScanFrame:
    """Provide deterministic frame behavior for unresolved-field scan tests.

    Purpose:
        Exercise iframe exception logging by raising from `evaluate()` while
        exposing a stable `url` property.
    """

    def __init__(self, frame_url: str):
        """Store a stable frame URL for logging assertions.

        Purpose:
            Make warning log assertions deterministic when scan fallbacks occur.
        Args:
            frame_url: URL string attached to the fake frame.
        Output:
            Returns `None` after storing the URL.
        """

        self.url = frame_url

    async def evaluate(self, script: str) -> list[dict[str, object]]:
        """Raise a deterministic error to emulate cross-origin iframe failures.

        Purpose:
            Trigger fallback logging in `scan_unresolved_fields`.
        Args:
            script: JavaScript scan payload from production logic.
        Output:
            Does not return because this fake always raises.
        Raises:
            RuntimeError: Always raised to emulate inaccessible frame context.
        """

        _ = script
        raise RuntimeError("cross-origin frame")


class FakeScanPage:
    """Provide deterministic page/frame objects for field-scan tests.

    Purpose:
        Keep unresolved-field scan tests isolated from Playwright runtime.
    """

    def __init__(self) -> None:
        """Initialize one main frame and one failing iframe.

        Purpose:
            Model mixed frame outcomes where main-frame scan succeeds but iframe
            scan fails and should log structured context.
        Args:
            None.
        Output:
            Returns `None` after initializing frame state.
        """

        self.main_frame = object()
        self.frames = [self.main_frame, FakeScanFrame("https://cross.origin/frame")]

    async def evaluate(self, script: str) -> list[dict[str, object]]:
        """Return no unresolved fields for the main-frame scan.

        Purpose:
            Focus the test on iframe failure logging instead of field parsing.
        Args:
            script: JavaScript scan payload from production logic.
        Output:
            Returns an empty descriptor list.
        """

        _ = script
        return []


class FakeUploadLocator:
    """Provide a locator stub that always fails count checks.

    Purpose:
        Drive upload fallback logging paths in selector loops.
    """

    @property
    def first(self) -> "FakeUploadLocator":
        """Return self to match Playwright locator chaining semantics.

        Purpose:
            Keep fake behavior compatible with `.locator(...).first` usage.
        Args:
            None.
        Output:
            Returns this instance.
        """

        return self

    async def count(self) -> int:
        """Raise a deterministic error for selector failure simulation.

        Purpose:
            Trigger exception handling and structured warning logs.
        Args:
            None.
        Output:
            Does not return because this fake always raises.
        Raises:
            RuntimeError: Always raised to emulate DOM query failure.
        """

        raise RuntimeError("selector lookup failed")


class FakeUploadPage:
    """Provide the minimal page API required by direct upload strategy tests.

    Purpose:
        Exercise selector-loop error handling without browser dependencies.
    """

    def locator(self, selector: str) -> FakeUploadLocator:
        """Return a locator stub for any selector.

        Purpose:
            Ensure each selector iteration in upload strategy reaches the same
            deterministic failure mode.
        Args:
            selector: CSS selector requested by upload strategy.
        Output:
            Returns a `FakeUploadLocator` instance.
        """

        _ = selector
        return FakeUploadLocator()


def _noop_async(*_: object, **__: object) -> Awaitable[None]:
    """Return a no-op awaitable used for monkeypatched async helpers.

    Purpose:
        Remove side effects from browser artifact helpers in unit tests.
    Args:
        *_: Ignored positional args.
        **__: Ignored keyword args.
    Output:
        Returns an awaitable resolving to `None`.
    """

    async def _inner() -> None:
        """Resolve immediately without side effects.

        Purpose:
            Provide awaitable compatibility for no-op monkeypatch helpers.
        Args:
            None.
        Output:
            Returns `None`.
        """

        return None

    return _inner()


def _build_confidence_report() -> ConfidenceReport:
    """Build a deterministic confidence report for browser flow tests.

    Purpose:
        Keep apply-flow assertions stable without depending on confidence logic
        internals in this integration-focused test module.
    Args:
        None.
    Output:
        Returns a `ConfidenceReport` with fixed values.
    """

    return ConfidenceReport(
        score=0.75,
        checks=[],
        has_hard_blockers=False,
        resume_uploaded=True,
        simplify_autofill_detected=False,
        unresolved_required_count=0,
        unresolved_optional_count=0,
        ats_platform=ATSPlatform.UNKNOWN,
    )


async def _seed_apply_candidate(
    db: DatabaseManager,
    *,
    review_run_id: int,
) -> JobPosting:
    """Insert one job and one eligible SUCCESS review row for apply claims.

    Purpose:
        Reduce setup duplication across apply-claim semantics tests.
    Args:
        db: Connected database manager used for inserts.
        review_run_id: Review-run identifier for deterministic joins.
    Output:
        Returns the inserted `JobPosting` model.
    """

    job = JobPosting(
        source="test",
        source_url=f"https://example.com/jobs/{review_run_id}",
        company="ApplyCo",
        title="Apply Candidate",
        description="Apply queue candidate",
    )
    await db.insert_job(job.to_db_dict())

    assert db.conn is not None
    await db.conn.execute(
        """
        INSERT INTO review_runs (
            id,
            job_hash,
            tailor_run_id,
            status,
            verdict,
            selected_pdf_path,
            fallback_base_pdf_path,
            started_at,
            completed_at
        )
        VALUES (?, ?, ?, 'SUCCESS', 'PASS', ?, ?, datetime('now', '-2 minutes'), datetime('now', '-1 minute'))
        """,
        (
            review_run_id,
            job.job_hash,
            review_run_id,
            "/tmp/selected.pdf",
            "/tmp/base.pdf",
        ),
    )
    await db.conn.commit()
    return job


@pytest.mark.asyncio
async def test_run_application_flow_uses_named_simplify_poll_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify Simplify polling uses object args and missing markers do not hang.

    Purpose:
        Regress H-001 by asserting `_run_application_flow` passes named polling
        args to JS and still returns normally when markers are absent.
    Args:
        monkeypatch: Fixture used to isolate helper calls from browser runtime.
        tmp_path: Temporary directory for artifact path arguments.
    Output:
        Returns `None`; test passes when flow completes and args are correct.
    """

    page = FakeBrowserPage(simplify_detected=False)
    trigger_calls = {"count": 0}

    async def fake_trigger(_: Any) -> None:
        """Count Simplify trigger attempts for branch assertions.

        Purpose:
            Confirm no trigger click is attempted when Simplify is not detected.
        Args:
            _: Ignored page argument from call site.
        Output:
            Returns `None` after incrementing call count.
        """

        trigger_calls["count"] += 1

    async def fake_upload(_: Any, __: Path) -> bool:
        """Return deterministic upload success in browser flow tests.

        Purpose:
            Keep the flow on the success path while isolating upload internals.
        Args:
            _: Ignored page argument from call site.
            __: Ignored PDF path from call site.
        Output:
            Returns `True`.
        """

        return True

    async def fake_scan(_: Any) -> list[object]:
        """Return no unresolved fields for deterministic assertions.

        Purpose:
            Keep outcome logic focused on polling and orchestration behavior.
        Args:
            _: Ignored page argument from call site.
        Output:
            Returns an empty list.
        """

        return []

    async def fake_confidence(*_: object, **__: object) -> ConfidenceReport:
        """Return deterministic confidence payload for flow assertions.

        Purpose:
            Avoid coupling this test to confidence scoring implementation.
        Args:
            *_: Ignored positional args from call site.
            **__: Ignored keyword args from call site.
        Output:
            Returns a fixed `ConfidenceReport`.
        """

        return _build_confidence_report()

    monkeypatch.setattr(browser, "detect_ats_platform", lambda *_: ATSPlatform.UNKNOWN)
    monkeypatch.setattr(browser, "_trigger_simplify_autofill", fake_trigger)
    monkeypatch.setattr(browser, "upload_resume", fake_upload)
    monkeypatch.setattr(browser, "scan_unresolved_fields", fake_scan)
    monkeypatch.setattr(browser, "compute_confidence", fake_confidence)
    monkeypatch.setattr(browser, "_save_screenshot_safe", _noop_async)
    monkeypatch.setattr(browser, "_save_dom_safe", _noop_async)

    result = await browser._run_application_flow(
        page=page,
        source_url="https://example.com/apply",
        resume_pdf_path=tmp_path / "resume.pdf",
        job_hash="abc123",
        screenshot_path=tmp_path / "shot.png",
        dom_snapshot_path=tmp_path / "dom.html",
        unresolved_path=tmp_path / "unresolved.json",
        dry_run=True,
    )

    assert result.success is True
    assert result.outcome == ApplyOutcome.NEEDS_REVIEW
    assert trigger_calls["count"] == 0
    assert page.simplify_poll_args == {
        "intervalMs": browser.SIMPLIFY_POLL_INTERVAL_MS,
        "timeoutMs": browser.SIMPLIFY_POLL_TIMEOUT_MS,
    }


@pytest.mark.asyncio
async def test_run_application_flow_navigation_failure_captures_failure_outcome(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify navigation failures return FAILED_NAVIGATION deterministically.

    Purpose:
        Cover the early-failure branch to prevent regressions in apply-run
        failure classification and artifact capture fallback behavior.
    Args:
        monkeypatch: Fixture used to intercept screenshot helper calls.
        tmp_path: Temporary directory for artifact path arguments.
    Output:
        Returns `None`; test passes when failure outcome is reported.
    """

    page = FakeBrowserPage(fail_on_goto=True)
    screenshot_calls = {"count": 0}

    async def fake_screenshot(*_: object, **__: object) -> None:
        """Count screenshot helper invocations during failure handling.

        Purpose:
            Verify navigation errors trigger screenshot capture attempts.
        Args:
            *_: Ignored positional args.
            **__: Ignored keyword args.
        Output:
            Returns `None` after incrementing call count.
        """

        screenshot_calls["count"] += 1

    monkeypatch.setattr(browser, "_save_screenshot_safe", fake_screenshot)

    result = await browser._run_application_flow(
        page=page,
        source_url="https://example.com/apply",
        resume_pdf_path=tmp_path / "resume.pdf",
        job_hash="abc123",
        screenshot_path=tmp_path / "shot.png",
        dom_snapshot_path=tmp_path / "dom.html",
        unresolved_path=tmp_path / "unresolved.json",
        dry_run=True,
    )

    assert result.success is False
    assert result.outcome == ApplyOutcome.FAILED_NAVIGATION
    assert screenshot_calls["count"] == 1


def test_calculate_next_retry_at_uses_sqlite_utc_format() -> None:
    """Verify apply retry scheduling emits SQLite-compatible UTC timestamps.

    Purpose:
        Regress H-002 by ensuring retry timestamps are persisted in
        `%Y-%m-%d %H:%M:%S` format instead of timezone ISO strings.
    Args:
        None.
    Output:
        Returns `None`; test passes when the timestamp format matches.
    """

    retry_at = process_apply_jobs._calculate_next_retry_at(
        retry_count=1,
        backoff_seconds=5,
        backoff_multiplier=2,
    )

    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", retry_at)
    assert "T" not in retry_at
    assert "+" not in retry_at


@pytest.mark.asyncio
async def test_claim_next_apply_job_accepts_due_iso_retry_timestamp() -> None:
    """Verify due ISO retry rows remain claimable after datetime normalization.

    Purpose:
        Regress H-002 by proving claim SQL converts legacy ISO timestamps before
        retry eligibility comparison.
    Args:
        None.
    Output:
        Returns `None`; test passes when a due row is claimed.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "jobs.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            await db.migrate_review_schema()
            await db.migrate_apply_schema()
            await _seed_apply_candidate(db, review_run_id=101)

            assert db.conn is not None
            due_iso = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            await db.conn.execute(
                """
                INSERT INTO apply_runs (
                    job_hash,
                    review_run_id,
                    status,
                    next_retry_at,
                    started_at,
                    completed_at
                )
                SELECT
                    rr.job_hash,
                    rr.id,
                    'FAILED',
                    ?,
                    datetime('now', '-2 hours'),
                    datetime('now', '-2 hours')
                FROM review_runs rr
                WHERE rr.id = 101
                """,
                (due_iso,),
            )
            await db.conn.commit()

            claimed = await db.claim_next_apply_job(max_retries=3)

    assert claimed is not None
    assert claimed["review_run_id"] == 101


@pytest.mark.asyncio
async def test_claim_next_apply_job_blocks_future_iso_retry_timestamp() -> None:
    """Verify future ISO retry rows remain non-claimable until due.

    Purpose:
        Ensure datetime normalization does not accidentally bypass retry windows
        for not-yet-due failed runs.
    Args:
        None.
    Output:
        Returns `None`; test passes when claim returns `None`.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "jobs.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            await db.migrate_review_schema()
            await db.migrate_apply_schema()
            await _seed_apply_candidate(db, review_run_id=202)

            assert db.conn is not None
            future_iso = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
            await db.conn.execute(
                """
                INSERT INTO apply_runs (
                    job_hash,
                    review_run_id,
                    status,
                    next_retry_at,
                    started_at,
                    completed_at
                )
                SELECT
                    rr.job_hash,
                    rr.id,
                    'FAILED',
                    ?,
                    datetime('now', '-1 hours'),
                    datetime('now', '-1 hours')
                FROM review_runs rr
                WHERE rr.id = 202
                """,
                (future_iso,),
            )
            await db.conn.commit()

            claimed = await db.claim_next_apply_job(max_retries=3)

    assert claimed is None


@pytest.mark.asyncio
async def test_claim_next_apply_job_respects_max_retries_limit() -> None:
    """Verify claim query stops returning rows after max retry threshold.

    Purpose:
        Cover apply retry-cap semantics so workers do not keep reclaiming jobs
        that have already exhausted allowed failed attempts.
    Args:
        None.
    Output:
        Returns `None`; test passes when claim returns `None` at retry limit.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "jobs.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            await db.migrate_review_schema()
            await db.migrate_apply_schema()
            await _seed_apply_candidate(db, review_run_id=303)

            assert db.conn is not None
            await db.conn.execute(
                """
                INSERT INTO apply_runs (
                    job_hash,
                    review_run_id,
                    status,
                    next_retry_at,
                    started_at,
                    completed_at
                )
                SELECT
                    rr.job_hash,
                    rr.id,
                    'FAILED',
                    datetime('now', '-10 minutes'),
                    datetime('now', '-20 minutes'),
                    datetime('now', '-20 minutes')
                FROM review_runs rr
                WHERE rr.id = 303
                """,
            )
            await db.conn.execute(
                """
                INSERT INTO apply_runs (
                    job_hash,
                    review_run_id,
                    status,
                    next_retry_at,
                    started_at,
                    completed_at
                )
                SELECT
                    rr.job_hash,
                    rr.id,
                    'FAILED',
                    datetime('now', '-5 minutes'),
                    datetime('now', '-6 minutes'),
                    datetime('now', '-6 minutes')
                FROM review_runs rr
                WHERE rr.id = 303
                """,
            )
            await db.conn.commit()

            claimed = await db.claim_next_apply_job(max_retries=2)

    assert claimed is None


@pytest.mark.asyncio
async def test_mark_stale_apply_runs_failed_releases_claim_for_retry() -> None:
    """Verify stale pending cleanup restores queue progress for apply jobs.

    Purpose:
        Cover startup recovery behavior so orphaned PENDING rows transition to
        FAILED and become eligible for fresh claim attempts.
    Args:
        None.
    Output:
        Returns `None`; test passes when stale run is marked failed and reclaims.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "jobs.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            await db.migrate_review_schema()
            await db.migrate_apply_schema()
            await _seed_apply_candidate(db, review_run_id=404)

            assert db.conn is not None
            await db.conn.execute(
                """
                INSERT INTO apply_runs (
                    job_hash,
                    review_run_id,
                    status,
                    started_at
                )
                SELECT
                    rr.job_hash,
                    rr.id,
                    'PENDING',
                    datetime('now', '-3 hours')
                FROM review_runs rr
                WHERE rr.id = 404
                """,
            )
            await db.conn.commit()

            stale_count = await db.mark_stale_apply_runs_failed(lease_seconds=60)
            claimed = await db.claim_next_apply_job(max_retries=3)

    assert stale_count == 1
    assert claimed is not None
    assert claimed["review_run_id"] == 404


@pytest.mark.asyncio
async def test_scan_unresolved_fields_logs_iframe_scan_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify iframe scan exceptions are logged with context before fallback.

    Purpose:
        Regress L-001 by enforcing structured diagnostic logging for iframe scan
        failures that are intentionally skipped.
    Args:
        monkeypatch: Fixture used to capture warning log calls.
    Output:
        Returns `None`; test passes when warning log captures frame URL.
    """

    warnings: list[tuple[Any, ...]] = []

    def fake_warning(*args: object, **kwargs: object) -> None:
        """Capture warning log call arguments for assertions.

        Purpose:
            Validate that fallback exception handling emits structured logs.
        Args:
            *args: Positional arguments passed to logger.warning.
            **kwargs: Keyword arguments passed to logger.warning.
        Output:
            Returns `None` after recording call details.
        """

        _ = kwargs
        warnings.append(args)

    monkeypatch.setattr(field_scanner.logger, "warning", fake_warning)

    unresolved = await field_scanner.scan_unresolved_fields(FakeScanPage())

    assert unresolved == []
    assert len(warnings) == 1
    assert "frame_url={}" in str(warnings[0][0])
    assert "https://cross.origin/frame" in str(warnings[0][1])


@pytest.mark.asyncio
async def test_direct_upload_strategy_logs_selector_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify direct upload strategy logs selector failures before fallback.

    Purpose:
        Regress L-001 by ensuring selector exceptions are not silently swallowed
        in resume upload fallback logic.
    Args:
        monkeypatch: Fixture used to capture warning log calls.
    Output:
        Returns `None`; test passes when one warning is emitted per selector.
    """

    warning_messages: list[tuple[Any, ...]] = []

    def fake_warning(*args: object, **kwargs: object) -> None:
        """Capture warning log calls for selector failure assertions.

        Purpose:
            Validate upload fallback emits diagnostics for every failed selector.
        Args:
            *args: Positional arguments passed to logger.warning.
            **kwargs: Keyword arguments passed to logger.warning.
        Output:
            Returns `None` after recording arguments.
        """

        _ = kwargs
        warning_messages.append(args)

    monkeypatch.setattr(resume_upload.logger, "warning", fake_warning)

    uploaded = await resume_upload._try_direct_file_input(
        FakeUploadPage(),
        "/tmp/resume.pdf",
    )

    assert uploaded is False
    assert len(warning_messages) == len(resume_upload._FILE_INPUT_SELECTORS)
