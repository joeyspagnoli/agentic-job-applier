"""Failure-reset helpers for requeueing jobs across pipeline stages.

Each method clears terminal failure markers for one stage so an operator
can deliberately retry a job that exhausted automatic retries. The
methods cross stage boundaries (gate -> tailor -> review -> apply), so
they live in their own mixin instead of being scattered.
"""

from __future__ import annotations

from src.database._mixins.base import _BaseMixin


class FailureResetsMixin(_BaseMixin):
    """Operator-facing requeue actions for the four pipeline stages."""

    async def reset_agent_failure_state(self, job_hash: str) -> None:
        """Requeue a terminally failed job back into NEW processing backlog.

        Purpose:
            Provide an explicit operator action for retrying jobs that failed
            terminally after the automated retry limit.
        Args:
            self: The database manager requeueing the target job.
            job_hash: Stable deduplication hash for the target job.
        Output:
            Returns `None` after clearing failure metadata and committing.
        """

        await self._ensure_agent_schema_ready()
        conn = self._require_conn()

        await conn.execute(
            """
            UPDATE job_postings
            SET status = 'NEW',
                agent_failed_at = NULL,
                agent_error = NULL,
                agent_retry_count = 0,
                agent_next_retry_at = NULL,
                agent_claim_token = NULL,
                agent_claimed_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE job_hash = ?
            """,
            (job_hash,),
        )
        await conn.commit()

    async def reset_tailor_failure_state(self, *, job_hash: str) -> None:
        """Delete FAILED tailor runs for a job so it can be requeued.

        Purpose:
            Provide an operator-facing action for retrying a job that
            exhausted its tailor retry limit or was manually rejected.
        Args:
            self: The database manager clearing the failure state.
            job_hash: Stable deduplication hash for the target job.
        Output:
            Returns `None` after deleting FAILED rows and committing.
        """

        await self._ensure_tailor_schema_ready()
        conn = self._require_conn()
        await conn.execute(
            "DELETE FROM tailor_runs WHERE job_hash = ? AND status = 'FAILED'",
            (job_hash,),
        )
        await conn.commit()

    async def reset_review_failure_state(self, *, job_hash: str) -> int:
        """Delete FAILED review runs for all tailor runs linked to one job.

        Purpose:
            Requeue review-stage failures by removing terminal FAILED rows so
            claim queries can pick the same tailor output again.
        Args:
            self: The database manager clearing review failure rows.
            job_hash: Stable job identifier tied to related tailor runs.
        Output:
            Returns the number of deleted FAILED review rows.
        """

        await self._ensure_review_schema_ready()
        conn = self._require_conn()
        cursor = await conn.execute(
            """
            DELETE FROM review_runs
            WHERE status = 'FAILED'
              AND tailor_run_id IN (
                  SELECT id FROM tailor_runs WHERE job_hash = ?
              )
            """,
            (job_hash,),
        )
        await conn.commit()
        return cursor.rowcount

    async def reset_apply_failure_state(self, *, job_hash: str) -> int:
        """Delete FAILED apply runs for all review runs linked to one job.

        Purpose:
            Requeue apply-stage failures by removing terminal FAILED rows so
            claim queries can process the same review result again.
        Args:
            self: The database manager clearing apply failure rows.
            job_hash: Stable job identifier tied to related review runs.
        Output:
            Returns the number of deleted FAILED apply rows.
        """

        await self._ensure_apply_schema_ready()
        conn = self._require_conn()
        cursor = await conn.execute(
            """
            DELETE FROM apply_runs
            WHERE status = 'FAILED'
              AND review_run_id IN (
                  SELECT id FROM review_runs WHERE job_hash = ?
              )
            """,
            (job_hash,),
        )
        await conn.commit()
        return cursor.rowcount
