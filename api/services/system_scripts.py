"""Lifecycle script dispatch helpers for `/api/system/*` endpoints."""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
from pathlib import Path

from src.utils.paths import resolve_repo_root

from api.config import SYSTEM_ACTION_FETCH_JOBS
from api.config import SYSTEM_ACTION_RESTART
from api.config import SYSTEM_ACTION_STOP
from api.config import SYSTEM_FETCH_JOBS_SCRIPT_PATH
from api.config import SYSTEM_RESTART_SCRIPT_PATH
from api.config import SYSTEM_STOP_SCRIPT_PATH

logger = logging.getLogger(__name__)


def _load_positive_int_env(name: str, default_value: int) -> int:
    """Load one positive integer environment value with fallback behavior.

    Purpose:
        Keep retry-limit and polling defaults predictable when environment
        values are missing, malformed, or invalid.
    Args:
        name: Environment variable name to read.
        default_value: Fallback value when env parsing fails.
    Output:
        Returns a strictly positive integer.
    """

    raw_value = os.getenv(name)
    if raw_value is None:
        return default_value
    try:
        parsed_value = int(raw_value)
    except ValueError:
        return default_value
    if parsed_value <= 0:
        return default_value
    return parsed_value


def _resolve_system_script_path(action: str) -> Path:
    """Resolve one lifecycle action to its canonical host script path.

    Purpose:
        Keep lifecycle endpoint command dispatch constrained to explicit
        repo-managed scripts.
    Args:
        action: Lifecycle action key (`stop` or `restart`).
    Output:
        Returns the absolute script `Path` for the action.
    Raises:
        ValueError: When action is unknown.
    """

    if action == SYSTEM_ACTION_STOP:
        return SYSTEM_STOP_SCRIPT_PATH
    if action == SYSTEM_ACTION_RESTART:
        return SYSTEM_RESTART_SCRIPT_PATH
    if action == SYSTEM_ACTION_FETCH_JOBS:
        return SYSTEM_FETCH_JOBS_SCRIPT_PATH
    raise ValueError(f"Unsupported system action: {action}")


async def _run_system_script(
    *,
    action: str,
    request_id: str,
    script_path: Path,
) -> None:
    """Run one lifecycle script in the background and log the result.

    Purpose:
        Execute operational lifecycle actions without blocking API response
        latency for the caller.
    Args:
        action: Lifecycle action key (`stop` or `restart`).
        request_id: Stable request identifier for log correlation.
        script_path: Absolute path to the script to execute.
    Output:
        Returns `None` after process completion or logging failure details.
    """

    try:
        process = await asyncio.create_subprocess_exec(
            str(script_path),
            cwd=str(resolve_repo_root()),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return_code = await process.wait()
    except OSError:
        logger.exception(
            "System action script execution failed.",
            extra={
                "action": action,
                "request_id": request_id,
                "script_path": str(script_path),
            },
        )
        return

    if return_code == 0:
        logger.info(
            "System action script completed successfully.",
            extra={"action": action, "request_id": request_id},
        )
        return

    logger.error(
        "System action script exited with non-zero status.",
        extra={
            "action": action,
            "request_id": request_id,
            "return_code": return_code,
        },
    )


def _dispatch_system_lifecycle_action(action: str) -> str:
    """Validate and dispatch one lifecycle action script asynchronously.

    Purpose:
        Keep lifecycle endpoint handlers thin while enforcing script existence,
        executable permissions, and non-blocking dispatch behavior.
    Args:
        action: Lifecycle action key (`stop` or `restart`).
    Output:
        Returns a request identifier tied to the dispatched background task.
    Raises:
        OSError: When script file is missing or not executable.
    """

    script_path = _resolve_system_script_path(action)
    if not script_path.exists():
        raise OSError(f"System action script is missing: {script_path}")
    if not script_path.is_file():
        raise OSError(f"System action script path is not a file: {script_path}")
    if not os.access(script_path, os.X_OK):
        raise OSError(f"System action script is not executable: {script_path}")

    request_id = secrets.token_hex(8)
    asyncio.create_task(
        _run_system_script(
            action=action,
            request_id=request_id,
            script_path=script_path,
        )
    )
    return request_id
