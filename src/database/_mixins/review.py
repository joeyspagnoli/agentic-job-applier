"""Resume-review run schema, claim, and verdict helpers.

Owns the `review_runs` table and methods that claim a tailor success
for review, persist the verdict/report payload, and mark stale runs.
Review queries depend on tailor schema readiness, which is owned by
`TailorMixin` and exposed through `_BaseMixin`.
"""

from __future__ import annotations

import os
from typing import Optional

from loguru import logger

from src.database._mixins.base import _BaseMixin
from src.utils.json_types import JSONObject

DEFAULT_REVIEW_CLAIM_LEASE_SECONDS = 7200


class ClaimOwnershipError(RuntimeError):
    """Represent stale or mismatched claim-token completion attempts."""


class ReviewMixin(_BaseMixin):
    """Review-run claim, verdict, and history queries."""

    async def migrate_review_schema(self) -> None:
        """Create review_runs table and indexes when missing.

        Purpose:
            Bootstrap post-tailor review run tracking idempotently so workers
            can run against databases that predate the review stage.
        Args:
            self: The database manager performing the migration.
        Output:
            Returns `None` after ensuring review schema exists.
        """

        conn = self._require_conn()
        await conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS review_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_hash TEXT NOT NULL,
                tailor_run_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                verdict TEXT,
                selected_yaml_path TEXT,
                selected_tex_path TEXT,
                selected_pdf_path TEXT,
                review_report_json TEXT,
                agent_stdout TEXT,
                agent_stderr TEXT,
                error TEXT,
                next_retry_at TIMESTAMP,
                fallback_base_yaml_path TEXT,
                fallback_base_tex_path TEXT,
                fallback_base_pdf_path TEXT,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                claim_token TEXT,
                CHECK (status IN ('PENDING', 'SUCCESS', 'FAILED')),
                CHECK (verdict IS NULL OR verdict IN (
                    'PASS', 'TAILORED', 'BASE', 'FAIL',
                    'NO_IMPROVEMENT', 'PAGE_FIT_FAILED'
                ))
            );
            CREATE INDEX IF NOT EXISTS idx_review_runs_job_hash
                ON review_runs(job_hash);
            CREATE INDEX IF NOT EXISTS idx_review_runs_status
                ON review_runs(status);
            CREATE INDEX IF NOT EXISTS idx_review_runs_started_at
                ON review_runs(started_at);
            CREATE INDEX IF NOT EXISTS idx_review_runs_tailor_run_id
                ON review_runs(tailor_run_id);
            CREATE INDEX IF NOT EXISTS idx_review_runs_tailor_status
                ON review_runs(tailor_run_id, status);
            """
        )
        await self._widen_verdict_check_if_needed()
        await conn.commit()
        self._review_schema_ready = True

    async def _widen_verdict_check_if_needed(self) -> None:
        """Rebuild `review_runs` when the verdict CHECK lacks new states.

        Purpose:
            SQLite cannot alter a CHECK constraint in place. On databases
            that predate this migration, the older `CHECK (... 'FAIL')`
            blocks the new `NO_IMPROVEMENT` and `PAGE_FIT_FAILED` verdicts,
            so the table is rebuilt with the widened CHECK and existing
            rows are copied over verbatim.
        Args:
            self: The database manager performing the rebuild.
        Output:
            Returns `None` after either rebuilding the table or detecting
            that the migration has already run.
        """

        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='review_runs'"
        )
        row = await cursor.fetchone()
        if row is None:
            return
        existing_sql = str(row["sql"] or "")
        if "'NO_IMPROVEMENT'" in existing_sql and "'PAGE_FIT_FAILED'" in existing_sql:
            return

        await conn.executescript(
            """
            CREATE TABLE review_runs__new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_hash TEXT NOT NULL,
                tailor_run_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                verdict TEXT,
                selected_yaml_path TEXT,
                selected_tex_path TEXT,
                selected_pdf_path TEXT,
                review_report_json TEXT,
                agent_stdout TEXT,
                agent_stderr TEXT,
                error TEXT,
                next_retry_at TIMESTAMP,
                fallback_base_yaml_path TEXT,
                fallback_base_tex_path TEXT,
                fallback_base_pdf_path TEXT,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                claim_token TEXT,
                CHECK (status IN ('PENDING', 'SUCCESS', 'FAILED')),
                CHECK (verdict IS NULL OR verdict IN (
                    'PASS', 'TAILORED', 'BASE', 'FAIL',
                    'NO_IMPROVEMENT', 'PAGE_FIT_FAILED'
                ))
            );
            INSERT INTO review_runs__new
            SELECT * FROM review_runs;
            DROP TABLE review_runs;
            ALTER TABLE review_runs__new RENAME TO review_runs;
            CREATE INDEX IF NOT EXISTS idx_review_runs_job_hash
                ON review_runs(job_hash);
            CREATE INDEX IF NOT EXISTS idx_review_runs_status
                ON review_runs(status);
            CREATE INDEX IF NOT EXISTS idx_review_runs_started_at
                ON review_runs(started_at);
            CREATE INDEX IF NOT EXISTS idx_review_runs_tailor_run_id
                ON review_runs(tailor_run_id);
            CREATE INDEX IF NOT EXISTS idx_review_runs_tailor_status
                ON review_runs(tailor_run_id, status);
            """
        )

    async def _ensure_review_schema_ready(self) -> None:
        """Ensure review_runs table exists before review queries run.

        Purpose:
            Prevent runtime SQL failures when callers use review-specific query
            paths on databases that predate the review schema.
        Args:
            self: The database manager validating review-schema readiness.
        Output:
            Returns `None` after ensuring the review schema exists.
        """

        if self._review_schema_ready:
            return

        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='review_runs'"
        )
        row = await cursor.fetchone()
        if row is not None:
            self._review_schema_ready = True
            return

        await self.migrate_review_schema()

    async def claim_next_review_job(
        self,
        *,
        max_retries: int,
        lease_seconds: int = DEFAULT_REVIEW_CLAIM_LEASE_SECONDS,
    ) -> Optional[JSONObject]:
        """Atomically claim one eligible tailor SUCCESS run for review.

        Purpose:
            Insert a PENDING review_runs row in a BEGIN IMMEDIATE transaction so
            concurrent review workers cannot double-claim the same tailor run.
        Args:
            self: The database manager performing the atomic claim.
            max_retries: Maximum FAILED review runs allowed per tailor run.
            lease_seconds: Seconds a PENDING review claim stays valid.
        Output:
            Returns merged job/tailor row with review metadata keys, or `None`
            when no eligible review candidate exists.
        Raises:
            ValueError: When `max_retries` is less than 1.
        """

        if max_retries < 1:
            raise ValueError(f"max_retries must be at least 1, got {max_retries}")

        await self._ensure_tailor_schema_ready()
        await self._ensure_review_schema_ready()
        conn = self._require_conn()
        claim_token = os.urandom(32).hex()
        lease_modifier = f"-{max(lease_seconds, 1)} seconds"

        try:
            await conn.execute("BEGIN IMMEDIATE")

            candidate_cursor = await conn.execute(
                """
                SELECT
                    jp.*,
                    tr.id AS tailor_run_id,
                    tr.artifact_yaml_path,
                    tr.artifact_tex_path,
                    tr.artifact_pdf_path
                FROM tailor_runs tr
                JOIN job_postings jp
                  ON jp.job_hash = tr.job_hash
                WHERE tr.status = 'SUCCESS'
                  AND NOT EXISTS (
                      SELECT 1 FROM review_runs rr
                      WHERE rr.tailor_run_id = tr.id
                        AND rr.status = 'SUCCESS'
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM review_runs rr
                      WHERE rr.tailor_run_id = tr.id
                        AND rr.status = 'PENDING'
                        AND rr.started_at > datetime('now', ?)
                  )
                  AND (
                      SELECT COUNT(*) FROM review_runs rr
                      WHERE rr.tailor_run_id = tr.id
                        AND rr.status = 'FAILED'
                  ) < ?
                  AND COALESCE(
                      (
                          SELECT MAX(rr.next_retry_at)
                          FROM review_runs rr
                          WHERE rr.tailor_run_id = tr.id
                            AND rr.status = 'FAILED'
                      ),
                      datetime('now', '-1 second')
                  ) <= datetime('now')
                ORDER BY COALESCE(tr.completed_at, tr.started_at) ASC, tr.id ASC
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
                INSERT INTO review_runs (job_hash, tailor_run_id, status, claim_token)
                VALUES (?, ?, 'PENDING', ?)
                RETURNING id, claim_token
                """,
                (
                    candidate_row["job_hash"],
                    candidate_row["tailor_run_id"],
                    claim_token,
                ),
            )
            review_row = await insert_cursor.fetchone()
            await conn.commit()
            logger.info(
                "Claimed review job: job_hash={} tailor_run_id={} review_run_id={}",
                candidate_row["job_hash"],
                candidate_row["tailor_run_id"],
                review_row["id"] if review_row else None,
            )
        except Exception:
            await conn.rollback()
            raise

        if review_row is None:
            return None

        merged_row = dict(candidate_row)
        merged_row["_review_run_id"] = review_row["id"]
        merged_row["_review_claim_token"] = review_row["claim_token"]
        return merged_row

    async def record_review_success(
        self,
        *,
        run_id: int,
        claim_token: str,
        verdict: str,
        selected_yaml_path: str | None,
        selected_tex_path: str | None,
        selected_pdf_path: str | None,
        review_report_json: str,
        agent_stdout: str | None,
        agent_stderr: str | None,
    ) -> None:
        """Mark a review run as successful and persist verdict artifacts.

        Purpose:
            Store the agent-authored verdict/report payload and selected resume
            references for downstream pipeline continuation.
        Args:
            self: The database manager recording review success.
            run_id: Primary key of the review_runs row to update.
            claim_token: Claim token that must still own the pending run.
            verdict: Agent-selected review verdict value.
            selected_yaml_path: Selected resume YAML path from report.
            selected_tex_path: Selected resume TeX path from report.
            selected_pdf_path: Selected resume PDF path from report.
            review_report_json: Canonical serialized review report JSON.
            agent_stdout: Raw pi subprocess stdout for diagnostics.
            agent_stderr: Raw pi subprocess stderr for diagnostics.
        Output:
            Returns `None` after updating review row and committing.
        """

        await self._ensure_review_schema_ready()
        conn = self._require_conn()
        cursor = await conn.execute(
            """
            UPDATE review_runs
            SET status = 'SUCCESS',
                verdict = ?,
                selected_yaml_path = ?,
                selected_tex_path = ?,
                selected_pdf_path = ?,
                review_report_json = ?,
                agent_stdout = ?,
                agent_stderr = ?,
                error = NULL,
                next_retry_at = NULL,
                claim_token = NULL,
                completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
              AND status = 'PENDING'
              AND claim_token = ?
            """,
            (
                verdict,
                selected_yaml_path,
                selected_tex_path,
                selected_pdf_path,
                review_report_json,
                agent_stdout,
                agent_stderr,
                run_id,
                claim_token,
            ),
        )
        if cursor.rowcount != 1:
            raise ClaimOwnershipError(
                f"Review run {run_id} is not owned by the provided claim token"
            )
        await conn.commit()

    async def record_review_failure(
        self,
        *,
        run_id: int,
        claim_token: str,
        error: str,
        next_retry_at: str | None,
        agent_stdout: str | None,
        agent_stderr: str | None,
        fallback_base_yaml_path: str,
        fallback_base_tex_path: str,
        fallback_base_pdf_path: str,
    ) -> None:
        """Mark a review run as failed and persist fallback/base diagnostics.

        Purpose:
            Store hard-runtime failure details and base fallback references so
            downstream stages can continue without blocking on review retries.
        Args:
            self: The database manager recording review failure.
            run_id: Primary key of the review_runs row to update.
            claim_token: Claim token that must still own the pending run.
            error: Failure reason text.
            next_retry_at: Optional UTC timestamp for scheduled retry.
            agent_stdout: Raw pi subprocess stdout for diagnostics.
            agent_stderr: Raw pi subprocess stderr for diagnostics.
            fallback_base_yaml_path: Base YAML fallback path.
            fallback_base_tex_path: Base TeX fallback path.
            fallback_base_pdf_path: Base PDF fallback path.
        Output:
            Returns `None` after updating review row and committing.
        """

        await self._ensure_review_schema_ready()
        conn = self._require_conn()
        cursor = await conn.execute(
            """
            UPDATE review_runs
            SET status = 'FAILED',
                error = ?,
                next_retry_at = ?,
                agent_stdout = ?,
                agent_stderr = ?,
                fallback_base_yaml_path = ?,
                fallback_base_tex_path = ?,
                fallback_base_pdf_path = ?,
                claim_token = NULL,
                completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
              AND status = 'PENDING'
              AND claim_token = ?
            """,
            (
                error,
                next_retry_at,
                agent_stdout,
                agent_stderr,
                fallback_base_yaml_path,
                fallback_base_tex_path,
                fallback_base_pdf_path,
                run_id,
                claim_token,
            ),
        )
        if cursor.rowcount != 1:
            raise ClaimOwnershipError(
                f"Review run {run_id} is not owned by the provided claim token"
            )
        await conn.commit()

    async def mark_stale_review_runs_failed(
        self,
        *,
        lease_seconds: int = DEFAULT_REVIEW_CLAIM_LEASE_SECONDS,
    ) -> int:
        """Convert stale PENDING review runs to FAILED on startup.

        Purpose:
            Handle worker crash recovery by marking orphaned PENDING review runs
            failed so they become retry-eligible.
        Args:
            self: The database manager performing stale-run cleanup.
            lease_seconds: Age threshold in seconds for stale PENDING rows.
        Output:
            Returns number of rows converted to FAILED.
        """

        await self._ensure_review_schema_ready()
        conn = self._require_conn()
        lease_modifier = f"-{max(lease_seconds, 1)} seconds"
        cursor = await conn.execute(
            """
            UPDATE review_runs
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

    async def get_review_failure_count(self, tailor_run_id: int) -> int:
        """Count FAILED review runs for one tailor run identifier.

        Purpose:
            Provide efficient retry-count lookups for review worker backoff and
            terminal-failure decisions.
        Args:
            tailor_run_id: Tailor run identifier associated with review attempts.
        Output:
            Returns number of FAILED review_runs rows for the tailor run.
        """

        await self._ensure_review_schema_ready()
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM review_runs WHERE tailor_run_id = ? AND status = 'FAILED'",
            (tailor_run_id,),
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def get_review_runs_for_tailor_run(
        self,
        tailor_run_id: int,
    ) -> list[JSONObject]:
        """Fetch review run history for one tailor run.

        Purpose:
            Support tests and operational diagnostics for post-tailor review
            retries and verdict progression.
        Args:
            tailor_run_id: Tailor run identifier to inspect.
        Output:
            Returns review_runs rows ordered by started_at ascending.
        """

        await self._ensure_review_schema_ready()
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT * FROM review_runs WHERE tailor_run_id = ? ORDER BY started_at ASC",
            (tailor_run_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
