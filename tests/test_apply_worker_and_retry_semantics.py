"""Validate apply worker browser flow, retry scheduling, and fallback logging.

Purpose:
    Cover the new apply stack with deterministic tests for Simplify polling,
    SQLite-compatible retry scheduling, claim eligibility, and diagnostic
    logging in fallback paths.
"""

from __future__ import annotations

import asyncio
import re
import sys
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
from src.database.db_manager import ClaimOwnershipError
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

    async def goto(
        self, source_url: str, timeout: int, wait_until: str | None = None
    ) -> None:
        """Record navigation and optionally raise to emulate page load errors.

        Purpose:
            Drive success/failure navigation branches in the flow under test.
        Args:
            source_url: Destination URL requested by the flow.
            timeout: Navigation timeout value; accepted for signature parity.
            wait_until: Playwright load-state hint; accepted for signature parity.
        Output:
            Returns `None` unless configured to raise.
        Raises:
            RuntimeError: When `fail_on_goto` was enabled for this page.
        """

        _ = timeout
        _ = wait_until
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


def test_normalize_apply_url_appends_apply_for_lever_postings() -> None:
    """Lever posting URLs must be rewritten to land on the apply form."""

    assert browser._normalize_apply_url(
        "https://jobs.lever.co/weride/abc-123"
    ) == "https://jobs.lever.co/weride/abc-123/apply"


def test_normalize_apply_url_idempotent_for_lever_apply_paths() -> None:
    """A URL already ending in /apply must not be rewritten twice."""

    url = "https://jobs.lever.co/weride/abc-123/apply"
    assert browser._normalize_apply_url(url) == url


