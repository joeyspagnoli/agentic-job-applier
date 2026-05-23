"""Tailored-resume access, validation, and artifact-resolution helpers."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from fastapi import Request

from src.agents.resume_tailor.pipeline import BASE_VARIANT_NAME
from src.agents.resume_tailor.pipeline import TAILORED_V1_VARIANT_NAME
from src.agents.resume_tailor.pipeline import TAILORED_V2_VARIANT_NAME
from src.database.db_manager import DatabaseManager
from src.utils.paths import resolve_database_path
from src.utils.paths import resolve_repo_root

from api.config import JOB_HASH_PATTERN
from api.config import LOCAL_TAILORED_RESUME_CLIENT_HOSTS
from api.config import TAILORED_RESUME_FILENAME
from api.config import TAILORED_RESUME_TOKEN_ENV_KEY
from api.config import TAILORED_RESUME_TOKEN_HEADER
from api.errors import _raise_api_error

# Closed whitelist of per-variant subdirectory names the tailor pipeline emits.
# Treated as a defense-in-depth boundary alongside the job_hash regex and
# `Path.resolve(strict=True)` — anything outside this set is rejected even if
# the rest of the path shape would otherwise validate.
_VARIANT_SUBDIR_NAMES = frozenset(
    {
        BASE_VARIANT_NAME,
        TAILORED_V1_VARIANT_NAME,
        TAILORED_V2_VARIANT_NAME,
    }
)


def _validate_job_hash(job_hash: str) -> str:
    """Validate one job-hash path parameter used for artifact file access.

    Purpose:
        Prevent path traversal in job-scoped file endpoints by enforcing a
        strict lowercase-hex hash format.
    Args:
        job_hash: Raw path parameter from the incoming API request.
    Output:
        Returns the validated hash string.
    Raises:
        HTTPException: When hash format is invalid.
    """

    normalized_hash = job_hash.strip()
    if not JOB_HASH_PATTERN.fullmatch(normalized_hash):
        _raise_api_error(
            status_code=400,
            code="INVALID_JOB_HASH",
            message="job_hash must be 32-64 lowercase hexadecimal characters.",
            details={"job_hash": job_hash},
        )
    return normalized_hash


def _require_tailored_resume_access(request: Request) -> None:
    """Require local-only access or token-authenticated access to resume PDFs.

    Purpose:
        Reduce accidental resume exposure by limiting default access to local
        clients, while supporting explicit remote access via a shared secret.
        Set `TAILORED_RESUME_ALLOW_REMOTE=true` to skip the localhost check
        entirely — useful when the API is reached through Docker's port
        forward (Docker Desktop on macOS rewrites the source IP to its
        internal vpnkit proxy address, so it never looks like 127.0.0.1).
    Args:
        request: Incoming request used to inspect client host and auth header.
    Output:
        Returns `None` when request is authorized.
    Raises:
        HTTPException: When request does not satisfy access requirements.
    """

    configured_token = os.getenv(TAILORED_RESUME_TOKEN_ENV_KEY, "").strip()
    if configured_token:
        provided_token = request.headers.get(TAILORED_RESUME_TOKEN_HEADER, "").strip()
        if not secrets.compare_digest(provided_token, configured_token):
            _raise_api_error(
                status_code=401,
                code="UNAUTHORIZED",
                message="Tailored resume download token is missing or invalid.",
                details={"header": TAILORED_RESUME_TOKEN_HEADER},
            )
        return

    # Escape hatch for Docker port-forwarded deployments: when set to true the
    # localhost-only check is skipped, on the assumption that the operator has
    # already chosen the network exposure by mapping the port in docker-compose.
    if os.getenv("TAILORED_RESUME_ALLOW_REMOTE", "").strip().lower() in {"1", "true", "yes"}:
        return

    client_host = (request.client.host if request.client is not None else "").lower()
    if client_host not in LOCAL_TAILORED_RESUME_CLIENT_HOSTS:
        _raise_api_error(
            status_code=403,
            code="FORBIDDEN",
            message=(
                "Tailored resume downloads are restricted to local clients unless "
                f"{TAILORED_RESUME_TOKEN_ENV_KEY} is configured. "
                "If you reach the API through Docker port forwarding, set "
                "TAILORED_RESUME_ALLOW_REMOTE=true to disable this check."
            ),
            details={"client_host": client_host or "unknown"},
        )


def _is_safe_tailored_resume_path(*, job_hash: str, candidate_path: Path) -> bool:
    """Check whether a resolved resume path matches an expected artifact shape.

    Purpose:
        Prevent arbitrary file serving by enforcing job-scoped resume artifact
        naming and directory conventions. Accepts both the current pipeline
        layout (`<hash>/<variant>/<variant>.pdf`) and the legacy flat layout
        (`<hash>/resume_tailored.pdf`) so historical rows continue to download.
    Args:
        job_hash: Validated job hash for the requested artifact.
        candidate_path: Filesystem path candidate resolved from DB metadata.
    Output:
        Returns `True` when the path shape is acceptable, else `False`.
    """

    # Cheap structural checks first so we never touch the filesystem (`is_file`)
    # for obviously-wrong inputs like directories or non-PDF extensions.
    if not candidate_path.is_file() or candidate_path.suffix.lower() != ".pdf":
        return False

    # Current pipeline layout: `<output_dir>/<hash>/<variant>/<variant>.pdf`.
    # The variant subdir name is constrained to the closed whitelist and must
    # match the filename stem; the hash is enforced one level up. The hash is
    # already regex-validated upstream (`_validate_job_hash`), so this check
    # combined with `Path.resolve(strict=True)` defeats traversal without
    # needing a `TAILORED_RESUME_DIR` directory pin (which would conflict with
    # the worker's `TAILOR_OUTPUT_DIR` env override).
    parent_name = candidate_path.parent.name
    if (
        parent_name in _VARIANT_SUBDIR_NAMES
        and candidate_path.parent.parent.name == job_hash
        and candidate_path.name == f"{parent_name}.pdf"
    ):
        return True

    # Legacy flat layout: `<hash>/resume_tailored.pdf`. Kept for pre-variant
    # `tailor_runs` rows that still resolve through this validator. Once those
    # rows age out, this branch can be removed.
    if parent_name == job_hash and candidate_path.name == TAILORED_RESUME_FILENAME:
        return True

    return False


def _resolve_artifact_path(raw_path: str) -> Path:
    """Resolve an artifact path from DB metadata into an absolute filesystem path.

    Purpose:
        Support both absolute and legacy relative artifact paths while keeping
        all resolution deterministic.
    Args:
        raw_path: Raw artifact path string persisted in the database.
    Output:
        Returns a resolved absolute `Path`.
    Raises:
        OSError: When the candidate path does not exist.
    """

    candidate_path = Path(raw_path).expanduser()
    if not candidate_path.is_absolute():
        candidate_path = (resolve_repo_root() / candidate_path).resolve(strict=True)
        return candidate_path
    return candidate_path.resolve(strict=True)


async def _resolve_latest_tailored_resume_pdf_path(job_hash: str) -> Path | None:
    """Resolve the latest tailored-resume artifact path for one job.

    Purpose:
        Prefer the reviewer-chosen PDF (`review_runs.selected_pdf_path`)
        so a BASE / PAGE_FIT_FAILED verdict serves the base resume — the
        invariant documented in the pipeline. Fall back to
        `tailor_runs.artifact_pdf_path` for rows that predate the review
        run (or migrations with no `review_runs` row yet).
    Args:
        job_hash: Validated job hash for artifact lookup.
    Output:
        Returns a safe resolved `Path` when an artifact exists, otherwise `None`.
    Raises:
        HTTPException: When persisted path metadata fails safety validation.
    """

    db_path = str(resolve_database_path())
    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        await db.migrate_tailor_schema()
        await db.migrate_review_schema()

        assert db.conn is not None
        conn = db.conn
        artifact_cursor = await conn.execute(
            """
            SELECT COALESCE(
                (
                    SELECT rr.selected_pdf_path
                    FROM review_runs rr
                    WHERE rr.job_hash = ?
                      AND rr.status = 'SUCCESS'
                      AND COALESCE(rr.selected_pdf_path, '') <> ''
                    ORDER BY COALESCE(rr.completed_at, rr.started_at) DESC,
                             rr.id DESC
                    LIMIT 1
                ),
                (
                    SELECT tr.artifact_pdf_path
                    FROM tailor_runs tr
                    WHERE tr.job_hash = ?
                      AND tr.status = 'SUCCESS'
                      AND COALESCE(tr.artifact_pdf_path, '') <> ''
                    ORDER BY COALESCE(tr.completed_at, tr.started_at) DESC,
                             tr.id DESC
                    LIMIT 1
                )
            ) AS resolved_pdf_path
            """,
            (job_hash, job_hash),
        )
        artifact_row = await artifact_cursor.fetchone()

    if artifact_row is None:
        return None

    raw_path = str(artifact_row["resolved_pdf_path"] or "").strip()
    if raw_path == "":
        return None

    try:
        resolved_path = _resolve_artifact_path(raw_path)
    except OSError:
        return None

    if not _is_safe_tailored_resume_path(
        job_hash=job_hash, candidate_path=resolved_path
    ):
        _raise_api_error(
            status_code=500,
            code="INVALID_ARTIFACT_PATH",
            message="Tailored resume artifact path failed safety validation.",
            details={
                "job_hash": job_hash,
                "path": raw_path,
            },
        )

    return resolved_path
