"""Status and autonomous-mode router (top-bar chips and toggle).

Backs the three top-bar chips and the new "autonomous mode" toggle:

* `GET /api/status/autonomous-readiness` — list of hard requirements
  for autonomous mode; the toggle is disabled in the UI unless every
  requirement reports `satisfied=true`.
* `GET /api/status/chrome` — soft requirement: host Chrome reachability
  used by the dashboard chip and by the apply loop.
* `GET /api/settings/autonomous-mode` — derived `{enabled}` based on
  the per-stage automation mode rows.
* `POST /api/settings/autonomous-mode` — flip every stage between
  `both` (ON) and `opt_in` (OFF) atomically, re-validating the hard
  requirements server-side before allowing ON.

The toggle never surfaces the `autonomous` per-stage mode (loops only,
buttons disabled); only `both` and `opt_in` are reachable from the UI.
"""

from __future__ import annotations

import os
from datetime import datetime
from datetime import timezone

from fastapi import APIRouter
from pydantic import BaseModel
from pydantic import Field

from src.agents.apply_worker.browser import check_chrome_reachable
from src.agents.resume_tailor.validator import validate_resume_tex
from src.database._mixins.system_settings import APPLY_MODE_KEY
from src.database._mixins.system_settings import AUTOMATION_STAGE_KEYS
from src.database._mixins.system_settings import GATE_MODE_KEY
from src.database._mixins.system_settings import TAILOR_MODE_KEY
from src.database.db_manager import DatabaseManager

from api.config import SETTINGS_PROFILE_PATH
from api.config import SETTINGS_RESUME_PATH
from api.errors import _raise_api_error
from api.services.env_keys import ENV_KEY_PLACEHOLDER_VALUES
from api.services.supervisor import get_active_supervisor

# UI-facing labels for each requirement row. Keep these stable —
# the dashboard renders the strings verbatim in tooltips.
_REQUIREMENT_NAME_OPENAI = "OPENAI_API_KEY"
_REQUIREMENT_NAME_PROFILE = "candidate_profile.yaml"
_REQUIREMENT_NAME_RESUME_TEX = "resume.tex contract"

# Mode strings that map onto the global autonomous toggle. ON enables
# both loops and button clicks; OFF leaves buttons working but pauses
# the asyncio loops.
_AUTONOMOUS_ON_MODE = "both"
_AUTONOMOUS_OFF_MODE = "opt_in"

# OS hint surfaced in the Chrome chip popover so the user can copy the
# right command without leaving the dashboard.
_CHROME_COMMAND_HINTS: dict[str, str] = {
    "mac": (
        'open -a "Google Chrome" --args --remote-debugging-port=9222'
    ),
    "linux": "google-chrome --remote-debugging-port=9222 &",
    "windows": (
        '"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" '
        "--remote-debugging-port=9222"
    ),
}
_CHROME_HINT_DEFAULT_OS = "mac"

router = APIRouter(prefix="/api", tags=["status"])


class AutonomousRequirementDto(BaseModel):
    """One requirement row surfaced by the readiness endpoint."""

    name: str = Field(
        ...,
        description="Stable identifier for the requirement; matches UI labels.",
    )
    satisfied: bool = Field(
        ...,
        description="Whether the requirement currently passes.",
    )
    fix: str = Field(
        ...,
        description="Short human-readable hint shown in the tooltip when not satisfied.",
    )


class AutonomousReadinessResponse(BaseModel):
    """Response payload for `GET /api/status/autonomous-readiness`."""

    ok: bool = Field(default=True)
    ready: bool = Field(
        ...,
        description="True only when every requirement reports satisfied=true.",
    )
    requirements: list[AutonomousRequirementDto]


class ChromeStatusResponse(BaseModel):
    """Response payload for `GET /api/status/chrome`."""

    ok: bool = Field(default=True)
    reachable: bool = Field(
        ...,
        description="True when the configured CDP endpoint responded within 5s.",
    )
    checked_at: str = Field(
        ...,
        description="ISO-8601 UTC timestamp captured immediately after the probe.",
    )
    cdp_url: str = Field(
        ...,
        description="The CDP endpoint URL the API probed.",
    )
    command_hint: str = Field(
        ...,
        description="OS-appropriate command to launch host Chrome with debug port.",
    )


