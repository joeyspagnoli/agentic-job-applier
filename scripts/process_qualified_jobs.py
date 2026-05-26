#!/usr/bin/env python3
"""Resume-tailor worker CLI shim.

The loop logic lives in ``src.workers.tailor``. This script provides the
standalone CLI entry point (argument parsing, env loading, preflight
checks, DB setup) used by the systemd unit and direct invocations.

Run once:
  python -m scripts.process_qualified_jobs

Run continuously:
  TAILOR_POLL_INTERVAL_SECONDS=30 python -m scripts.process_qualified_jobs --loop
"""

from __future__ import annotations

# Re-export every name the supervisor (and any existing tests) previously
# imported directly from this module so those import sites remain valid
# until the coordinator updates them.
from src.workers.tailor import (  # noqa: F401  re-export
    AUTONOMOUS_MODES,
    DEFAULT_CANDIDATE_PROFILE_YAML_PATH,
    DEFAULT_TAILOR_MAX_RETRIES,
    DEFAULT_TAILOR_OUTPUT_DIR,
    DEFAULT_TAILOR_POLL_INTERVAL_SECONDS,
    DEFAULT_TAILOR_RESUME_TEX_PATH,
    OPT_IN_MODE,
    TailorPreflightError,
    _check_preflight,
    _load_int_env,
    _notify_preflight_failure,
    _run_one_cycle,
    run_tailor_loop,
    tailor_once,
)

__all__ = [
    "AUTONOMOUS_MODES",
    "DEFAULT_CANDIDATE_PROFILE_YAML_PATH",
    "DEFAULT_TAILOR_MAX_RETRIES",
    "DEFAULT_TAILOR_OUTPUT_DIR",
    "DEFAULT_TAILOR_POLL_INTERVAL_SECONDS",
    "DEFAULT_TAILOR_RESUME_TEX_PATH",
    "OPT_IN_MODE",
    "TailorPreflightError",
    "_check_preflight",
    "_load_int_env",
    "_notify_preflight_failure",
    "_run_one_cycle",
    "main",
    "run_tailor_loop",
    "tailor_once",
]

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

from src.database.db_manager import DEFAULT_TAILOR_CLAIM_LEASE_SECONDS, DatabaseManager
from src.utils.paths import resolve_database_path, resolve_repo_root


async def main() -> None:
    """Parse CLI args and run the worker once or in a polling loop.

    Purpose:
        Entry point invoked by the systemd unit and CLI users. Loads env,
        validates dependencies, prepares the database, then either runs one
        pass or polls forever — both paths honor the per-stage automation
        mode read on every cycle.
    Args:
        None.
    Output:
        Returns ``None`` after the requested processing mode completes.
    """
    load_dotenv()

    if not os.environ.get("OPENAI_API_KEY"):
        logger.warning(
            "OPENAI_API_KEY is not set — tailor worker is disabled. "
            "Set OPENAI_API_KEY to enable the tailor pipeline."
        )
        if "--loop" in sys.argv:
            while True:
                await asyncio.sleep(3600)
        return

    parser = argparse.ArgumentParser(
        description="Process QUALIFIED jobs through the resume tailor pipeline",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--loop", action="store_true", help="Poll forever")
    mode_group.add_argument(
        "--once", action="store_true", help="Process once and exit (default)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=os.getenv("TAILOR_OUTPUT_DIR", DEFAULT_TAILOR_OUTPUT_DIR),
    )
    parser.add_argument(
        "--resume-tex-path",
        type=str,
        default=os.getenv("TAILOR_RESUME_TEX_PATH", DEFAULT_TAILOR_RESUME_TEX_PATH),
    )
    parser.add_argument(
        "--candidate-profile-yaml-path",
        type=str,
        default=os.getenv(
            "CANDIDATE_PROFILE_YAML_PATH", DEFAULT_CANDIDATE_PROFILE_YAML_PATH
        ),
    )
    parser.add_argument(
        "--database-path",
        type=str,
        default=None,
        help="SQLite database path (default: from DATABASE_PATH env)",
    )
    args = parser.parse_args()

    should_loop = args.loop and not args.once
    poll_interval_seconds = _load_int_env(
        "TAILOR_POLL_INTERVAL_SECONDS",
        DEFAULT_TAILOR_POLL_INTERVAL_SECONDS,
    )
    max_retries = _load_int_env("TAILOR_MAX_RETRIES", DEFAULT_TAILOR_MAX_RETRIES)
    lease_seconds = _load_int_env(
        "TAILOR_CLAIM_LEASE_SECONDS", DEFAULT_TAILOR_CLAIM_LEASE_SECONDS
    )

    try:
        _check_preflight()
    except TailorPreflightError as exc:
        logger.error("Tailor preflight failed: {}", exc)
        await _notify_preflight_failure(str(exc))
        return

    repo_root = resolve_repo_root()

    output_base_dir = Path(args.output_dir)
    if not output_base_dir.is_absolute():
        output_base_dir = repo_root / output_base_dir

    resume_tex_path = Path(args.resume_tex_path)
    if not resume_tex_path.is_absolute():
        resume_tex_path = repo_root / resume_tex_path

    candidate_profile_yaml_path = Path(args.candidate_profile_yaml_path)
    if not candidate_profile_yaml_path.is_absolute():
        candidate_profile_yaml_path = repo_root / candidate_profile_yaml_path

    if not resume_tex_path.exists():
        logger.error("Resume TeX not found: {}", resume_tex_path)
        await _notify_preflight_failure(f"Resume TeX not found: {resume_tex_path}")
        return

    if args.database_path:
        db_path = str(Path(args.database_path).resolve())
    else:
        db_path = str(resolve_database_path())

    async with DatabaseManager(db_path) as db:
        await db.create_tables()

        if not should_loop:
            await _run_one_cycle(
                db=db,
                output_base_dir=output_base_dir,
                resume_tex_path=resume_tex_path,
                candidate_profile_yaml_path=candidate_profile_yaml_path,
                max_retries=max_retries,
                lease_seconds=lease_seconds,
            )
            return

        logger.info(
            "Tailor worker entering loop: poll={}s lease={}s max_retries={}",
            poll_interval_seconds,
            lease_seconds,
            max_retries,
        )

        await run_tailor_loop(
            db=db,
            output_base_dir=output_base_dir,
            resume_tex_path=resume_tex_path,
            candidate_profile_yaml_path=candidate_profile_yaml_path,
            max_retries=max_retries,
            lease_seconds=lease_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )


if __name__ == "__main__":
    asyncio.run(main())
