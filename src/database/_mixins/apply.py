"""Browser-apply run schema, claim, and handoff helpers.

Owns the `apply_runs` and `apply_handoffs` tables. Includes the apply
claim transaction, success/failure recorders, and the human-review
handoff transition state machine. The handoff transition reaches into
`job_postings` to keep the workflow status aligned with reviewer action.
"""

from __future__ import annotations

import os
from typing import Any
from typing import Optional

from loguru import logger

from src.database._mixins.base import _BaseMixin
from src.database._mixins.review import ClaimOwnershipError
from src.utils.json_types import JSONObject

DEFAULT_APPLY_CLAIM_LEASE_SECONDS = 1800  # Browser ops are slower than agent runs


class ApplyRunInFlightError(RuntimeError):
    """Represent a duplicate-enqueue attempt while a PENDING apply run exists.

    Raised by `enqueue_apply_run_for_job` when a non-deleted PENDING row
    already exists for the requested job hash.
    """

    def __init__(self, run_id: int, status: str) -> None:
        super().__init__(f"Apply run {run_id} is already in flight ({status})")
        self.run_id = run_id
        self.status = status


class NoReviewRunError(RuntimeError):
    """Represent a missing eligible review run for an apply-enqueue attempt.

    Raised by `enqueue_apply_run_for_job` when no SUCCESS review run
    exists for the requested job hash.
    """


