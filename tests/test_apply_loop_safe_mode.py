"""Regression tests for the SAFE_MODE → ``dry_run`` plumbing (Bug 2).

The supervisor's ``_apply_factory`` resolves ``SAFE_MODE`` at call time
and passes the boolean into ``run_apply_loop``. ``run_apply_loop`` itself
now also defaults to ``safe_mode_from_env()`` when ``dry_run is None`` so
any future in-process caller that forgets to thread the env var still
gets the correct behavior.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

import scripts.process_apply_jobs as process_apply_jobs


class _StopLoop(BaseException):
    """Sentinel raised inside the stubbed _apply_once to break the infinite poll."""


async def _force_apply_mode_active(_db: Any) -> bool:
    """Return True so the loop body executes one cycle.

    Purpose:
        Bypass the per-stage automation gate while the test only cares
        about the ``dry_run`` value passed downstream.
    """

    return True


async def _force_chrome_reachable(_cdp_url: str) -> bool:
    """Pretend Chrome is reachable so the loop proceeds to _apply_once.

    Purpose:
        Avoid touching the network while the test only cares about the
        ``dry_run`` propagation.
    """

    return True


def _build_dry_run_capture() -> tuple[list[bool], "Any"]:
    """Build a list-backed _apply_once stub that records dry_run values.

    Purpose:
        Centralize the test scaffold so each parametric case stays
        readable. The stub raises ``_StopLoop`` after capturing so the
        ``while True`` in ``run_apply_loop`` exits.
    Returns:
        ``(captured, stub)`` — the list and the stub coroutine the test
        monkeypatches in place of ``_apply_once``.
    """

    captured: list[bool] = []

    async def _stub(*, dry_run: bool, **_unused: object) -> int:
        captured.append(dry_run)
        raise _StopLoop()

    return captured, _stub


async def _run_loop_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    dry_run: bool | None,
) -> bool:
    """Drive ``run_apply_loop`` for exactly one iteration and capture ``dry_run``.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
        tmp_path: Pytest tmp dir for the artifact base.
        dry_run: Value forwarded to ``run_apply_loop`` (``None`` exercises
            the env-driven default).
    Returns:
        The ``dry_run`` value the loop body forwarded to ``_apply_once``.
    """

    captured, stub = _build_dry_run_capture()
    monkeypatch.setattr(process_apply_jobs, "_apply_once", stub)
    monkeypatch.setattr(
        process_apply_jobs, "_is_apply_mode_active", _force_apply_mode_active
    )
    monkeypatch.setattr(
        process_apply_jobs, "check_chrome_reachable", _force_chrome_reachable
    )

    with pytest.raises(_StopLoop):
        await process_apply_jobs.run_apply_loop(
            db=None,  # type: ignore[arg-type]
            output_base_dir=tmp_path,
            cdp_url="http://localhost:9222",
            dry_run=dry_run,
        )

    assert captured, "stubbed _apply_once was never invoked"
    return captured[0]


@pytest.mark.asyncio
async def test_run_apply_loop_defaults_to_safe_mode_env_when_dry_run_none(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """``dry_run=None`` resolves from ``SAFE_MODE=true`` at call time.

    Purpose:
        Lock the behavior that any caller (current or future) which omits
        ``dry_run`` gets the env-driven kill switch instead of the old
        hard-coded ``True``.
    """

    monkeypatch.setenv("SAFE_MODE", "true")
    resolved = await _run_loop_once(monkeypatch, tmp_path, dry_run=None)
    assert resolved is True


@pytest.mark.asyncio
async def test_run_apply_loop_defaults_to_false_when_safe_mode_unset(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """``dry_run=None`` resolves to ``False`` when ``SAFE_MODE`` is unset.

    Purpose:
        Confirm the default opens the auto-submit gate by default in
        production so the finisher actually runs.
    """

    monkeypatch.delenv("SAFE_MODE", raising=False)
    resolved = await _run_loop_once(monkeypatch, tmp_path, dry_run=None)
    assert resolved is False


@pytest.mark.asyncio
async def test_run_apply_loop_respects_explicit_dry_run_true(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Explicit ``dry_run=True`` wins regardless of env state.

    Purpose:
        Preserve the CLI-path contract — ``scripts/process_apply_jobs.py``
        ``main()`` still passes ``dry_run=safe_mode_from_env()`` and that
        value must propagate verbatim.
    """

    monkeypatch.setenv("SAFE_MODE", "false")
    resolved = await _run_loop_once(monkeypatch, tmp_path, dry_run=True)
    assert resolved is True


@pytest.mark.asyncio
async def test_supervisor_apply_factory_passes_safe_mode_to_loop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Supervisor's ``_apply_factory`` reads ``SAFE_MODE`` at invocation.

    Purpose:
        Lock the regression for Bug 2 — before the fix the supervisor
        called ``run_apply_loop`` without ``dry_run``, so the loop
        defaulted to ``True`` and ``SAFE_MODE=false`` was silently ignored.
    """

    from api.services import supervisor as supervisor_module

    captured: list[bool] = []

    async def _capture_run_apply_loop(
        *,
        db: object,
        output_base_dir: Path,
        cdp_url: str,
        dry_run: bool,
        **_unused: object,
    ) -> None:
        del db, output_base_dir, cdp_url, _unused
        captured.append(dry_run)

    monkeypatch.setattr(supervisor_module, "run_apply_loop", _capture_run_apply_loop)
    monkeypatch.setenv("SAFE_MODE", "false")

    class _StubConfig:
        apply_output_dir = tmp_path
        apply_cdp_url = "http://localhost:9222"

    class _StubSupervisor:
        _db = None
        _config = _StubConfig()

        async def run(self) -> None:
            await supervisor_module.LoopSupervisor._apply_factory(self)  # type: ignore[arg-type]

    await _StubSupervisor().run()

    assert captured == [False], (
        "Bug 2 regression: supervisor must pass safe_mode_from_env() through"
    )

    # And again with SAFE_MODE=true to confirm the env hop is live, not cached.
    captured.clear()
    monkeypatch.setenv("SAFE_MODE", "true")
    await _StubSupervisor().run()
    assert captured == [True]


def test_module_level_smoke() -> None:
    """Cheap import-time smoke so pytest collects this file even on bad env.

    Purpose:
        Defend against an accidental rename that would otherwise hide
        the async cases from collection (pytest-asyncio quietly skips
        them when the module fails to import).
    """

    from src.agents.apply_worker.finisher_integration import safe_mode_from_env

    assert callable(process_apply_jobs.run_apply_loop)
    assert callable(safe_mode_from_env)
    asyncio.run(asyncio.sleep(0))
