"""In-process asyncio supervisor for the four pipeline loops.

This module owns the lifecycle of the discovery, gate, tailor, and apply
worker loops when they run inside the FastAPI process instead of in
separate worker containers. The supervisor:

* always runs the discovery loop (no LLM spend, never user-gated)
* runs the gate / tailor / apply loops only when the user has the
  autonomous toggle ON, mapped to per-stage automation mode rows of
  ``both`` (loops + button clicks both active)
* reacts to mode flips through ``notify_mode_changed`` so toggling the
  UI starts or cancels gated loops within ``MODE_WATCH_POLL_SECONDS``
* restarts a failed worker with bounded exponential backoff so a
  transient exception does not silently disable a stage for the rest
  of the process lifetime
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from src.database._mixins.system_settings import APPLY_MODE_KEY
from src.database._mixins.system_settings import AUTOMATION_STAGE_KEYS
from src.database._mixins.system_settings import GATE_MODE_KEY
from src.database._mixins.system_settings import TAILOR_MODE_KEY
from src.database.db_manager import DatabaseManager
from src.utils.paths import resolve_database_path
from src.utils.paths import resolve_repo_root

from main import DEFAULT_DISCOVERY_INTERVAL_MINUTES
from main import run_discovery_loop
from scripts.process_apply_jobs import DEFAULT_APPLY_OUTPUT_DIR
from scripts.process_apply_jobs import run_apply_loop
from scripts.process_new_jobs import run_gate_loop
from scripts.process_qualified_jobs import (
    DEFAULT_CANDIDATE_PROFILE_YAML_PATH,
    DEFAULT_TAILOR_OUTPUT_DIR,
    DEFAULT_TAILOR_RESUME_TEX_PATH,
    run_tailor_loop,
)

logger = logging.getLogger(__name__)

# Stages that map onto the autonomous toggle. Discovery is intentionally
# excluded — it always runs and is owned by the supervisor directly.
GATED_STAGE_KEYS: tuple[str, ...] = (
    GATE_MODE_KEY,
    TAILOR_MODE_KEY,
    APPLY_MODE_KEY,
)

# Stage names used internally so log messages and the active-stage map
# read consistently. These are NOT user-facing strings — the UI only
# sees the global autonomous toggle.
STAGE_NAME_DISCOVERY = "discovery"
STAGE_NAME_GATE = "gate"
STAGE_NAME_TAILOR = "tailor"
STAGE_NAME_APPLY = "apply"

# Modes that map onto "loop is active".
_ACTIVE_LOOP_MODES: frozenset[str] = frozenset({"autonomous", "both"})

# Initial and ceiling backoff seconds when a worker raises a non-cancel
# exception. The loops themselves catch most exceptions per-cycle, so
# this only fires for unexpected escapes (e.g., import-time failures).
_RESTART_BACKOFF_INITIAL_SECONDS = 5
_RESTART_BACKOFF_MAX_SECONDS = 300

# How frequently the mode watcher polls the database when no explicit
# ``notify_mode_changed`` call has fired. Acts as a safety net for
# external mutations (CLI/SQL edits) that bypass the API router.
MODE_WATCH_POLL_SECONDS = 30

# How frequently the watcher checks the mode-change event so a UI flip
# is reflected in active tasks within this many seconds.
_MODE_WATCH_EVENT_TIMEOUT_SECONDS = 1.5


def _resolve_path(default_value: str, env_value: str | None) -> Path:
    """Resolve a configurable path against the repo root.

    Purpose:
        Centralize the "resolve relative to repo root" rule so worker
        config paths read by the supervisor follow the same convention
        as the standalone CLI entry points.
    Args:
        default_value: Repo-relative default path used when env is unset.
        env_value: Optional override pulled from environment.
    Output:
        Returns an absolute resolved `Path`.
    """

    raw = env_value if env_value not in (None, "") else default_value
    candidate = Path(raw)  # type: ignore[arg-type]
    if not candidate.is_absolute():
        candidate = (resolve_repo_root() / candidate).resolve()
    return candidate


@dataclass(frozen=True)
class SupervisorConfig:
    """Resolved worker-loop configuration consumed by the supervisor.

    Purpose:
        Capture the small set of paths and tuning knobs the supervisor
        needs in one immutable bundle so tests can construct an instance
        without monkeypatching environment variables.
    """

    discovery_interval_minutes: int
    tailor_output_dir: Path
    tailor_resume_tex_path: Path
    tailor_candidate_profile_yaml_path: Path
    apply_output_dir: Path
    apply_cdp_url: str


def _load_int_env(name: str, default_value: int) -> int:
    """Parse a positive integer env var with a safe fallback.

    Purpose:
        Mirror the worker-script `_load_int_env` semantics so identical
        env vars produce identical effective values regardless of which
        entry point (supervisor vs. CLI) reads them.
    Args:
        name: Environment variable name.
        default_value: Fallback value when parsing fails or is non-positive.
    Output:
        Returns the parsed positive integer or the default.
    """

    raw = os.getenv(name)
    if raw is None:
        return default_value
    try:
        parsed = int(raw)
    except ValueError:
        return default_value
    if parsed <= 0:
        return default_value
    return parsed


def build_config_from_env() -> SupervisorConfig:
    """Build the supervisor config snapshot from process environment.

    Purpose:
        Provide a single place that translates env vars into the
        resolved paths and tuning knobs the supervisor passes to each
        worker loop, so tests can substitute a hand-built instance.
    Args:
        None.
    Output:
        Returns a `SupervisorConfig` snapshot pinned to current env.
    """

    discovery_interval_minutes = _load_int_env(
        "RUN_INTERVAL_MINUTES",
        DEFAULT_DISCOVERY_INTERVAL_MINUTES,
    )
    tailor_output_dir = _resolve_path(
        DEFAULT_TAILOR_OUTPUT_DIR,
        os.getenv("TAILOR_OUTPUT_DIR"),
    )
    tailor_resume_tex_path = _resolve_path(
        DEFAULT_TAILOR_RESUME_TEX_PATH,
        os.getenv("TAILOR_RESUME_TEX_PATH"),
    )
    tailor_candidate_profile_yaml_path = _resolve_path(
        DEFAULT_CANDIDATE_PROFILE_YAML_PATH,
        os.getenv("CANDIDATE_PROFILE_YAML_PATH"),
    )
    apply_output_dir = _resolve_path(
        DEFAULT_APPLY_OUTPUT_DIR,
        os.getenv("APPLY_OUTPUT_DIR"),
    )
    apply_cdp_url = os.getenv(
        "CHROME_CDP_URL", "http://host.docker.internal:9222"
    ).strip()

    return SupervisorConfig(
        discovery_interval_minutes=discovery_interval_minutes,
        tailor_output_dir=tailor_output_dir,
        tailor_resume_tex_path=tailor_resume_tex_path,
        tailor_candidate_profile_yaml_path=tailor_candidate_profile_yaml_path,
        apply_output_dir=apply_output_dir,
        apply_cdp_url=apply_cdp_url,
    )


class LoopSupervisor:
    """Lifecycle manager for the four pipeline asyncio loops.

    Purpose:
        Run discovery unconditionally and gate/tailor/apply based on the
        per-stage automation mode rows. Exposes ``notify_mode_changed``
        so the API can immediately reconcile active tasks after the
        autonomous toggle flips.
    """

    def __init__(
        self,
        *,
        db: DatabaseManager,
        config: SupervisorConfig,
    ) -> None:
        """Capture the shared dependencies for the supervisor.

        Purpose:
            Bind one DB connection (reused across loops to avoid SQLite
            file-lock contention) and the resolved config snapshot so
            ``start`` can wire up tasks deterministically.
        Args:
            db: Connected database manager, owned by the API lifespan.
            config: Pre-resolved worker config.
        Output:
            Returns `None`.
        """

        self._db = db
        self._config = config
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._mode_changed = asyncio.Event()
        self._stopped = False

    def notify_mode_changed(self) -> None:
        """Wake the mode watcher so toggle flips reconcile immediately.

        Purpose:
            The router calls this after writing new automation-mode
            rows; the watcher then re-reads the modes and starts or
            cancels gated loops accordingly without waiting for the
            periodic safety-net poll.
        Args:
            None.
        Output:
            Returns `None`.
        """

        self._mode_changed.set()

    async def start(self) -> None:
        """Spawn the discovery loop, gated loops, and mode watcher.

        Purpose:
            Kick off all asyncio tasks the supervisor owns. Idempotent
            in the sense that double-starting is a programming error;
            it raises a `RuntimeError` to surface the bug.
        Args:
            None.
        Output:
            Returns `None`.
        Raises:
            RuntimeError: When the supervisor has already been started.
        """

        if self._tasks:
            raise RuntimeError("LoopSupervisor.start called twice")

        self._stopped = False
        logger.info("Supervisor starting: discovery + mode-gated loops")

        self._spawn(STAGE_NAME_DISCOVERY, self._discovery_factory)
        await self._reconcile_gated_loops()
        self._spawn("mode_watcher", self._mode_watcher_factory)

    async def stop(self) -> None:
        """Cancel every supervised task and wait for cleanup.

        Purpose:
            Drain all in-flight asyncio tasks during FastAPI shutdown so
            the process does not leave dangling work behind.
        Args:
            None.
        Output:
            Returns `None`.
        """

        self._stopped = True
        logger.info("Supervisor stopping; cancelling {} task(s)", len(self._tasks))
        for task in self._tasks.values():
            task.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()

    @property
    def active_stages(self) -> tuple[str, ...]:
        """Return the currently running supervised stage names.

        Purpose:
            Surface the live set of running loops for diagnostics and
            for the status router so the dashboard can show what is
            actually executing rather than what the settings rows say.
        Args:
            None.
        Output:
            Returns a tuple of stage-name strings.
        """

        return tuple(sorted(self._tasks.keys()))

    async def _reconcile_gated_loops(self) -> None:
        """Start or cancel gated loops so they match the stored modes.

        Purpose:
            Single reconcile step shared between startup and the mode
            watcher; reading the rows once and diffing keeps the watcher
            cheap and avoids racing the start path.
        Args:
            None.
        Output:
            Returns `None`.
        """

        modes = await self._read_stage_modes()

        # Map each gated stage to its loop factory. The factories close
        # over `self`/`self._config` so the supervisor remains the only
        # source of loop parameters.
        gated_factories: dict[str, Callable[[], Awaitable[None]]] = {
            STAGE_NAME_GATE: self._gate_factory,
            STAGE_NAME_TAILOR: self._tailor_factory,
            STAGE_NAME_APPLY: self._apply_factory,
        }
        stage_to_mode_key: dict[str, str] = {
            STAGE_NAME_GATE: GATE_MODE_KEY,
            STAGE_NAME_TAILOR: TAILOR_MODE_KEY,
            STAGE_NAME_APPLY: APPLY_MODE_KEY,
        }

        for stage_name, factory in gated_factories.items():
            should_run = modes.get(stage_to_mode_key[stage_name]) in _ACTIVE_LOOP_MODES
            is_running = stage_name in self._tasks
            if should_run and not is_running:
                logger.info("Supervisor: starting {} loop (mode permits)", stage_name)
                self._spawn(stage_name, factory)
            elif not should_run and is_running:
                logger.info("Supervisor: cancelling {} loop (mode opted out)", stage_name)
                await self._cancel_task(stage_name)

    async def _read_stage_modes(self) -> dict[str, str]:
        """Return the latest per-stage automation modes as a dict.

        Purpose:
            One DB read returns the values used by the reconcile loop;
            we avoid querying each row independently to keep the watcher
            tick cost minimal.
        Args:
            None.
        Output:
            Returns a `{settings_key: mode_string}` dict containing one
            entry per gated stage.
        """

        modes: dict[str, str] = {}
        for stage_key in AUTOMATION_STAGE_KEYS:
            modes[stage_key] = await self._db.get_automation_mode(stage_key)
        return modes

    async def _cancel_task(self, name: str) -> None:
        """Cancel and await one supervised task by name.

        Purpose:
            Shared helper so cancel-and-wait stays consistent between
            mode-driven reconciliation and full shutdown.
        Args:
            name: Stage name used as the task key.
        Output:
            Returns `None`.
        """

        task = self._tasks.pop(name, None)
        if task is None:
            return
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            # Swallow CancelledError and any final-cycle exception — we
            # already logged them when the loop raised; this await only
            # blocks until the task acknowledges the cancel.
            return

    def _spawn(
        self,
        name: str,
        factory: Callable[[], Awaitable[None]],
    ) -> None:
        """Create one supervised task with a restart-on-error wrapper.

        Purpose:
            Wrap every loop in the same restart-with-backoff harness so
            an unexpected exception does not silently disable a stage
            for the remainder of the process lifetime.
        Args:
            name: Stage name used as the task key and log tag.
            factory: Zero-arg coroutine factory the wrapper re-invokes
                on each restart attempt.
        Output:
            Returns `None`.
        """

        async def _supervised() -> None:
            backoff_seconds = _RESTART_BACKOFF_INITIAL_SECONDS
            while not self._stopped:
                try:
                    await factory()
                    # Loops should run forever; a clean return is unexpected.
                    logger.warning("Supervisor: {} loop returned cleanly", name)
                    return
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.exception(
                        "Supervisor: {} loop crashed: {}; restarting in {}s",
                        name,
                        exc,
                        backoff_seconds,
                    )
                    await asyncio.sleep(backoff_seconds)
                    backoff_seconds = min(
                        backoff_seconds * 2, _RESTART_BACKOFF_MAX_SECONDS
                    )

        self._tasks[name] = asyncio.create_task(_supervised(), name=f"supervisor:{name}")

    async def _mode_watcher_factory(self) -> None:
        """Poll for mode changes and reconcile gated loops.

        Purpose:
            React to UI toggle flips within ~1-2s by waiting on the
            mode-changed event, with a periodic ``MODE_WATCH_POLL_SECONDS``
            safety-net poll catching external mutations.
        Args:
            None.
        Output:
            Returns `None` only on cancellation.
        """

        while True:
            try:
                await asyncio.wait_for(
                    self._mode_changed.wait(),
                    timeout=MODE_WATCH_POLL_SECONDS,
                )
                self._mode_changed.clear()
            except asyncio.TimeoutError:
                pass
            # Even on timeout we still reconcile, so out-of-band SQL/CLI
            # edits eventually take effect.
            await self._reconcile_gated_loops()
            # Tiny sleep so a flurry of `notify_mode_changed` calls
            # coalesces into one reconcile pass.
            await asyncio.sleep(_MODE_WATCH_EVENT_TIMEOUT_SECONDS)

    async def _discovery_factory(self) -> None:
        """Run the discovery loop forever.

        Purpose:
            Discovery has no LLM spend and is always active; the
            interval is the only knob the supervisor passes through.
        Args:
            None.
        Output:
            Returns `None` only on cancellation.
        """

        await run_discovery_loop(
            interval_minutes=self._config.discovery_interval_minutes,
        )

    async def _gate_factory(self) -> None:
        """Run the gate loop forever using the shared DB connection.

        Purpose:
            Defer to the gate worker's `run_gate_loop` so the
            in-process supervisor and the standalone CLI exercise
            exactly the same code path.
        Args:
            None.
        Output:
            Returns `None` only on cancellation.
        """

        await run_gate_loop(db=self._db)

    async def _tailor_factory(self) -> None:
        """Run the tailor loop forever using the shared DB connection.

        Purpose:
            Wire the tailor worker entry point with the supervisor's
            resolved paths.
        Args:
            None.
        Output:
            Returns `None` only on cancellation.
        """

        await run_tailor_loop(
            db=self._db,
            output_base_dir=self._config.tailor_output_dir,
            resume_tex_path=self._config.tailor_resume_tex_path,
            candidate_profile_yaml_path=(
                self._config.tailor_candidate_profile_yaml_path
            ),
        )

    async def _apply_factory(self) -> None:
        """Run the apply loop forever using the shared DB connection.

        Purpose:
            Wire the apply worker entry point with the resolved CDP URL
            and artifact directory.
        Args:
            None.
        Output:
            Returns `None` only on cancellation.
        """

        await run_apply_loop(
            db=self._db,
            output_base_dir=self._config.apply_output_dir,
            cdp_url=self._config.apply_cdp_url,
        )


_active_supervisor: LoopSupervisor | None = None
_active_db: DatabaseManager | None = None


async def start_supervisor() -> LoopSupervisor:
    """Boot the process-wide supervisor and its shared DB connection.

    Purpose:
        Provide a single entry point that the FastAPI lifespan calls at
        startup so callers do not have to manage the DB lifecycle or the
        singleton wiring.
    Args:
        None.
    Output:
        Returns the running `LoopSupervisor` instance.
    Raises:
        RuntimeError: When called while a supervisor is already active.
    """

    global _active_supervisor, _active_db
    if _active_supervisor is not None:
        raise RuntimeError("start_supervisor called while one is already active")

    db_path = str(resolve_database_path())
    db = DatabaseManager(db_path)
    await db.__aenter__()
    try:
        await db.create_tables()
        await db.seed_automation_defaults_from_env()
    except Exception:
        await db.__aexit__(None, None, None)
        raise

    config = build_config_from_env()
    supervisor = LoopSupervisor(db=db, config=config)
    await supervisor.start()

    _active_db = db
    _active_supervisor = supervisor
    return supervisor


async def stop_supervisor() -> None:
    """Cancel the supervisor and close its DB connection.

    Purpose:
        Mirror `start_supervisor` so the FastAPI shutdown hook tears
        down the supervisor singleton without leaking tasks or
        connections.
    Args:
        None.
    Output:
        Returns `None`.
    """

    global _active_supervisor, _active_db
    supervisor = _active_supervisor
    db = _active_db
    _active_supervisor = None
    _active_db = None

    if supervisor is not None:
        await supervisor.stop()
    if db is not None:
        await db.__aexit__(None, None, None)


def get_active_supervisor() -> LoopSupervisor | None:
    """Return the running supervisor singleton, if any.

    Purpose:
        Allow the status router to notify the supervisor about mode
        changes without each handler re-wiring its own reference.
    Args:
        None.
    Output:
        Returns the running `LoopSupervisor` or `None` when not started.
    """

    return _active_supervisor