def test_normalize_apply_url_passthrough_for_non_lever() -> None:
    """Non-Lever URLs are returned unchanged so other ATSes are unaffected."""

    for url in (
        "https://boards.greenhouse.io/cloudflare/jobs/7914628",
        "https://jobs.ashbyhq.com/notion/abc/application",
        "https://salesforce.wd12.myworkdayjobs.com/External_Career_Site/job/X",
    ):
        assert browser._normalize_apply_url(url) == url


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
async def test_apply_once_persists_handoff_when_outcome_needs_review(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify apply loop persists handoff rows for NEEDS_REVIEW outcomes.

    Purpose:
        Ensure operator-review persistence is written whenever a successful
        apply attempt stops at NEEDS_REVIEW (dry-run or submit-not-implemented).
    Args:
        monkeypatch: Fixture used to inject deterministic browser responses.
        tmp_path: Temporary directory for deterministic resume artifact paths.
    Output:
        Returns `None`; test passes when handoff persistence is invoked once.
    """

    selected_pdf = tmp_path / "selected.pdf"
    selected_pdf.write_bytes(b"%PDF-1.4")

    class FakeDB:
        """Capture apply persistence calls for one deterministic apply cycle.

        Purpose:
            Keep `_apply_once` tests focused on orchestration behavior without
            creating a full SQLite database fixture.
        """

        def __init__(self) -> None:
            """Initialize deterministic claim payload and call collectors.

            Purpose:
                Seed one eligible claimed row and empty call history lists.
            Args:
                None.
            Output:
                Returns `None`.
            """

            self.success_calls: list[dict[str, object]] = []
            self.handoff_calls: list[dict[str, object]] = []

        async def is_budget_exceeded(self) -> bool:
            """Return non-exceeded state for success-path orchestration tests.

            Purpose:
                Keep this test focused on success/handoff persistence behavior
                rather than budget-guard branching.
            Args:
                self: Fake DB instance.
            Output:
                Returns `False`.
            """

            return False

        async def claim_next_apply_job(self, **_: object) -> dict[str, object]:
            """Return one pre-claimed apply candidate row.

            Purpose:
                Simulate queue claim behavior needed by `_apply_once`.
            Args:
                **_: Ignored keyword arguments from production call site.
            Output:
                Returns a single claimed-row payload.
            """

            return {
                "_apply_run_id": 77,
                "_apply_claim_token": "claim-token-77",
                "job_hash": "a" * 32,
                "review_run_id": 88,
                "source_url": "https://example.com/jobs/77",
                "review_verdict": "PASS",
                "selected_pdf_path": str(selected_pdf),
                "fallback_base_pdf_path": str(selected_pdf),
            }

        async def record_apply_success(self, **kwargs: object) -> None:
            """Store apply-success payload for later assertions.

            Purpose:
                Verify `_apply_once` writes expected success persistence data.
            Args:
                **kwargs: Keyword payload forwarded from `_apply_once`.
            Output:
                Returns `None` after recording one call.
            """

            self.success_calls.append(dict(kwargs))

        async def record_apply_handoff(self, **kwargs: object) -> None:
            """Store handoff payload for later assertions.

            Purpose:
                Verify `_apply_once` emits operator handoff persistence.
            Args:
                **kwargs: Keyword payload forwarded from `_apply_once`.
            Output:
                Returns `None` after recording one call.
            """

            self.handoff_calls.append(dict(kwargs))

        async def record_cost_event(
            self,
            *,
            stage: str,
            cost_usd: float,
            job_hash: str | None = None,
            run_id: str | None = None,
            metadata_json: str | None = None,
        ) -> None:
            """Accept cost writes without side effects in orchestration tests.

            Purpose:
                Keep this test isolated from cost-persistence details while
                matching the worker's expected DB interface.
            Args:
                stage: Stage label for the cost event.
                cost_usd: Cost amount emitted by the worker.
                job_hash: Optional associated job hash.
                run_id: Optional associated run identifier.
                metadata_json: Optional serialized metadata payload.
            Output:
                Returns `None`.
            """

            _ = (stage, cost_usd, job_hash, run_id, metadata_json)

    async def fake_apply_to_job(**_: object) -> browser.ApplyRunResult:
        """Return deterministic NEEDS_REVIEW run result for orchestration tests.

        Purpose:
            Isolate `_apply_once` persistence behavior from browser internals.
        Args:
            **_: Ignored keyword args from production call site.
        Output:
            Returns a successful `ApplyRunResult` with NEEDS_REVIEW outcome.
        """

        return browser.ApplyRunResult(
            success=True,
            outcome=ApplyOutcome.NEEDS_REVIEW,
            confidence_score=0.82,
            confidence_report=_build_confidence_report(),
            screenshot_path=str(tmp_path / "screenshot.png"),
            dom_snapshot_path=str(tmp_path / "dom.html"),
            unresolved_fields=[],
            ats_platform=ATSPlatform.GREENHOUSE,
            page_url="https://boards.greenhouse.io/example/jobs/77",
        )

    monkeypatch.setattr(process_apply_jobs, "apply_to_job", fake_apply_to_job)

    fake_db = FakeDB()
    processed_count = await process_apply_jobs._apply_once(
        db=fake_db,  # type: ignore[arg-type]
        output_base_dir=tmp_path,
        cdp_url="http://localhost:9222",
        max_retries=2,
        lease_seconds=60,
        backoff_seconds=5,
        backoff_multiplier=2,
        dry_run=True,
    )

    assert processed_count == 1
    assert len(fake_db.success_calls) == 1
    assert len(fake_db.handoff_calls) == 1
    assert fake_db.handoff_calls[0]["apply_run_id"] == 77
    assert fake_db.handoff_calls[0]["review_run_id"] == 88
    assert fake_db.handoff_calls[0]["apply_outcome"] == "NEEDS_REVIEW"


@pytest.mark.asyncio
async def test_record_apply_success_rejects_invalid_claim_token() -> None:
    """Verify apply success writes require the active claim token.

    Purpose:
        Regress H-004 by ensuring stale workers cannot finalize apply runs
        after losing ownership of the pending claim row.
    Args:
        None.
    Output:
        Returns `None`; test passes when mismatched token raises ownership error.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "jobs.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            await db.migrate_review_schema()
            await db.migrate_apply_schema()
            await _seed_apply_candidate(db, review_run_id=505)

            claimed = await db.claim_next_apply_job(max_retries=2)
            assert claimed is not None
            apply_run_id_raw = claimed["_apply_run_id"]
            assert isinstance(apply_run_id_raw, int)

            with pytest.raises(ClaimOwnershipError):
                await db.record_apply_success(
                    run_id=apply_run_id_raw,
                    claim_token="invalid-token",
                    outcome=ApplyOutcome.NEEDS_REVIEW.value,
                    resume_pdf_path=None,
                    resume_source="TAILORED",
                    confidence_score=0.7,
                    confidence_report_json=None,
                    screenshot_path=None,
                    dom_snapshot_path=None,
                    unresolved_fields_json=None,
                    simplify_autofill_detected=False,
                    ats_platform=ATSPlatform.UNKNOWN.value,
                    page_url="https://example.com/jobs/505",
                )


@pytest.mark.asyncio
async def test_record_apply_failure_rejects_invalid_claim_token() -> None:
    """Verify apply failure writes require the active claim token.

    Purpose:
        Regress H-004 by preventing stale workers from forcing FAILED status on
        pending runs that belong to a different claim owner.
    Args:
        None.
    Output:
        Returns `None`; test passes when mismatched token raises ownership error.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "jobs.db"
        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            await db.migrate_review_schema()
            await db.migrate_apply_schema()
            await _seed_apply_candidate(db, review_run_id=606)

            claimed = await db.claim_next_apply_job(max_retries=2)
            assert claimed is not None
            apply_run_id_raw = claimed["_apply_run_id"]
            assert isinstance(apply_run_id_raw, int)

            with pytest.raises(ClaimOwnershipError):
                await db.record_apply_failure(
                    run_id=apply_run_id_raw,
                    claim_token="invalid-token",
                    error="runtime_timeout",
                    next_retry_at="2000-01-01 00:00:00",
                    outcome=ApplyOutcome.FAILED_OTHER.value,
                    screenshot_path=None,
                    dom_snapshot_path=None,
                    ats_platform=ATSPlatform.UNKNOWN.value,
                    page_url="https://example.com/jobs/606",
                )


@pytest.mark.asyncio
async def test_apply_once_persists_handoff_when_cost_telemetry_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify handoff persistence is not blocked by cost telemetry failures.

    Purpose:
        Regress H-005 by ensuring telemetry exceptions remain best-effort and
        cannot suppress human-review handoff rows after successful apply writes.
    Args:
        monkeypatch: Fixture used to inject deterministic runtime behavior.
        tmp_path: Temporary directory for deterministic artifact paths.
    Output:
        Returns `None`; test passes when handoff persists despite telemetry error.
    """

    selected_pdf = tmp_path / "selected.pdf"
    selected_pdf.write_bytes(b"%PDF-1.4")

    class FakeDB:
        """Capture apply persistence calls with deterministic claim payload."""

        def __init__(self) -> None:
            """Initialize deterministic call collectors for assertions.

            Purpose:
                Store success and handoff payloads emitted by `_apply_once`.
            Args:
                None.
            Output:
                Returns `None`.
            """

            self.success_calls: list[dict[str, object]] = []
            self.handoff_calls: list[dict[str, object]] = []

        async def is_budget_exceeded(self) -> bool:
            """Return non-exceeded state for orchestration-path coverage.

            Purpose:
                Keep this test focused on success-path persistence ordering.
            Args:
                self: Fake DB instance.
            Output:
                Returns `False`.
            """

            return False

        async def claim_next_apply_job(self, **_: object) -> dict[str, object]:
            """Return one claimed row including token ownership metadata.

            Purpose:
                Provide deterministic queue claim payload for `_apply_once`.
            Args:
                **_: Ignored keyword arguments from production call site.
            Output:
                Returns one claimed-row dictionary.
            """

            return {
                "_apply_run_id": 88,
                "_apply_claim_token": "claim-token-88",
                "job_hash": "b" * 32,
                "review_run_id": 99,
                "source_url": "https://example.com/jobs/88",
                "review_verdict": "PASS",
                "selected_pdf_path": str(selected_pdf),
                "fallback_base_pdf_path": str(selected_pdf),
            }

        async def record_apply_success(self, **kwargs: object) -> None:
            """Store apply-success payload for later assertions.

            Purpose:
                Verify `_apply_once` writes success persistence before telemetry.
            Args:
                **kwargs: Payload forwarded from `_apply_once`.
            Output:
                Returns `None` after recording one call.
            """

            self.success_calls.append(dict(kwargs))

        async def record_apply_handoff(self, **kwargs: object) -> None:
            """Store handoff payload for later assertions.

            Purpose:
                Verify handoff persistence remains intact under telemetry errors.
            Args:
                **kwargs: Payload forwarded from `_apply_once`.
            Output:
                Returns `None` after recording one call.
            """

            self.handoff_calls.append(dict(kwargs))

    async def fake_apply_to_job(**_: object) -> browser.ApplyRunResult:
        """Return deterministic NEEDS_REVIEW result for orchestration tests.

        Purpose:
            Keep this test focused on persistence ordering and error isolation.
        Args:
            **_: Ignored call-site arguments.
        Output:
            Returns successful `ApplyRunResult` requiring handoff.
        """

        return browser.ApplyRunResult(
            success=True,
            outcome=ApplyOutcome.NEEDS_REVIEW,
            confidence_score=0.91,
            confidence_report=_build_confidence_report(),
            screenshot_path=str(tmp_path / "screenshot.png"),
            dom_snapshot_path=str(tmp_path / "dom.html"),
            unresolved_fields=[],
            ats_platform=ATSPlatform.GREENHOUSE,
            page_url="https://boards.greenhouse.io/example/jobs/88",
        )

    async def fake_record_stage_cost_event(**_: object) -> None:
        """Raise deterministic telemetry error for best-effort behavior tests.

        Purpose:
            Ensure telemetry write failures cannot break success/handoff flow.
        Args:
            **_: Ignored call-site arguments.
        Output:
            Does not return because this helper always raises.
        Raises:
            RuntimeError: Always raised for deterministic failure simulation.
        """

        raise RuntimeError("cost telemetry unavailable")

    monkeypatch.setattr(process_apply_jobs, "apply_to_job", fake_apply_to_job)
    monkeypatch.setattr(
        process_apply_jobs,
        "record_stage_cost_event",
        fake_record_stage_cost_event,
    )

    fake_db = FakeDB()
    processed_count = await process_apply_jobs._apply_once(
        db=fake_db,  # type: ignore[arg-type]
        output_base_dir=tmp_path,
        cdp_url="http://localhost:9222",
        max_retries=2,
        lease_seconds=60,
        backoff_seconds=5,
        backoff_multiplier=2,
        dry_run=True,
    )

    assert processed_count == 1
    assert len(fake_db.success_calls) == 1
    assert len(fake_db.handoff_calls) == 1


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


@pytest.mark.asyncio
async def test_main_always_runs_with_dry_run_true_regardless_of_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify the apply worker hard-disables auto-submit at the call site.

    Purpose:
        Lock in the OSS-launch safety contract that `dry_run=True` is always
        forwarded to `_apply_once`, even when the legacy `APPLY_DRY_RUN`
        environment variable is set to a falsy value.
    Args:
        monkeypatch: Fixture used to inject deterministic preflight, DB, and
            apply-once stubs while controlling environment state.
        tmp_path: Temporary directory used as the apply output base dir.
    Output:
        Returns `None`; test passes when `dry_run=True` is captured exactly once.
    """

    # Arrange: legacy env var explicitly tries to enable auto-submit.
    monkeypatch.setenv("APPLY_DRY_RUN", "false")
    monkeypatch.setattr(sys, "argv", ["process_apply_jobs", "--once"])

    captured_kwargs: list[dict[str, object]] = []

    async def fake_apply_once(**kwargs: object) -> int:
        """Capture orchestration kwargs so test can assert dry_run value.

        Purpose:
            Avoid side effects from the real apply loop while preserving the
            keyword interface used by `_apply_once`.
        Args:
            **kwargs: Forwarded keyword payload from `main`.
        Output:
            Returns `1` to signal one job was processed.
        """

        captured_kwargs.append(dict(kwargs))
        return 1

    async def fake_check_chrome_preflight(_: str) -> None:
        """Bypass network-dependent Chrome preflight in unit tests.

        Purpose:
            Keep the test deterministic without launching a real Chrome.
        Args:
            _: Ignored CDP URL argument.
        Output:
            Returns `None`.
        """

        return None

    def fake_check_preflight(_: str) -> None:
        """Bypass dependency preflight in unit tests.

        Purpose:
            Avoid playwright/display checks in this orchestration-focused test.
        Args:
            _: Ignored CDP URL argument.
        Output:
            Returns `None`.
        """

        return None

    class FakeDB:
        """Minimal async-context DB stub for `main` orchestration tests."""

        async def __aenter__(self) -> "FakeDB":
            """Return self to support async-with usage in the worker.

            Purpose:
                Match the production `DatabaseManager` async-context shape.
            Args:
                None.
            Output:
                Returns this fake DB instance.
            """

            return self

        async def __aexit__(self, *_: object) -> None:
            """Accept context-exit calls without side effects.

            Purpose:
                Match the production async-context shape.
            Args:
                *_: Ignored exception triple.
            Output:
                Returns `None`.
            """

            return None

        async def create_tables(self) -> None:
            """Accept schema bootstrap call without side effects."""

            return None

        async def migrate_review_schema(self) -> None:
            """Accept review-schema migration call without side effects."""

            return None

        async def migrate_apply_schema(self) -> None:
            """Accept apply-schema migration call without side effects."""

            return None

        async def migrate_cost_schema(self) -> None:
            """Accept cost-schema migration call without side effects."""

            return None

        async def mark_stale_apply_runs_failed(self, *, lease_seconds: int) -> int:
            """Return zero stale rows for orchestration tests.

            Purpose:
                Keep startup logging deterministic while exercising `main`.
            Args:
                lease_seconds: Lease threshold from worker config (ignored).
            Output:
                Returns `0`.
            """

            _ = lease_seconds
            return 0

    monkeypatch.setattr(process_apply_jobs, "_apply_once", fake_apply_once)
    monkeypatch.setattr(
        process_apply_jobs,
        "_check_chrome_preflight",
        fake_check_chrome_preflight,
    )
    monkeypatch.setattr(process_apply_jobs, "_check_preflight", fake_check_preflight)
    monkeypatch.setattr(
        process_apply_jobs,
        "DatabaseManager",
        lambda *_args, **_kwargs: FakeDB(),
    )
    monkeypatch.setattr(
        process_apply_jobs,
        "resolve_database_path",
        lambda: tmp_path / "jobs.db",
    )
    monkeypatch.setattr(
        process_apply_jobs,
        "resolve_repo_root",
        lambda: tmp_path,
    )

    # Act
    await process_apply_jobs.main()

    # Assert: dry_run was forwarded as True exactly once, despite env override.
    assert len(captured_kwargs) == 1
    assert captured_kwargs[0]["dry_run"] is True


def test_main_argparse_rejects_no_dry_run_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify `--no-dry-run` is no longer a recognized CLI option.

    Purpose:
        Lock in removal of the auto-submit override flag so future regressions
        cannot reintroduce a CLI path that bypasses the dry-run guard.
    Args:
        monkeypatch: Fixture used to set deterministic argv.
    Output:
        Returns `None`; test passes when argparse exits with non-zero status.
    """

    # Arrange
    monkeypatch.setattr(sys, "argv", ["process_apply_jobs", "--no-dry-run"])

    # Act / Assert
    with pytest.raises(SystemExit) as exc_info:
        asyncio.run(process_apply_jobs.main())

    assert exc_info.value.code != 0


def test_load_bool_env_helper_is_removed() -> None:
    """Verify the orphaned `_load_bool_env` helper was deleted.

    Purpose:
        Guard against reintroducing the env-var-driven dry-run override path
        by ensuring the helper that parsed `APPLY_DRY_RUN` no longer exists.
    Args:
        None.
    Output:
        Returns `None`; test passes when the attribute is absent.
    """

    assert not hasattr(process_apply_jobs, "_load_bool_env")
    assert not hasattr(process_apply_jobs, "DEFAULT_APPLY_DRY_RUN")
