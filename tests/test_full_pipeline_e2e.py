"""Exercise deterministic full-pipeline integration from discovery to review.

Purpose:
    Close the default-suite coverage gap for autonomous workflow handoffs by
    validating discovery, gate, tailor, and review wiring in one local run.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

import main as discovery_main
from scripts import process_new_jobs
from scripts import process_qualified_jobs
from scripts import process_reviewed_resumes
from src.agents.resume_review_pi import ReviewReport
from src.agents.resume_review_pi import ReviewRunResult
from src.agents.resume_review_pi import ReviewVerdict
from src.agents.resume_tailor_pi import TailorRunResult
from src.agents.root_apply_decider import ApplyDecision
from src.agents.root_apply_decider import GateDebugInfo
from src.agents.root_apply_decider import GateRunResult
from src.database.db_manager import DatabaseManager
from src.models.job_posting import JobPosting

PAST_RETRY_TIMESTAMP = "2000-01-01 00:00:00"
DEFAULT_LEASE_SECONDS = 7_200
DEFAULT_BACKOFF_SECONDS = 600
DEFAULT_BACKOFF_MULTIPLIER = 2


def _build_gate_result(decision: ApplyDecision) -> GateRunResult:
    """Build a deterministic gate result payload for integration tests.

    Purpose:
        Keep full-pipeline tests independent from live model variability while
        preserving the same serialized payload contract used in production.
    Args:
        decision: Gate decision to persist for this test run.
    Output:
        Returns a deterministic `GateRunResult` instance.
    """

    return GateRunResult(
        decision=decision,
        debug=GateDebugInfo(
            confidence=0.98,
            explanation="Deterministic integration gate decision",
            preference_matches=["full-pipeline-test"],
            preference_conflicts=[],
        ),
        raw_response=f'{{"decision":"{decision.value}"}}',
        provider="test",
        model="test-model",
        parse_mode="json_recovered",
    )


def _build_fake_greenhouse_fetcher(
    *,
    posting: JobPosting,
) -> type:
    """Build an async fetcher class that returns one deterministic posting.

    Purpose:
        Provide a drop-in replacement for `GreenhouseFetcher` so discovery can
        run without network I/O in deterministic integration tests.
    Args:
        posting: Normalized posting returned by the fake fetcher.
    Output:
        Returns a class implementing the async context manager interface.
    """

    class FakeGreenhouseFetcher:
        """Return one deterministic posting while matching production shape."""

        def __init__(self, company_name: str, greenhouse_id: str):
            """Store constructor values for interface parity.

            Purpose:
                Keep the fake class signature compatible with orchestrator
                construction behavior.
            Args:
                company_name: Configured company label.
                greenhouse_id: Configured board identifier.
            Output:
                Returns `None` after storing values.
            """

            self.company_name = company_name
            self.greenhouse_id = greenhouse_id

        async def __aenter__(self) -> "FakeGreenhouseFetcher":
            """Return self for async context-manager compatibility.

            Purpose:
                Match `async with GreenhouseFetcher(...)` behavior.
            Args:
                self: Fake fetcher instance.
            Output:
                Returns this instance.
            """

            return self

        async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            """Provide a no-op async context exit implementation.

            Purpose:
                Preserve production control flow without additional teardown.
            Args:
                self: Fake fetcher instance.
                exc_type: Exception type if context exits with an error.
                exc_val: Exception value if context exits with an error.
                exc_tb: Exception traceback if context exits with an error.
            Output:
                Returns `None`.
            """

            _ = (exc_type, exc_val, exc_tb)

        async def fetch_jobs(self) -> list[JobPosting]:
            """Return exactly one deterministic posting.

            Purpose:
                Keep discovery output stable for pipeline integration asserts.
            Args:
                self: Fake fetcher instance.
            Output:
                Returns a one-element list containing `posting`.
            """

            _ = self
            return [posting]

    return FakeGreenhouseFetcher


def _patch_discovery_for_single_greenhouse_posting(
    *,
    monkeypatch: pytest.MonkeyPatch,
    db_path: Path,
    posting: JobPosting,
) -> None:
    """Patch discovery config/fetcher wiring to emit one known posting.

    Purpose:
        Constrain discovery to a single deterministic Greenhouse source so full
        pipeline integration tests remain network-free and reproducible.
    Args:
        monkeypatch: Pytest monkeypatch fixture.
        db_path: Temporary SQLite path for the current test.
        posting: Posting that discovery should persist as NEW.
    Output:
        Returns `None` after patching discovery dependencies.
    """

    original_load_yaml = discovery_main.load_yaml

    def fake_load_yaml(path: str | Path) -> dict[str, Any]:
        """Return minimal company config while preserving other YAML reads.

        Purpose:
            Keep discovery deterministic by replacing only `companies.yaml`
            payloads used for source fan-out.
        Args:
            path: YAML path requested by the orchestrator.
        Output:
            Returns deterministic company config for `companies.yaml`.
        """

        if Path(path).name == "companies.yaml":
            return {
                "greenhouse_companies": {"ExampleCo": {"greenhouse_id": "exampleco"}},
                "workday_companies": {},
                "job_boards": {},
            }
        return original_load_yaml(path)

    monkeypatch.setattr(discovery_main, "resolve_database_path", lambda: db_path)
    monkeypatch.setattr(discovery_main, "load_yaml", fake_load_yaml)
    monkeypatch.setattr(
        discovery_main,
        "GreenhouseFetcher",
        _build_fake_greenhouse_fetcher(posting=posting),
    )


def _write_tailor_and_review_base_files(*, base_dir: Path) -> tuple[Path, Path, Path]:
    """Write deterministic base resume files required by tailor/review stages.

    Purpose:
        Provide stable on-disk base artifacts for worker calls that expect real
        filesystem paths during integration tests.
    Args:
        base_dir: Directory where base resume files should be created.
    Output:
        Returns `(base_yaml_path, base_tex_path, base_pdf_path)`.
    """

    base_dir.mkdir(parents=True, exist_ok=True)

    base_yaml_path = base_dir / "resume_content.yaml"
    base_tex_path = base_dir / "resume_base.tex"
    base_pdf_path = base_dir / "resume_base.pdf"

    base_yaml_path.write_text(
        "schema_version: 1\n"
        "personal:\n"
        "  section_id: personal\n"
        "  name: Test User\n"
        "  phone: 555-555-5555\n"
        "  email: test@example.com\n"
        "  links: []\n"
        "education:\n"
        "  section_id: education\n"
        "  heading: Education\n"
        "  entries: []\n"
        "experience:\n"
        "  section_id: experience\n"
        "  heading: Experience\n"
        "  listings: []\n"
        "projects:\n"
        "  section_id: projects\n"
        "  heading: Projects\n"
        "  listings: []\n"
        "skills_achievements:\n"
        "  section_id: skills_achievements\n"
        "  heading: Skills and Achievements\n"
        "  listings: []\n",
        encoding="utf-8",
    )
    base_tex_path.write_text("% base tex\n", encoding="utf-8")
    base_pdf_path.write_text("% base pdf\n", encoding="utf-8")
    return base_yaml_path, base_tex_path, base_pdf_path


def _build_tailor_success_result(*, tex_path: Path, pdf_path: Path) -> TailorRunResult:
    """Construct a deterministic successful tailor runtime payload.

    Purpose:
        Centralize successful `TailorRunResult` creation for integration tests.
    Args:
        tex_path: Expected tailored TeX output path.
        pdf_path: Expected tailored PDF output path.
    Output:
        Returns a successful `TailorRunResult` object.
    """

    return TailorRunResult(
        success=True,
        output_tex_path=str(tex_path),
        output_pdf_path=str(pdf_path),
        final_page_count=1,
    )


def _build_review_success_result(*, invocation: Any) -> ReviewRunResult:
    """Construct a deterministic successful review runtime payload.

    Purpose:
        Keep review success assertions focused on worker persistence instead of
        verbose result object assembly in each test.
    Args:
        invocation: `ReviewInvocationContract` passed to the runtime stub.
    Output:
        Returns a successful `ReviewRunResult` object.
    """

    report = ReviewReport(
        verdict=ReviewVerdict.TAILORED,
        summary="Keep tailored output",
        iteration_count=1,
        selected_yaml_path=invocation.tailored_yaml_path,
        selected_tex_path=invocation.tailored_tex_path,
        selected_pdf_path=invocation.tailored_pdf_path,
    )
    Path(invocation.review_report_path).write_text(
        report.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return ReviewRunResult(
        success=True,
        hard_failure=False,
        verdict=ReviewVerdict.TAILORED,
        review_report_path=invocation.review_report_path,
        review_report=report,
        selected_yaml_path=invocation.tailored_yaml_path,
        selected_tex_path=invocation.tailored_tex_path,
        selected_pdf_path=invocation.tailored_pdf_path,
        agent_stdout="review ok",
        agent_stderr="",
    )


@pytest.mark.asyncio
async def test_deterministic_full_pipeline_success_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify discovery->gate->tailor->review succeeds and remains idempotent.

    Purpose:
        Cover the high-priority deterministic full-pipeline handoff gap from
        bug-report/test-plan and assert reruns do not duplicate successful work.
    Args:
        monkeypatch: Pytest fixture used to patch external/runtime dependencies.
    Output:
        Returns `None`; test passes when one run succeeds and reruns process 0.
    """

    posting = JobPosting(
        source="greenhouse_test",
        source_url="https://example.com/jobs/full-pipeline-success",
        company="ExampleCo",
        title="Software Engineering Intern",
        location="Remote",
        job_type="Internship",
        description="Build backend systems and tooling.",
        requirements="Pursuing a BS in CS.",
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        db_path = tmp_path / "jobs.db"
        output_base_dir = tmp_path / "tailored"
        base_yaml_path, base_tex_path, base_pdf_path = _write_tailor_and_review_base_files(
            base_dir=tmp_path / "base",
        )

        _patch_discovery_for_single_greenhouse_posting(
            monkeypatch=monkeypatch,
            db_path=db_path,
            posting=posting,
        )

        async def fake_gate_decider(**_: object) -> GateRunResult:
            """Return deterministic APPLY for every gate invocation.

            Purpose:
                Keep full-pipeline tests deterministic and network-free.
            Args:
                **_: Ignored keyword arguments from production call site.
            Output:
                Returns deterministic APPLY gate output.
            """

            return _build_gate_result(ApplyDecision.APPLY)

        def fake_tailor_pipeline(*, invocation: Any) -> TailorRunResult:
            """Write deterministic tailor artifacts and return success.

            Purpose:
                Simulate a successful tailor runtime without calling pi tooling.
            Args:
                invocation: `TailorInvocationContract` from worker code.
            Output:
                Returns a successful `TailorRunResult`.
            """

            work_yaml_path = Path(invocation.resume_yaml_path)
            tex_path = Path(invocation.output_tex_path)
            pdf_path = Path(invocation.output_pdf_path)

            work_yaml_path.write_text("tailored: true\n", encoding="utf-8")
            tex_path.write_text("% tailored tex\n", encoding="utf-8")
            pdf_path.write_text("% tailored pdf\n", encoding="utf-8")
            return _build_tailor_success_result(tex_path=tex_path, pdf_path=pdf_path)

        def fake_review_pipeline(*, invocation: Any) -> ReviewRunResult:
            """Return deterministic successful review verdict and report.

            Purpose:
                Simulate review runtime completion without external binaries.
            Args:
                invocation: `ReviewInvocationContract` from worker code.
            Output:
                Returns successful `ReviewRunResult` with TAILORED verdict.
            """

            return _build_review_success_result(invocation=invocation)

        monkeypatch.setattr(process_new_jobs, "get_decider_model", lambda: object())
        monkeypatch.setattr(process_new_jobs, "build_root_agent", lambda model: object())
        monkeypatch.setattr(process_new_jobs, "_run_decider_for_job", fake_gate_decider)
        monkeypatch.setattr(
            process_qualified_jobs,
            "run_resume_tailor_pipeline",
            fake_tailor_pipeline,
        )
        monkeypatch.setattr(
            process_reviewed_resumes,
            "run_resume_review_pipeline",
            fake_review_pipeline,
        )

        await discovery_main.run_job_discovery()

        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            await db.migrate_agent_schema()
            await db.migrate_tailor_schema()
            await db.migrate_review_schema()

            gate_processed = await process_new_jobs.process_once(
                db=db,
                limit=10,
                max_retries=1,
            )
            tailor_processed = await process_qualified_jobs.tailor_once(
                db=db,
                output_base_dir=output_base_dir,
                resume_yaml_path=base_yaml_path,
                max_retries=2,
                lease_seconds=DEFAULT_LEASE_SECONDS,
                backoff_seconds=DEFAULT_BACKOFF_SECONDS,
                backoff_multiplier=DEFAULT_BACKOFF_MULTIPLIER,
            )
            review_processed = await process_reviewed_resumes._review_once(
                db=db,
                output_base_dir=output_base_dir,
                base_yaml_path=base_yaml_path,
                base_tex_path=base_tex_path,
                base_pdf_path=base_pdf_path,
                max_retries=2,
                lease_seconds=DEFAULT_LEASE_SECONDS,
                backoff_seconds=DEFAULT_BACKOFF_SECONDS,
                backoff_multiplier=DEFAULT_BACKOFF_MULTIPLIER,
            )

            gate_processed_again = await process_new_jobs.process_once(
                db=db,
                limit=10,
                max_retries=1,
            )
            tailor_processed_again = await process_qualified_jobs.tailor_once(
                db=db,
                output_base_dir=output_base_dir,
                resume_yaml_path=base_yaml_path,
                max_retries=2,
                lease_seconds=DEFAULT_LEASE_SECONDS,
                backoff_seconds=DEFAULT_BACKOFF_SECONDS,
                backoff_multiplier=DEFAULT_BACKOFF_MULTIPLIER,
            )
            review_processed_again = await process_reviewed_resumes._review_once(
                db=db,
                output_base_dir=output_base_dir,
                base_yaml_path=base_yaml_path,
                base_tex_path=base_tex_path,
                base_pdf_path=base_pdf_path,
                max_retries=2,
                lease_seconds=DEFAULT_LEASE_SECONDS,
                backoff_seconds=DEFAULT_BACKOFF_SECONDS,
                backoff_multiplier=DEFAULT_BACKOFF_MULTIPLIER,
            )

            stored_job = await db.get_job_by_hash(posting.job_hash)
            tailor_runs = await db.get_tailor_runs_for_job(posting.job_hash)

            assert stored_job is not None
            assert stored_job["status"] == "QUALIFIED"
            assert gate_processed == 1
            assert tailor_processed == 1
            assert review_processed == 1
            assert gate_processed_again == 0
            assert tailor_processed_again == 0
            assert review_processed_again == 0

            assert len(tailor_runs) == 1
            assert tailor_runs[0]["status"] == "SUCCESS"
            assert tailor_runs[0]["artifact_yaml_path"]
            assert tailor_runs[0]["artifact_tex_path"]
            assert tailor_runs[0]["artifact_pdf_path"]

            review_runs = await db.get_review_runs_for_tailor_run(
                int(tailor_runs[0]["id"]),
            )
            assert len(review_runs) == 1
            assert review_runs[0]["status"] == "SUCCESS"
            assert review_runs[0]["verdict"] == "TAILORED"
            assert review_runs[0]["review_report_json"] is not None


@pytest.mark.asyncio
async def test_full_pipeline_review_failure_persists_fallback_and_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify review failure stores fallback paths and can be reclaimed.

    Purpose:
        Cover deterministic end-to-end failure/fallback behavior required by
        the test plan, including retry scheduling and later successful reclaim.
    Args:
        monkeypatch: Pytest fixture used to patch external/runtime dependencies.
    Output:
        Returns `None`; test passes when FAILED then SUCCESS review states exist.
    """

    posting = JobPosting(
        source="greenhouse_test",
        source_url="https://example.com/jobs/full-pipeline-failure",
        company="ExampleCo",
        title="Backend Intern",
        location="Remote",
        job_type="Internship",
        description="Test review failure fallback path.",
        requirements="Pursuing a BS in CS.",
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        db_path = tmp_path / "jobs.db"
        output_base_dir = tmp_path / "tailored"
        base_yaml_path, base_tex_path, base_pdf_path = _write_tailor_and_review_base_files(
            base_dir=tmp_path / "base",
        )

        _patch_discovery_for_single_greenhouse_posting(
            monkeypatch=monkeypatch,
            db_path=db_path,
            posting=posting,
        )

        async def fake_gate_decider(**_: object) -> GateRunResult:
            """Return deterministic APPLY decision for test job.

            Purpose:
                Keep this failure-path test focused on review-stage behavior.
            Args:
                **_: Ignored keyword arguments from production call site.
            Output:
                Returns deterministic APPLY gate output.
            """

            return _build_gate_result(ApplyDecision.APPLY)

        def fake_tailor_pipeline(*, invocation: Any) -> TailorRunResult:
            """Write deterministic tailor artifacts and return success.

            Purpose:
                Prepare concrete files so review failure reflects runtime logic,
                not missing artifact paths.
            Args:
                invocation: `TailorInvocationContract` from worker code.
            Output:
                Returns successful `TailorRunResult`.
            """

            work_yaml_path = Path(invocation.resume_yaml_path)
            tex_path = Path(invocation.output_tex_path)
            pdf_path = Path(invocation.output_pdf_path)
            work_yaml_path.write_text("tailored: true\n", encoding="utf-8")
            tex_path.write_text("% tailored tex\n", encoding="utf-8")
            pdf_path.write_text("% tailored pdf\n", encoding="utf-8")
            return _build_tailor_success_result(tex_path=tex_path, pdf_path=pdf_path)

        def fake_review_failure_pipeline(*, invocation: Any) -> ReviewRunResult:
            """Return deterministic hard failure for review runtime path.

            Purpose:
                Exercise review fallback and retry persistence behavior.
            Args:
                invocation: `ReviewInvocationContract` from worker code.
            Output:
                Returns failed `ReviewRunResult`.
            """

            return ReviewRunResult(
                success=False,
                hard_failure=True,
                failure_reason="simulated review runtime failure",
                review_report_path=invocation.review_report_path,
                review_report=None,
                selected_yaml_path=None,
                selected_tex_path=None,
                selected_pdf_path=None,
                agent_stdout="",
                agent_stderr="runtime failed",
            )

        def fake_review_success_pipeline(*, invocation: Any) -> ReviewRunResult:
            """Return deterministic successful review payload on retry.

            Purpose:
                Validate reclaim-and-complete behavior after one FAILED run.
            Args:
                invocation: `ReviewInvocationContract` from worker code.
            Output:
                Returns successful `ReviewRunResult`.
            """

            return _build_review_success_result(invocation=invocation)

        monkeypatch.setattr(process_new_jobs, "get_decider_model", lambda: object())
        monkeypatch.setattr(process_new_jobs, "build_root_agent", lambda model: object())
        monkeypatch.setattr(process_new_jobs, "_run_decider_for_job", fake_gate_decider)
        monkeypatch.setattr(
            process_qualified_jobs,
            "run_resume_tailor_pipeline",
            fake_tailor_pipeline,
        )
        monkeypatch.setattr(
            process_reviewed_resumes,
            "run_resume_review_pipeline",
            fake_review_failure_pipeline,
        )
        monkeypatch.setattr(
            process_reviewed_resumes,
            "_calculate_next_retry_at",
            lambda **_: PAST_RETRY_TIMESTAMP,
        )

        await discovery_main.run_job_discovery()

        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            await db.migrate_agent_schema()
            await db.migrate_tailor_schema()
            await db.migrate_review_schema()

            gate_processed = await process_new_jobs.process_once(
                db=db,
                limit=10,
                max_retries=1,
            )
            tailor_processed = await process_qualified_jobs.tailor_once(
                db=db,
                output_base_dir=output_base_dir,
                resume_yaml_path=base_yaml_path,
                max_retries=2,
                lease_seconds=DEFAULT_LEASE_SECONDS,
                backoff_seconds=DEFAULT_BACKOFF_SECONDS,
                backoff_multiplier=DEFAULT_BACKOFF_MULTIPLIER,
            )
            review_processed = await process_reviewed_resumes._review_once(
                db=db,
                output_base_dir=output_base_dir,
                base_yaml_path=base_yaml_path,
                base_tex_path=base_tex_path,
                base_pdf_path=base_pdf_path,
                max_retries=3,
                lease_seconds=DEFAULT_LEASE_SECONDS,
                backoff_seconds=DEFAULT_BACKOFF_SECONDS,
                backoff_multiplier=DEFAULT_BACKOFF_MULTIPLIER,
            )

            tailor_runs = await db.get_tailor_runs_for_job(posting.job_hash)
            assert len(tailor_runs) == 1

            review_runs_after_failure = await db.get_review_runs_for_tailor_run(
                int(tailor_runs[0]["id"]),
            )
            assert len(review_runs_after_failure) == 1
            assert review_runs_after_failure[0]["status"] == "FAILED"
            assert (
                review_runs_after_failure[0]["fallback_base_yaml_path"]
                == str(base_yaml_path)
            )
            assert (
                review_runs_after_failure[0]["fallback_base_tex_path"]
                == str(base_tex_path)
            )
            assert (
                review_runs_after_failure[0]["fallback_base_pdf_path"]
                == str(base_pdf_path)
            )
            assert (
                review_runs_after_failure[0]["next_retry_at"]
                == PAST_RETRY_TIMESTAMP
            )
            assert gate_processed == 1
            assert tailor_processed == 1
            assert review_processed == 0

            monkeypatch.setattr(
                process_reviewed_resumes,
                "run_resume_review_pipeline",
                fake_review_success_pipeline,
            )

            review_processed_after_retry = await process_reviewed_resumes._review_once(
                db=db,
                output_base_dir=output_base_dir,
                base_yaml_path=base_yaml_path,
                base_tex_path=base_tex_path,
                base_pdf_path=base_pdf_path,
                max_retries=3,
                lease_seconds=DEFAULT_LEASE_SECONDS,
                backoff_seconds=DEFAULT_BACKOFF_SECONDS,
                backoff_multiplier=DEFAULT_BACKOFF_MULTIPLIER,
            )

            review_runs_after_retry = await db.get_review_runs_for_tailor_run(
                int(tailor_runs[0]["id"]),
            )
            assert len(review_runs_after_retry) == 2
            assert review_runs_after_retry[0]["status"] == "FAILED"
            assert review_runs_after_retry[1]["status"] == "SUCCESS"
            assert review_runs_after_retry[1]["verdict"] == "TAILORED"
            assert review_processed_after_retry == 1


@pytest.mark.asyncio
async def test_tailor_to_review_claim_preserves_artifact_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify review claims receive artifact paths persisted by tailor runs.

    Purpose:
        Cover the tailor->review contract continuity gap in the test plan by
        asserting claim payload fields match persisted tailor artifacts.
    Args:
        monkeypatch: Pytest fixture used to patch tailor runtime dependency.
    Output:
        Returns `None`; test passes when claim fields carry expected artifacts.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        db_path = tmp_path / "jobs.db"
        output_base_dir = tmp_path / "tailored"
        base_yaml_path, _, _ = _write_tailor_and_review_base_files(
            base_dir=tmp_path / "base",
        )

        job = JobPosting(
            source="contract_test",
            source_url="https://example.com/jobs/contract-continuity",
            company="ContractCo",
            title="Infrastructure Intern",
            description="Tailor to review handoff contract test",
        )

        def fake_tailor_pipeline(*, invocation: Any) -> TailorRunResult:
            """Write deterministic tailor artifacts and return success.

            Purpose:
                Populate real artifact files so review claim payload can be
                validated against persisted paths.
            Args:
                invocation: `TailorInvocationContract` from worker code.
            Output:
                Returns successful `TailorRunResult`.
            """

            work_yaml_path = Path(invocation.resume_yaml_path)
            tex_path = Path(invocation.output_tex_path)
            pdf_path = Path(invocation.output_pdf_path)
            work_yaml_path.write_text("tailored: true\n", encoding="utf-8")
            tex_path.write_text("% tailored tex\n", encoding="utf-8")
            pdf_path.write_text("% tailored pdf\n", encoding="utf-8")
            return _build_tailor_success_result(tex_path=tex_path, pdf_path=pdf_path)

        monkeypatch.setattr(
            process_qualified_jobs,
            "run_resume_tailor_pipeline",
            fake_tailor_pipeline,
        )

        async with DatabaseManager(str(db_path)) as db:
            await db.create_tables()
            await db.migrate_agent_schema()
            await db.migrate_tailor_schema()
            await db.migrate_review_schema()
            await db.insert_job(job.to_db_dict())
            await db.update_job_status(job.job_hash, "QUALIFIED")

            tailor_processed = await process_qualified_jobs.tailor_once(
                db=db,
                output_base_dir=output_base_dir,
                resume_yaml_path=base_yaml_path,
                max_retries=2,
                lease_seconds=DEFAULT_LEASE_SECONDS,
                backoff_seconds=DEFAULT_BACKOFF_SECONDS,
                backoff_multiplier=DEFAULT_BACKOFF_MULTIPLIER,
            )
            claimed_review_job = await db.claim_next_review_job(max_retries=2)

            assert tailor_processed == 1
            assert claimed_review_job is not None

            claimed_yaml_path = Path(str(claimed_review_job["artifact_yaml_path"]))
            claimed_tex_path = Path(str(claimed_review_job["artifact_tex_path"]))
            claimed_pdf_path = Path(str(claimed_review_job["artifact_pdf_path"]))

            assert claimed_yaml_path.exists()
            assert claimed_tex_path.exists()
            assert claimed_pdf_path.exists()
            assert claimed_yaml_path.name == "resume_content_work.yaml"
            assert claimed_tex_path.name == "resume_tailored.tex"
            assert claimed_pdf_path.name == "resume_tailored.pdf"