class AutonomousModeResponse(BaseModel):
    """Response payload for the autonomous-mode GET/POST endpoints."""

    ok: bool = Field(default=True)
    enabled: bool = Field(
        ...,
        description=(
            "True when every per-stage automation mode row equals `both` — the "
            "ON state for the global autonomous toggle."
        ),
    )


class AutonomousModePatch(BaseModel):
    """Request body for `POST /api/settings/autonomous-mode`."""

    enabled: bool = Field(
        ...,
        description="Target state for the global autonomous toggle.",
    )


def _is_openai_key_configured() -> bool:
    """Return True when OPENAI_API_KEY is set to a non-placeholder value.

    Purpose:
        Reuse the same definition the existing `/api/system/health`
        endpoint uses so the readiness endpoint and the legacy health
        endpoint never disagree on whether a key is "configured".
    Args:
        None.
    Output:
        Returns `True` when the env var is set and not a placeholder.
    """

    raw_value = os.environ.get("OPENAI_API_KEY", "").strip()
    return raw_value != "" and raw_value not in ENV_KEY_PLACEHOLDER_VALUES


def _resume_tex_contract_passes() -> bool:
    """Return True when `config/resume.tex` exists and passes the validator.

    Purpose:
        Reject autonomous mode when the tailor pipeline would
        immediately fail every job because the on-disk `.tex` does not
        match the published contract.
    Args:
        None.
    Output:
        Returns `True` when the file exists and `validate_resume_tex`
        reports `ok=True`.
    """

    if not SETTINGS_RESUME_PATH.exists():
        return False
    try:
        tex_text = SETTINGS_RESUME_PATH.read_text(encoding="utf-8")
    except OSError:
        return False
    report = validate_resume_tex(tex_text, run_compile_check=False)
    return report.ok


def _build_requirements() -> list[AutonomousRequirementDto]:
    """Build the per-requirement readiness rows.

    Purpose:
        Single source of truth for the hard requirements that gate the
        autonomous toggle. Adding a new requirement only needs an entry
        here; the readiness endpoint and the POST validator both rely
        on it.
    Args:
        None.
    Output:
        Returns the requirement DTO list in display order.
    """

    return [
        AutonomousRequirementDto(
            name=_REQUIREMENT_NAME_OPENAI,
            satisfied=_is_openai_key_configured(),
            fix="Set OPENAI_API_KEY in Settings → API Keys before enabling autonomous mode.",
        ),
        AutonomousRequirementDto(
            name=_REQUIREMENT_NAME_PROFILE,
            satisfied=SETTINGS_PROFILE_PATH.exists(),
            fix="Upload a candidate_profile.yaml in Settings → Profile.",
        ),
        AutonomousRequirementDto(
            name=_REQUIREMENT_NAME_RESUME_TEX,
            satisfied=_resume_tex_contract_passes(),
            fix="Upload a resume.tex that passes the contract validator in Settings → Resume.",
        ),
    ]


def _command_hint_for(os_hint: str | None) -> str:
    """Resolve the OS hint string into a launch command.

    Purpose:
        Keep the Chrome chip's copy-paste command consistent and
        sourced from one place. Unknown hints fall through to the macOS
        default since macOS is the documented primary supported host.
    Args:
        os_hint: Optional `?os=mac|linux|windows` query value.
    Output:
        Returns the launch command string for the resolved OS.
    """

    normalized = (os_hint or _CHROME_HINT_DEFAULT_OS).strip().lower()
    return _CHROME_COMMAND_HINTS.get(normalized, _CHROME_COMMAND_HINTS[_CHROME_HINT_DEFAULT_OS])


def _resolve_cdp_url() -> str:
    """Return the configured CDP endpoint URL.

    Purpose:
        Mirror the supervisor's env-resolution rule so the dashboard
        chip probes the same endpoint the apply loop will use.
    Args:
        None.
    Output:
        Returns the URL string.
    """

    return os.getenv("CHROME_CDP_URL", "http://host.docker.internal:9222").strip()