class ApplyMixin(_BaseMixin):
    """Apply-run claim, success/failure, handoff, and transition helpers."""

    async def migrate_apply_schema(self) -> None:
        """Create apply_runs table and indexes when missing.

        Purpose:
            Bootstrap browser apply-run tracking idempotently so workers
            can run against databases that predate the apply stage.
        Args:
            self: The database manager performing the migration.
        Output:
            Returns `None` after ensuring apply schema exists.
        """

        # Lazy import avoids a `src.database` ↔ `src.agents` import cycle
        # (loading the schema module triggers `src.agents.__init__`).
        from src.agents.apply_worker.schemas import (  # noqa: PLC0415
            apply_outcome_check_sql,
        )

        conn = self._require_conn()
        runs_outcome_check = apply_outcome_check_sql("outcome")
        handoff_outcome_check = apply_outcome_check_sql("apply_outcome")
        await conn.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS apply_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_hash TEXT NOT NULL,
                review_run_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                resume_pdf_path TEXT,
                resume_source TEXT,
                outcome TEXT,
                confidence_score REAL,
                confidence_report_json TEXT,
                screenshot_path TEXT,
                dom_snapshot_path TEXT,
                unresolved_fields_json TEXT,
                simplify_autofill_detected BOOLEAN,
                ats_platform TEXT,
                page_url TEXT,
                error TEXT,
                next_retry_at TIMESTAMP,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                claim_token TEXT,
                CHECK (status IN ('PENDING', 'SUCCESS', 'FAILED')),
                CHECK (outcome IS NULL OR {runs_outcome_check})
            );
            CREATE INDEX IF NOT EXISTS idx_apply_runs_job_hash
                ON apply_runs(job_hash);
            CREATE INDEX IF NOT EXISTS idx_apply_runs_status
                ON apply_runs(status);
            CREATE INDEX IF NOT EXISTS idx_apply_runs_started_at
                ON apply_runs(started_at);
            CREATE INDEX IF NOT EXISTS idx_apply_runs_review_run_id
                ON apply_runs(review_run_id);
            CREATE INDEX IF NOT EXISTS idx_apply_runs_outcome
                ON apply_runs(outcome);
            CREATE TABLE IF NOT EXISTS apply_handoffs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                apply_run_id INTEGER NOT NULL UNIQUE,
                job_hash TEXT NOT NULL,
                review_run_id INTEGER NOT NULL,
                handoff_status TEXT NOT NULL DEFAULT 'PENDING_REVIEW',
                apply_outcome TEXT NOT NULL,
                resume_source TEXT,
                resume_pdf_path TEXT,
                confidence_score REAL,
                confidence_report_json TEXT,
                unresolved_fields_json TEXT,
                screenshot_path TEXT,
                dom_snapshot_path TEXT,
                ats_platform TEXT,
                page_url TEXT,
                reviewer_notes TEXT,
                reviewed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CHECK (handoff_status IN ('PENDING_REVIEW', 'APPROVED', 'REJECTED')),
                CHECK ({handoff_outcome_check})
            );
            CREATE INDEX IF NOT EXISTS idx_apply_handoffs_status
                ON apply_handoffs(handoff_status);
            CREATE INDEX IF NOT EXISTS idx_apply_handoffs_job_hash
                ON apply_handoffs(job_hash);
            CREATE INDEX IF NOT EXISTS idx_apply_handoffs_review_run_id
                ON apply_handoffs(review_run_id);
            """
        )
        # Idempotent ALTER ensures pre-existing databases pick up the
        # finisher diagnostic columns on the next startup.
        existing_cursor = await conn.execute("PRAGMA table_info(apply_handoffs)")
        existing_rows = await existing_cursor.fetchall()
        existing_columns = {str(row["name"]) for row in existing_rows}
        for column_name, column_definition in (
            ("deferred_questions_json", "TEXT"),
            ("finisher_diagnostics_json", "TEXT"),
            ("user_answers_json", "TEXT"),
        ):
            if column_name in existing_columns:
                continue
            await conn.execute(
                f"ALTER TABLE apply_handoffs ADD COLUMN {column_name} {column_definition}"
            )

        # Idempotent ALTER: add soft-delete support to apply_runs on
        # pre-existing databases.
        runs_cursor = await conn.execute("PRAGMA table_info(apply_runs)")
        runs_rows = await runs_cursor.fetchall()
        runs_columns = {str(row["name"]) for row in runs_rows}
        if "deleted_at" not in runs_columns:
            await conn.execute("ALTER TABLE apply_runs ADD COLUMN deleted_at TIMESTAMP")

        await conn.commit()
        self._apply_schema_ready = True

    async def _ensure_apply_schema_ready(self) -> None:
        """Ensure apply_runs table exists before apply queries run.

        Purpose:
            Prevent runtime SQL failures when callers use apply-specific query
            paths on databases that predate the apply schema.
        Args:
            self: The database manager validating apply-schema readiness.
        Output:
            Returns `None` after ensuring the apply schema exists.
        """

        if self._apply_schema_ready:
            return

        await self.migrate_apply_schema()

    async def claim_next_apply_job(
        self,
        *,
        max_retries: int,
        lease_seconds: int = DEFAULT_APPLY_CLAIM_LEASE_SECONDS,
    ) -> Optional[JSONObject]:
        """Atomically claim one eligible reviewed job for browser application.

        Purpose:
            Insert a PENDING apply_runs row in a BEGIN IMMEDIATE transaction so
            concurrent apply workers cannot double-claim the same review run.
        Args:
            self: The database manager performing the atomic claim.
            max_retries: Maximum FAILED apply runs allowed per review run.
            lease_seconds: Seconds a PENDING apply claim stays valid.
        Output:
            Returns merged job/review row with apply metadata keys, or `None`
            when no eligible apply candidate exists.
        Raises:
            ValueError: When `max_retries` is less than 1.
        """

        if max_retries < 1:
            raise ValueError(f"max_retries must be at least 1, got {max_retries}")

        await self._ensure_review_schema_ready()
        await self._ensure_apply_schema_ready()
        conn = self._require_conn()
        claim_token = os.urandom(32).hex()
        lease_modifier = f"-{max(lease_seconds, 1)} seconds"

        try:
            await conn.execute("BEGIN IMMEDIATE")

            candidate_cursor = await conn.execute(
                """
                SELECT
                    jp.job_hash,
                    jp.source_url,
                    jp.title,
                    jp.company,
                    jp.description,
                    rr.id AS review_run_id,
                    rr.verdict AS review_verdict,
                    rr.selected_pdf_path,
                    rr.selected_yaml_path,
                    rr.fallback_base_pdf_path
                FROM review_runs rr
                JOIN job_postings jp
                  ON jp.job_hash = rr.job_hash
                WHERE rr.status = 'SUCCESS'
                  AND rr.verdict IN ('PASS', 'TAILORED', 'BASE')
                  AND NOT EXISTS (
                      SELECT 1 FROM apply_runs ar
                      WHERE ar.review_run_id = rr.id
                        AND ar.status = 'SUCCESS'
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM apply_runs ar
                      WHERE ar.review_run_id = rr.id
                        AND ar.status = 'PENDING'
                        AND ar.started_at > datetime('now', ?)
                  )
                  -- Never re-claim a PENDING row that already has a
                  -- claim_token. User-triggered rows from
                  -- POST /api/jobs/{hash}/apply always carry one, and so
                  -- does every autonomous-claim row. Stale rows are recovered
                  -- by ``mark_stale_apply_runs_failed`` at startup, not by
                  -- the running loop.
                  AND NOT EXISTS (
                      SELECT 1 FROM apply_runs ar
                      WHERE ar.review_run_id = rr.id
                        AND ar.status = 'PENDING'
                        AND ar.claim_token IS NOT NULL
                  )
                  AND (
                      SELECT COUNT(*) FROM apply_runs ar
                      WHERE ar.review_run_id = rr.id
                        AND ar.status = 'FAILED'
                  ) < ?
                  AND COALESCE(
                      (
                          SELECT MAX(datetime(ar.next_retry_at))
                          FROM apply_runs ar
                          WHERE ar.review_run_id = rr.id
                            AND ar.status = 'FAILED'
                      ),
                      datetime('now', '-1 second')
                  ) <= datetime('now')
                ORDER BY COALESCE(rr.completed_at, rr.started_at) ASC, rr.id ASC
                LIMIT 1
                """,
                (lease_modifier, max_retries),
            )
            candidate_row = await candidate_cursor.fetchone()
            if candidate_row is None:
                await conn.rollback()
                return None

            insert_cursor = await conn.execute(
                """
                INSERT INTO apply_runs (job_hash, review_run_id, status, claim_token)
                VALUES (?, ?, 'PENDING', ?)
                RETURNING id, claim_token
                """,
                (
                    candidate_row["job_hash"],
                    candidate_row["review_run_id"],
                    claim_token,
                ),
            )
            apply_row = await insert_cursor.fetchone()
            await conn.commit()
            logger.info(
                "Claimed apply job: job_hash={} review_run_id={} apply_run_id={}",
                candidate_row["job_hash"],
                candidate_row["review_run_id"],
                apply_row["id"] if apply_row else None,
            )
        except Exception:
            await conn.rollback()
            raise

        if apply_row is None:
            return None

        merged_row = dict(candidate_row)
        merged_row["_apply_run_id"] = apply_row["id"]
        merged_row["_apply_claim_token"] = apply_row["claim_token"]
        return merged_row

    async def record_apply_success(
        self,
        *,
        run_id: int,
        claim_token: str,
        outcome: str,
        resume_pdf_path: str | None,
        resume_source: str | None,
        confidence_score: float | None,
        confidence_report_json: str | None,
        screenshot_path: str | None,
        dom_snapshot_path: str | None,
        unresolved_fields_json: str | None,
        simplify_autofill_detected: bool | None,
        ats_platform: str | None,
        page_url: str | None,
    ) -> None:
        """Mark an apply run as successful and persist all diagnostics.

        Purpose:
            Store the full application outcome, confidence report, and captured
            artifacts for user review and future agent repair.
        Args:
            self: The database manager recording apply success.
            run_id: Primary key of the apply_runs row to update.
            claim_token: Claim token that must still own the pending run.
            outcome: Application-level result value.
            resume_pdf_path: Path to the resume PDF that was uploaded.
            resume_source: Whether TAILORED or BASE resume was used.
            confidence_score: Overall confidence score in [0.0, 1.0].
            confidence_report_json: Serialized ConfidenceReport payload.
            screenshot_path: Path to the pre-submit screenshot.
            dom_snapshot_path: Path to the captured page HTML.
            unresolved_fields_json: Serialized list of unresolved field metadata.
            simplify_autofill_detected: Whether Simplify extension activated.
            ats_platform: Detected ATS platform identifier.
            page_url: Final page URL after any redirects.
        Output:
            Returns `None` after updating the apply row and committing.
        """

        await self._ensure_apply_schema_ready()
        conn = self._require_conn()
        cursor = await conn.execute(
            """
            UPDATE apply_runs
            SET status = 'SUCCESS',
                outcome = ?,
                resume_pdf_path = ?,
                resume_source = ?,
                confidence_score = ?,
                confidence_report_json = ?,
                screenshot_path = ?,
                dom_snapshot_path = ?,
                unresolved_fields_json = ?,
                simplify_autofill_detected = ?,
                ats_platform = ?,
                page_url = ?,
                error = NULL,
                next_retry_at = NULL,
                claim_token = NULL,
                completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
              AND status = 'PENDING'
              AND claim_token = ?
            """,
            (
                outcome,
                resume_pdf_path,
                resume_source,
                confidence_score,
                confidence_report_json,
                screenshot_path,
                dom_snapshot_path,
                unresolved_fields_json,
                simplify_autofill_detected,
                ats_platform,
                page_url,
                run_id,
                claim_token,
            ),
        )
        if cursor.rowcount != 1:
            raise ClaimOwnershipError(
                f"Apply run {run_id} is not owned by the provided claim token"
            )
        await conn.commit()

    async def record_apply_failure(
        self,
        *,
        run_id: int,
        claim_token: str,
        error: str,
        next_retry_at: str | None,
        outcome: str | None = None,
        screenshot_path: str | None = None,
        dom_snapshot_path: str | None = None,
        ats_platform: str | None = None,
        page_url: str | None = None,
    ) -> None:
        """Mark an apply run as failed and persist partial diagnostics.

        Purpose:
            Store failure details and any partial artifacts captured before the
            error so post-mortem analysis is possible even on failed attempts.
        Args:
            self: The database manager recording apply failure.
            run_id: Primary key of the apply_runs row to update.
            claim_token: Claim token that must still own the pending run.
            error: Failure reason text.
            next_retry_at: Optional UTC timestamp for scheduled retry.
            outcome: Optional application-level failure classification.
            screenshot_path: Path to any captured screenshot before failure.
            dom_snapshot_path: Path to any captured page HTML before failure.
            ats_platform: Detected ATS platform identifier if available.
            page_url: Final page URL if available.
        Output:
            Returns `None` after updating the apply row and committing.
        """

        await self._ensure_apply_schema_ready()
        conn = self._require_conn()
        cursor = await conn.execute(
            """
            UPDATE apply_runs
            SET status = 'FAILED',
                error = ?,
                next_retry_at = ?,
                outcome = ?,
                screenshot_path = ?,
                dom_snapshot_path = ?,
                ats_platform = ?,
                page_url = ?,
                claim_token = NULL,
                completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
              AND status = 'PENDING'
              AND claim_token = ?
            """,
            (
                error,
                next_retry_at,
                outcome,
                screenshot_path,
                dom_snapshot_path,
                ats_platform,
                page_url,
                run_id,
                claim_token,
            ),
        )
        if cursor.rowcount != 1:
            raise ClaimOwnershipError(
                f"Apply run {run_id} is not owned by the provided claim token"
            )
        await conn.commit()

    async def record_apply_handoff(
        self,
        *,
        apply_run_id: int,
        job_hash: str,
        review_run_id: int,
        apply_outcome: str,
        resume_source: str | None,
        resume_pdf_path: str | None,
        confidence_score: float | None,
        confidence_report_json: str | None,
        unresolved_fields_json: str | None,
        screenshot_path: str | None,
        dom_snapshot_path: str | None,
        ats_platform: str | None,
        page_url: str | None,
        deferred_questions_json: str | None = None,
        finisher_diagnostics_json: str | None = None,
    ) -> None:
        """Create or update a human-review handoff row for one apply attempt.

        Purpose:
            Persist a stable operator-review checkpoint keyed to apply run ID
            so dry-run outcomes can be audited and approved asynchronously.
        Args:
            self: The database manager writing the handoff checkpoint.
            apply_run_id: Primary key of the associated `apply_runs` row.
            job_hash: Stable job identifier associated with the run.
            review_run_id: Source review run that fed apply-stage eligibility.
            apply_outcome: Apply outcome enum captured from browser execution.
            resume_source: Whether TAILORED or BASE resume was used.
            resume_pdf_path: Path to the uploaded resume PDF.
            confidence_score: Final weighted confidence score.
            confidence_report_json: Serialized confidence-check breakdown.
            unresolved_fields_json: Serialized unresolved-field metadata.
            screenshot_path: Path to pre-submit screenshot artifact.
            dom_snapshot_path: Path to captured DOM snapshot artifact.
            ats_platform: Detected ATS platform slug.
            page_url: Final in-browser URL after automation steps.
            deferred_questions_json: Serialized list of questions the finisher
                could not answer autonomously and deferred for human review.
            finisher_diagnostics_json: Serialized diagnostics blob from the
                finisher pass, including `simplify_no_op` telemetry.
        Output:
            Returns `None` after upserting handoff persistence state.
        """

        await self._ensure_apply_schema_ready()
        conn = self._require_conn()
        await conn.execute(
            """
            INSERT INTO apply_handoffs (
                apply_run_id,
                job_hash,
                review_run_id,
                handoff_status,
                apply_outcome,
                resume_source,
                resume_pdf_path,
                confidence_score,
                confidence_report_json,
                unresolved_fields_json,
                screenshot_path,
                dom_snapshot_path,
                ats_platform,
                page_url,
                deferred_questions_json,
                finisher_diagnostics_json
            )
            VALUES (?, ?, ?, 'PENDING_REVIEW', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(apply_run_id) DO UPDATE SET
                job_hash = excluded.job_hash,
                review_run_id = excluded.review_run_id,
                apply_outcome = excluded.apply_outcome,
                resume_source = excluded.resume_source,
                resume_pdf_path = excluded.resume_pdf_path,
                confidence_score = excluded.confidence_score,
                confidence_report_json = excluded.confidence_report_json,
                unresolved_fields_json = excluded.unresolved_fields_json,
                screenshot_path = excluded.screenshot_path,
                dom_snapshot_path = excluded.dom_snapshot_path,
                ats_platform = excluded.ats_platform,
                page_url = excluded.page_url,
                deferred_questions_json = excluded.deferred_questions_json,
                finisher_diagnostics_json = excluded.finisher_diagnostics_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                apply_run_id,
                job_hash,
                review_run_id,
                apply_outcome,
                resume_source,
                resume_pdf_path,
                confidence_score,
                confidence_report_json,
                unresolved_fields_json,
                screenshot_path,
                dom_snapshot_path,
                ats_platform,
                page_url,
                deferred_questions_json,
                finisher_diagnostics_json,
            ),
        )
        await conn.commit()

    async def get_apply_handoffs(
        self,
        *,
        handoff_status: str | None = None,
        limit: int = 100,
    ) -> list[JSONObject]:
        """Fetch persisted apply handoffs for operator review workflows.

        Purpose:
            Provide deterministic read access to apply-stage handoff records
            for tooling and test assertions.
        Args:
            self: The database manager loading handoff rows.
            handoff_status: Optional status filter.
            limit: Maximum number of rows to return, clamped to at least 1.
        Output:
            Returns newest-first handoff rows as dictionaries.
        """

        await self._ensure_apply_schema_ready()
        conn = self._require_conn()
        safe_limit = max(limit, 1)

        if handoff_status is None:
            cursor = await conn.execute(
                """
                SELECT *
                FROM apply_handoffs
                ORDER BY COALESCE(updated_at, created_at) DESC, id DESC
                LIMIT ?
                """,
                (safe_limit,),
            )
        else:
            cursor = await conn.execute(
                """
                SELECT *
                FROM apply_handoffs
                WHERE handoff_status = ?
                ORDER BY COALESCE(updated_at, created_at) DESC, id DESC
                LIMIT ?
                """,
                (handoff_status, safe_limit),
            )

        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def mark_stale_apply_runs_failed(
        self,
        *,
        lease_seconds: int = DEFAULT_APPLY_CLAIM_LEASE_SECONDS,
    ) -> int:
        """Convert stale PENDING apply runs to FAILED on startup.

        Purpose:
            Handle worker crash recovery by marking orphaned PENDING apply runs
            failed so they become retry-eligible.
        Args:
            self: The database manager performing stale-run cleanup.
            lease_seconds: Age threshold in seconds for stale PENDING rows.
        Output:
            Returns number of rows converted to FAILED.
        """

        await self._ensure_apply_schema_ready()
        conn = self._require_conn()
        lease_modifier = f"-{max(lease_seconds, 1)} seconds"
        cursor = await conn.execute(
            """
            UPDATE apply_runs
            SET status = 'FAILED',
                error = 'stale_pending_on_startup',
                completed_at = CURRENT_TIMESTAMP
            WHERE status = 'PENDING'
              AND started_at <= datetime('now', ?)
            """,
            (lease_modifier,),
        )
        await conn.commit()
        return cursor.rowcount

    async def get_apply_failure_count(self, review_run_id: int) -> int:
        """Count FAILED apply runs for one review run identifier.

        Purpose:
            Provide efficient retry-count lookups for apply worker backoff and
            terminal-failure decisions.
        Args:
            self: The database manager querying failure counts.
            review_run_id: Review run identifier associated with apply attempts.
        Output:
            Returns number of FAILED apply_runs rows for the review run.
        """

        await self._ensure_apply_schema_ready()
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM apply_runs WHERE review_run_id = ? AND status = 'FAILED'",
            (review_run_id,),
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def transition_handoff_status(
        self,
        *,
        handoff_id: int,
        target_status: str,
        reviewer_notes: str | None = None,
    ) -> JSONObject:
        """Resolve a human-review handoff and update job status atomically.

        Purpose:
            Apply APPROVED/REJECTED decisions safely, enforce one-way handoff
            transitions, and keep job_postings status aligned with review action.
        Args:
            self: The database manager applying the transition.
            handoff_id: Primary key of the `apply_handoffs` row to resolve.
            target_status: Final handoff status (`APPROVED` or `REJECTED`).
            reviewer_notes: Optional reviewer note text.
        Output:
            Returns the resolved handoff row as a dictionary.
        Raises:
            ValueError: When the handoff does not exist or transition is invalid.
        """

        allowed_targets = {"APPROVED", "REJECTED"}
        if target_status not in allowed_targets:
            raise ValueError(f"Unsupported handoff target status: {target_status}")

        await self._ensure_apply_schema_ready()
        conn = self._require_conn()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            cursor = await conn.execute(
                "SELECT * FROM apply_handoffs WHERE id = ?",
                (handoff_id,),
            )
            handoff_row = await cursor.fetchone()
            if handoff_row is None:
                await conn.rollback()
                raise ValueError("handoff_not_found")

            current_status = str(handoff_row["handoff_status"])
            if current_status != "PENDING_REVIEW":
                await conn.rollback()
                raise ValueError("handoff_already_resolved")

            await conn.execute(
                """
                UPDATE apply_handoffs
                SET handoff_status = ?,
                    reviewer_notes = ?,
                    reviewed_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (target_status, reviewer_notes, handoff_id),
            )

            resolved_job_status = (
                "APPLIED" if target_status == "APPROVED" else "REJECTED"
            )
            await conn.execute(
                """
                UPDATE job_postings
                SET status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_hash = ?
                """,
                (resolved_job_status, handoff_row["job_hash"]),
            )

            updated_cursor = await conn.execute(
                "SELECT * FROM apply_handoffs WHERE id = ?",
                (handoff_id,),
            )
            updated_row = await updated_cursor.fetchone()
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise

        if updated_row is None:
            raise ValueError("handoff_update_failed")
        return dict(updated_row)

    async def save_handoff_user_answers(
        self,
        *,
        handoff_id: int,
        user_answers_json: str,
    ) -> JSONObject:
        """Persist reviewer-supplied answers for one human-review handoff.

        Purpose:
            Back the ``POST /api/human-review/{id}/answers`` endpoint so
            reviewers can type values for finisher-deferred Tier-3 questions
            and have them survive a page refresh. The actual resume-and-submit
            machinery is a follow-up; this call just records what the human
            wrote into ``apply_handoffs.user_answers_json``.
        Args:
            self: The database manager performing the update.
            handoff_id: Primary key of the target row.
            user_answers_json: Pre-serialized JSON payload (e.g.
                ``[{"field_id": "e368", "answer": "Female"}, ...]``).
        Output:
            Returns the updated handoff row as a dictionary.
        Raises:
            ValueError: When the handoff does not exist.
        """

        await self._ensure_apply_schema_ready()
        conn = self._require_conn()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            cursor = await conn.execute(
                "SELECT id FROM apply_handoffs WHERE id = ?",
                (handoff_id,),
            )
            if await cursor.fetchone() is None:
                await conn.rollback()
                raise ValueError("handoff_not_found")

            await conn.execute(
                """
                UPDATE apply_handoffs
                SET user_answers_json = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (user_answers_json, handoff_id),
            )
            updated_cursor = await conn.execute(
                "SELECT * FROM apply_handoffs WHERE id = ?",
                (handoff_id,),
            )
            updated_row = await updated_cursor.fetchone()
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise

        if updated_row is None:
            raise ValueError("handoff_update_failed")
        return dict(updated_row)

    async def enqueue_apply_run_for_job(self, *, job_hash: str) -> dict[str, Any]:
        """Atomically claim a user-triggered apply run for one job.

        Purpose:
            Back the ``POST /api/jobs/{hash}/apply`` endpoint. Inside a
            ``BEGIN IMMEDIATE`` transaction we (a) confirm no in-flight
            apply exists, (b) find the most recent SUCCESS review run +
            its job posting, (c) INSERT a new ``apply_runs`` row with a
            fresh ``claim_token`` so the autonomous loop never duplicates
            it, and (d) return a merged row in the same shape as
            :meth:`claim_next_apply_job` so the router can hand it
            straight to the background task that runs the browser.
        Args:
            self: The database manager performing the insert.
            job_hash: Stable deduplication hash of the target job.
        Output:
            Returns a merged dict carrying the same keys
            :meth:`claim_next_apply_job` emits: ``job_hash``,
            ``source_url``, ``title``, ``company``, ``description``,
            ``review_run_id``, ``review_verdict``,
            ``selected_pdf_path``, ``selected_yaml_path``,
            ``fallback_base_pdf_path``, plus ``_apply_run_id``,
            ``_apply_claim_token``, ``status``, and a back-compat
            ``id`` alias for callers that still read it.
        Raises:
            NoReviewRunError: When no SUCCESS review run exists for the job.
            ApplyRunInFlightError: When a non-deleted PENDING apply run for
                this job hash already exists.
        """

        await self._ensure_review_schema_ready()
        await self._ensure_apply_schema_ready()
        conn = self._require_conn()
        claim_token = os.urandom(32).hex()

        try:
            await conn.execute("BEGIN IMMEDIATE")

            # Reject if any non-deleted PENDING apply run already exists.
            inflight_cursor = await conn.execute(
                """
                SELECT id, status FROM apply_runs
                WHERE job_hash = ?
                  AND deleted_at IS NULL
                  AND status = 'PENDING'
                LIMIT 1
                """,
                (job_hash,),
            )
            inflight_row = await inflight_cursor.fetchone()
            if inflight_row is not None:
                await conn.rollback()
                raise ApplyRunInFlightError(
                    run_id=int(inflight_row["id"]),
                    status=str(inflight_row["status"]),
                )

            # Find the most recent SUCCESS review run for this job AND
            # pull the job posting + review verdict columns the worker
            # needs. One query keeps the transaction tight.
            joined_cursor = await conn.execute(
                """
                SELECT
                    jp.job_hash AS job_hash,
                    jp.source_url AS source_url,
                    jp.title AS title,
                    jp.company AS company,
                    jp.description AS description,
                    rr.id AS review_run_id,
                    rr.verdict AS review_verdict,
                    rr.selected_pdf_path AS selected_pdf_path,
                    rr.selected_yaml_path AS selected_yaml_path,
                    rr.fallback_base_pdf_path AS fallback_base_pdf_path
                FROM review_runs rr
                JOIN job_postings jp ON jp.job_hash = rr.job_hash
                WHERE rr.job_hash = ?
                  AND rr.status = 'SUCCESS'
                ORDER BY COALESCE(rr.completed_at, rr.started_at) DESC, rr.id DESC
                LIMIT 1
                """,
                (job_hash,),
            )
            joined_row = await joined_cursor.fetchone()
            if joined_row is None:
                await conn.rollback()
                raise NoReviewRunError(
                    f"No SUCCESS review run found for job_hash={job_hash!r}"
                )

            review_run_id = int(joined_row["review_run_id"])

            insert_cursor = await conn.execute(
                """
                INSERT INTO apply_runs (job_hash, review_run_id, status, claim_token)
                VALUES (?, ?, 'PENDING', ?)
                RETURNING id, status, claim_token
                """,
                (job_hash, review_run_id, claim_token),
            )
            inserted_row = await insert_cursor.fetchone()
            await conn.commit()
        except (ApplyRunInFlightError, NoReviewRunError):
            raise
        except Exception:
            await conn.rollback()
            raise

        if inserted_row is None:
            raise RuntimeError("INSERT INTO apply_runs returned no row")

        merged: dict[str, Any] = dict(joined_row)
        # Back-compat: every existing caller of
        # ``enqueue_apply_run_for_job`` reads ``result["id"]`` and
        # ``result["status"]``. Keep those keys live alongside the
        # ``_apply_*`` keys the worker expects.
        merged["id"] = int(inserted_row["id"])
        merged["status"] = str(inserted_row["status"])
        merged["_apply_run_id"] = int(inserted_row["id"])
        merged["_apply_claim_token"] = str(inserted_row["claim_token"])
        return merged

    async def enqueue_apply_run_with_base_resume(
        self,
        *,
        job_hash: str,
        base_pdf_path: str,
    ) -> dict[str, Any]:
        """Atomically enqueue an apply run that ships the base resume only.

        Purpose:
            Back the ``POST /api/jobs/{hash}/apply`` "skip tailoring"
            path. When the user clicks "Apply anyways" on a job without
            a SUCCESS review, the apply pipeline still needs a real
            ``apply_runs`` row tied to a real ``review_runs`` row tied to
            a real ``tailor_runs`` row — those NOT NULL FK relationships
            are load-bearing for the worker's claim path
            (:meth:`claim_next_apply_job`) and serialization
            (``api/routers/apply_runs.py:_serialize_apply_run_row``).
            We satisfy them by synthesizing a minimal tailor row
            (``status='SUCCESS'``, ``error='skipped_by_user'``, no
            artifacts) and a minimal review row (``status='SUCCESS'``,
            ``verdict='BASE'``, ``fallback_base_pdf_path=<pdf>``). The
            worker's ``_resolve_resume_path`` already handles
            ``verdict='BASE'`` by uploading ``fallback_base_pdf_path``
            with ``resume_source='BASE'``, so no worker changes are
            required.
        Args:
            self: The database manager performing the inserts.
            job_hash: Stable deduplication hash of the target job.
            base_pdf_path: Filesystem path to a compiled base-resume PDF
                produced by
                :func:`src.agents.resume_tailor.base_compile.compile_base_resume_pdf`.
        Output:
            Returns a merged dict in the same shape as
            :meth:`enqueue_apply_run_for_job` so the router and
            ``_spawn_user_apply_task`` need no special-case handling.
        Raises:
            ApplyRunInFlightError: When a non-deleted PENDING apply run
                for this job hash already exists.
        """

        await self._ensure_tailor_schema_ready()
        await self._ensure_review_schema_ready()
        await self._ensure_apply_schema_ready()
        conn = self._require_conn()
        claim_token = os.urandom(32).hex()

        try:
            await conn.execute("BEGIN IMMEDIATE")

            inflight_cursor = await conn.execute(
                """
                SELECT id, status FROM apply_runs
                WHERE job_hash = ?
                  AND deleted_at IS NULL
                  AND status = 'PENDING'
                LIMIT 1
                """,
                (job_hash,),
            )
            inflight_row = await inflight_cursor.fetchone()
            if inflight_row is not None:
                await conn.rollback()
                raise ApplyRunInFlightError(
                    run_id=int(inflight_row["id"]),
                    status=str(inflight_row["status"]),
                )

            job_cursor = await conn.execute(
                """
                SELECT
                    jp.job_hash AS job_hash,
                    jp.source_url AS source_url,
                    jp.title AS title,
                    jp.company AS company,
                    jp.description AS description
                FROM job_postings jp
                WHERE jp.job_hash = ?
                LIMIT 1
                """,
                (job_hash,),
            )
            job_row = await job_cursor.fetchone()
            if job_row is None:
                await conn.rollback()
                raise NoReviewRunError(
                    f"No job_postings row found for job_hash={job_hash!r}"
                )

            tailor_insert_cursor = await conn.execute(
                """
                INSERT INTO tailor_runs (
                    job_hash, status, error, completed_at, claim_token
                )
                VALUES (?, 'SUCCESS', 'skipped_by_user', CURRENT_TIMESTAMP, NULL)
                RETURNING id
                """,
                (job_hash,),
            )
            tailor_row = await tailor_insert_cursor.fetchone()
            if tailor_row is None:
                raise RuntimeError("INSERT INTO tailor_runs returned no row")
            tailor_run_id = int(tailor_row["id"])

            review_insert_cursor = await conn.execute(
                """
                INSERT INTO review_runs (
                    job_hash,
                    tailor_run_id,
                    status,
                    verdict,
                    fallback_base_pdf_path,
                    completed_at,
                    claim_token
                )
                VALUES (?, ?, 'SUCCESS', 'BASE', ?, CURRENT_TIMESTAMP, NULL)
                RETURNING id
                """,
                (job_hash, tailor_run_id, base_pdf_path),
            )
            review_row = await review_insert_cursor.fetchone()
            if review_row is None:
                raise RuntimeError("INSERT INTO review_runs returned no row")
            review_run_id = int(review_row["id"])

            apply_insert_cursor = await conn.execute(
                """
                INSERT INTO apply_runs (job_hash, review_run_id, status, claim_token)
                VALUES (?, ?, 'PENDING', ?)
                RETURNING id, status, claim_token
                """,
                (job_hash, review_run_id, claim_token),
            )
            inserted_row = await apply_insert_cursor.fetchone()
            await conn.commit()
        except (ApplyRunInFlightError, NoReviewRunError):
            raise
        except Exception:
            await conn.rollback()
            raise

        if inserted_row is None:
            raise RuntimeError("INSERT INTO apply_runs returned no row")

        merged: dict[str, Any] = dict(job_row)
        merged["review_run_id"] = review_run_id
        merged["review_verdict"] = "BASE"
        merged["selected_pdf_path"] = None
        merged["selected_yaml_path"] = None
        merged["fallback_base_pdf_path"] = base_pdf_path
        merged["id"] = int(inserted_row["id"])
        merged["status"] = str(inserted_row["status"])
        merged["_apply_run_id"] = int(inserted_row["id"])
        merged["_apply_claim_token"] = str(inserted_row["claim_token"])
        return merged

    async def get_apply_run(self, run_id: int) -> Optional[JSONObject]:
        """Fetch one apply_runs row by primary key.

        Purpose:
            Back the `GET /api/apply-runs/{id}` endpoint without forcing
            the router to assemble any join.
        Args:
            self: The database manager performing the lookup.
            run_id: Primary key of the apply_runs row.
        Output:
            Returns the row as a dict, or `None` when not found or
            soft-deleted.
        """

        await self._ensure_apply_schema_ready()
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT * FROM apply_runs WHERE id = ? AND deleted_at IS NULL",
            (run_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row is not None else None

    async def soft_delete_apply_run(self, run_id: int) -> bool:
        """Mark one apply_runs row as soft-deleted.

        Purpose:
            Free the per-job in-flight slot so new apply runs can be
            enqueued after a failure, while keeping the row for audit.
        Args:
            self: The database manager performing the soft-delete.
            run_id: Primary key of the apply_runs row.
        Output:
            Returns `True` when a row was updated, `False` when the row
            does not exist or was already soft-deleted.
        """

        await self._ensure_apply_schema_ready()
        conn = self._require_conn()
        cursor = await conn.execute(
            """
            UPDATE apply_runs
            SET deleted_at = CURRENT_TIMESTAMP
            WHERE id = ? AND deleted_at IS NULL
            """,
            (run_id,),
        )
        await conn.commit()
        return cursor.rowcount > 0
