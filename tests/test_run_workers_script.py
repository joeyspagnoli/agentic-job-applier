"""Validate worker supervisor script behavior on child process failures.

Purpose:
    Ensure the local multi-worker supervisor script stops sibling workers and
    exits with the failing child's status code when one worker crashes.
"""

from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path

SCRIPT_PATH = Path("scripts/docker/run_workers.sh")


def _write_fake_uv(
    *,
    uv_path: Path,
    marker_path: Path,
    gate_pid_path: Path,
) -> None:
    """Create a fake `uv` executable for deterministic worker-script tests.

    Purpose:
        Simulate one long-running gate worker and one crashing tailor worker so
        the supervisor's wait/cleanup behavior can be asserted deterministically.
    Args:
        uv_path: Output path for the fake executable.
        marker_path: File receiving lifecycle markers from fake workers.
        gate_pid_path: File storing the gate worker PID for test cleanup.
    Output:
        Returns `None` after writing and chmod'ing the fake executable.
    """

    script_text = f"""#!/usr/bin/env bash
set -euo pipefail

if [[ "$*" == *"scripts.process_new_jobs"* ]]; then
  echo gate_started >> "{marker_path}"
  echo $$ > "{gate_pid_path}"
  trap 'echo gate_terminated >> "{marker_path}"; exit 0' TERM INT
  while true; do sleep 1; done
fi

if [[ "$*" == *"scripts.process_qualified_jobs"* ]]; then
  echo tailor_failed >> "{marker_path}"
  exit 17
fi

echo unexpected_worker >> "{marker_path}"
exit 0
"""
    uv_path.write_text(script_text, encoding="utf-8")
    uv_path.chmod(0o755)


def _terminate_pid_file(pid_path: Path) -> None:
    """Terminate one PID recorded in a file if that process is still alive.

    Purpose:
        Keep the test hermetic by cleaning up any fake worker process that may
        remain if the supervisor script regresses.
    Args:
        pid_path: Path containing one process ID string.
    Output:
        Returns `None` after best-effort process termination.
    """

    if not pid_path.exists():
        return

    pid_text = pid_path.read_text(encoding="utf-8").strip()
    if pid_text == "":
        return

    pid = int(pid_text)
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return


def test_run_workers_stops_siblings_after_nonzero_child_exit(tmp_path: Path) -> None:
    """Verify supervisor kills sibling workers and returns failing exit code.

    Purpose:
        Regress H-006 by proving `run_workers.sh` still performs cleanup when
        one worker exits non-zero under `set -euo pipefail`.
    Args:
        tmp_path: Pytest temporary directory fixture.
    Output:
        Returns `None`; test passes when siblings are terminated and code is 17.
    """

    fake_bin_dir = tmp_path / "bin"
    fake_bin_dir.mkdir(parents=True, exist_ok=True)
    marker_path = tmp_path / "worker_markers.log"
    gate_pid_path = tmp_path / "gate.pid"
    fake_uv_path = fake_bin_dir / "uv"
    _write_fake_uv(
        uv_path=fake_uv_path,
        marker_path=marker_path,
        gate_pid_path=gate_pid_path,
    )

    env = dict(os.environ)
    env["PATH"] = f"{fake_bin_dir}:{env.get('PATH', '')}"
    env["WORKERS"] = "gate,tailor"

    try:
        completed = subprocess.run(
            ["bash", str(SCRIPT_PATH)],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    finally:
        _terminate_pid_file(gate_pid_path)

    assert completed.returncode == 17
    markers = marker_path.read_text(encoding="utf-8").splitlines()
    assert "gate_started" in markers
    assert "tailor_failed" in markers
    assert "gate_terminated" in markers