@router.get("/status/autonomous-readiness", response_model=AutonomousReadinessResponse)
async def get_autonomous_readiness() -> AutonomousReadinessResponse:
    """Report whether autonomous mode is eligible to be enabled.

    Purpose:
        Drive the autonomous-toggle disabled state in the top bar and
        let the user see exactly which requirement is failing.
    Args:
        None.
    Output:
        Returns the readiness DTO with a per-requirement breakdown.
    """

    requirements = _build_requirements()
    ready = all(item.satisfied for item in requirements)
    return AutonomousReadinessResponse(ready=ready, requirements=requirements)


@router.get("/status/chrome", response_model=ChromeStatusResponse)
async def get_chrome_status(os: str | None = None) -> ChromeStatusResponse:
    """Probe host Chrome over CDP and return the result for the chip.

    Purpose:
        Drive the Chrome chip in the top bar and expose the
        OS-appropriate launch command for the popover.
    Args:
        os: Optional OS hint from the dashboard (`mac`, `linux`, `windows`).
    Output:
        Returns the chrome status DTO with reachability, probe time,
        endpoint URL, and a copy-paste launch command.
    """

    cdp_url = _resolve_cdp_url()
    reachable = await check_chrome_reachable(cdp_url)
    return ChromeStatusResponse(
        reachable=reachable,
        checked_at=datetime.now(tz=timezone.utc).isoformat(),
        cdp_url=cdp_url,
        command_hint=_command_hint_for(os),
    )


async def _read_global_autonomous_state(db: DatabaseManager) -> bool:
    """Return `True` when every stage row is set to the ON-mode value.

    Purpose:
        Encapsulate the "all stages are `both`" derivation so the GET
        endpoint and the POST round-trip share one implementation.
    Args:
        db: Connected database manager.
    Output:
        Returns `True` iff each stage row matches `_AUTONOMOUS_ON_MODE`.
    """

    for stage_key in AUTOMATION_STAGE_KEYS:
        mode = await db.get_automation_mode(stage_key)
        if mode != _AUTONOMOUS_ON_MODE:
            return False
    return True


@router.get("/settings/autonomous-mode", response_model=AutonomousModeResponse)
async def get_autonomous_mode() -> AutonomousModeResponse:
    """Return the derived global autonomous-toggle state.

    Purpose:
        Let the dashboard render the toggle in the correct position on
        first load without scanning every per-stage row.
    Args:
        None.
    Output:
        Returns `{enabled}` reflecting current persisted stage rows.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    db_path = str(_main.resolve_database_path())
    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        enabled = await _read_global_autonomous_state(db)

    return AutonomousModeResponse(enabled=enabled)


@router.post("/settings/autonomous-mode", response_model=AutonomousModeResponse)
async def set_autonomous_mode(payload: AutonomousModePatch) -> AutonomousModeResponse:
    """Flip every stage between ON (`both`) and OFF (`opt_in`).

    Purpose:
        Provide one transactional write path for the autonomous toggle.
        When enabling, re-validate every hard requirement so the UI's
        disabled state cannot be bypassed by an out-of-band POST.
        After persisting, notify the supervisor so the gated loops
        start or stop within ~1-2 seconds.
    Args:
        payload: New target state for the toggle.
    Output:
        Returns the post-write derived state.
    Raises:
        HTTPException: 409 when enabling and one or more hard
            requirements are not satisfied.
    """

    from api import main as _main  # noqa: PLC0415 — late import for monkeypatch hook

    if payload.enabled:
        requirements = _build_requirements()
        missing = [item.name for item in requirements if not item.satisfied]
        if missing:
            _raise_api_error(
                status_code=409,
                code="AUTONOMOUS_REQUIREMENTS_NOT_MET",
                message=(
                    "Cannot enable autonomous mode: one or more requirements "
                    "are not satisfied."
                ),
                details={"missing": missing},
            )

    target_mode = _AUTONOMOUS_ON_MODE if payload.enabled else _AUTONOMOUS_OFF_MODE

    db_path = str(_main.resolve_database_path())
    async with DatabaseManager(db_path) as db:
        await db.create_tables()
        for stage_key in (GATE_MODE_KEY, TAILOR_MODE_KEY, APPLY_MODE_KEY):
            await db.set_automation_mode(stage_key, target_mode)
        enabled = await _read_global_autonomous_state(db)

    supervisor = get_active_supervisor()
    if supervisor is not None:
        supervisor.notify_mode_changed()

    return AutonomousModeResponse(enabled=enabled)
