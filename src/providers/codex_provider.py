"""Codex provider with OAuth device auth flow.

Authenticates via `codex login --device-auth` and routes AI calls
through the Codex CLI subprocess. The auth session persists in a
Docker volume at CODEX_HOME.

Reference: job-ops orchestrator/src/server/services/llm/codex/login.ts
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
from dataclasses import dataclass, field
from enum import Enum

from loguru import logger

from src.providers.errors import (
    ProviderAuthError,
    ProviderConnectionError,
    ProviderResponseError,
)
from src.providers.types import (
    CompletionRequest,
    CompletionResponse,
    ProviderType,
)

DEVICE_AUTH_TIMEOUT_SECONDS = 15.0
LOGOUT_TIMEOUT_SECONDS = 10.0
CODEX_COMPLETION_TIMEOUT_SECONDS = 120.0
MAX_BUFFERED_LINES = 80

DEVICE_CODE_REGEX = re.compile(r"\b[A-Z0-9]{4,}-[A-Z0-9]{4,}\b")
URL_REGEX = re.compile(r"(https?://\S+)", re.IGNORECASE)
EXPIRES_MINUTES_REGEX = re.compile(r"expires in (\d+) minutes", re.IGNORECASE)

# ANSI escape sequence pattern for stripping terminal colors.
ANSI_ESCAPE_REGEX = re.compile(r"\x1B\[[0-9;]*[a-zA-Z]")


class DeviceAuthStatus(str, Enum):
    """State machine for the Codex device auth flow."""

    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class DeviceAuthSnapshot:
    """Serializable snapshot of the current device auth session.

    Attributes:
        status: Current auth flow state.
        is_login_in_progress: True if auth is actively waiting for user.
        verification_url: URL the user must open in their browser.
        user_code: One-time code the user must enter at the URL.
        expires_at_iso: ISO timestamp when the code expires.
        message: Human-readable status message.
    """

    status: DeviceAuthStatus = DeviceAuthStatus.IDLE
    is_login_in_progress: bool = False
    verification_url: str | None = None
    user_code: str | None = None
    expires_at_iso: str | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize the snapshot for API responses."""
        return {
            "status": self.status.value,
            "loginInProgress": self.is_login_in_progress,
            "verificationUrl": self.verification_url,
            "userCode": self.user_code,
            "expiresAt": self.expires_at_iso,
            "message": self.message,
        }


@dataclass
class _DeviceAuthSession:
    """Mutable internal state for an active device auth flow."""

    status: DeviceAuthStatus = DeviceAuthStatus.IDLE
    verification_url: str | None = None
    user_code: str | None = None
    expires_at_epoch_ms: float | None = None
    message: str | None = None
    output_lines: list[str] = field(default_factory=list)
    process: asyncio.subprocess.Process | None = None


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from terminal output."""
    return ANSI_ESCAPE_REGEX.sub("", text)


def _parse_output_line(session: _DeviceAuthSession, raw_line: str) -> None:
    """Parse a line of codex login output for device code and URL."""
    line = _strip_ansi(raw_line).strip()
    if not line:
        return

    session.output_lines.append(line)
    if len(session.output_lines) > MAX_BUFFERED_LINES:
        session.output_lines.pop(0)

    if not session.verification_url:
        url_match = URL_REGEX.search(line)
        if url_match:
            session.verification_url = url_match.group(1)

    if not session.user_code:
        code_match = DEVICE_CODE_REGEX.search(line)
        if code_match:
            session.user_code = code_match.group(0)

    if not session.expires_at_epoch_ms:
        expires_match = EXPIRES_MINUTES_REGEX.search(line)
        if expires_match:
            import time

            minutes = int(expires_match.group(1))
            session.expires_at_epoch_ms = (time.time() + minutes * 60) * 1000


def _session_to_snapshot(session: _DeviceAuthSession | None) -> DeviceAuthSnapshot:
    """Convert internal session state to an immutable API snapshot."""
    if session is None:
        return DeviceAuthSnapshot()

    from datetime import datetime, timezone

    expires_iso = None
    if session.expires_at_epoch_ms:
        expires_dt = datetime.fromtimestamp(
            session.expires_at_epoch_ms / 1000, tz=timezone.utc
        )
        expires_iso = expires_dt.isoformat()

    return DeviceAuthSnapshot(
        status=session.status,
        is_login_in_progress=session.status
        in (DeviceAuthStatus.STARTING, DeviceAuthStatus.RUNNING),
        verification_url=session.verification_url,
        user_code=session.user_code,
        expires_at_iso=expires_iso,
        message=session.message,
    )


def _get_codex_command() -> str:
    """Resolve the codex CLI binary path."""
    env_bin = os.environ.get("CODEX_APP_SERVER_BIN", "").strip()
    if env_bin:
        return env_bin
    # Check if codex is on PATH.
    if shutil.which("codex"):
        return "codex"
    raise ProviderConnectionError(
        "Codex CLI is not installed or not on PATH",
        provider="codex",
    )


class CodexProvider:
    """Route AI completions through Codex CLI with device auth.

    The provider manages the OAuth device auth flow and persists
    credentials via the Codex CLI's native auth storage.

    Attributes:
        _codex_home: Directory for Codex auth persistence.
        _session: Active device auth session state, if any.
    """

    def __init__(self, *, codex_home: str | None = None) -> None:
        """Initialize the Codex provider.

        Args:
            codex_home: Directory for Codex auth tokens. Defaults to
                CODEX_HOME env var or ~/.codex.
        """
        self._codex_home = codex_home or os.environ.get("CODEX_HOME", "")
        self._session: _DeviceAuthSession | None = None

    @property
    def provider_type(self) -> ProviderType:
        """Return the provider backend type."""
        return ProviderType.CODEX

    @property
    def is_authenticated(self) -> bool:
        """Return True if the device auth flow has completed."""
        if self._session and self._session.status == DeviceAuthStatus.COMPLETED:
            return True
        # Check if Codex has a cached session from a previous run.
        auth_path = os.path.join(self._codex_home, "auth.json") if self._codex_home else ""
        if auth_path and os.path.isfile(auth_path):
            return True
        return False

    def get_auth_snapshot(self) -> DeviceAuthSnapshot:
        """Return the current device auth status for API consumers."""
        return _session_to_snapshot(self._session)

    async def start_device_auth(
        self, *, force_restart: bool = False
    ) -> DeviceAuthSnapshot:
        """Initiate the Codex OAuth device authorization flow.

        Spawns `codex login --device-auth` and waits for the CLI to emit
        a verification URL and one-time code.

        Args:
            force_restart: Kill any active session and start fresh.

        Returns:
            Snapshot with the verification URL and user code.

        Raises:
            ProviderAuthError: If the device auth flow fails to start.
        """
        if self._session:
            is_active = self._session.status in (
                DeviceAuthStatus.STARTING,
                DeviceAuthStatus.RUNNING,
            )
            if is_active and not force_restart:
                return _session_to_snapshot(self._session)
            await self._kill_session_process()

        command = _get_codex_command()

        env = {**os.environ}
        if self._codex_home:
            env["CODEX_HOME"] = self._codex_home

        session = _DeviceAuthSession(status=DeviceAuthStatus.STARTING)
        self._session = session

        try:
            proc = await asyncio.create_subprocess_exec(
                command,
                "login",
                "--device-auth",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            session.process = proc
        except FileNotFoundError as exc:
            session.status = DeviceAuthStatus.FAILED
            session.message = "Codex CLI is not installed in this runtime."
            raise ProviderAuthError(
                session.message, provider="codex"
            ) from exc
        except OSError as exc:
            session.status = DeviceAuthStatus.FAILED
            session.message = f"Failed to start Codex login: {exc}"
            raise ProviderAuthError(
                session.message, provider="codex"
            ) from exc

        # Wait for the device code to appear in stdout/stderr.
        try:
            snapshot = await asyncio.wait_for(
                self._wait_for_device_code(session),
                timeout=DEVICE_AUTH_TIMEOUT_SECONDS,
            )
            return snapshot
        except asyncio.TimeoutError:
            session.status = DeviceAuthStatus.FAILED
            session.message = (
                "Timed out waiting for Codex device authorization code."
            )
            await self._kill_session_process()
            raise ProviderAuthError(session.message, provider="codex")

    async def _wait_for_device_code(
        self, session: _DeviceAuthSession
    ) -> DeviceAuthSnapshot:
        """Read codex login output until a device code is found."""
        proc = session.process
        if not proc or not proc.stdout or not proc.stderr:
            raise ProviderAuthError(
                "Codex login process failed to start", provider="codex"
            )

        async def read_stream(stream: asyncio.StreamReader) -> None:
            """Read lines from a stream and parse for device code."""
            while True:
                line_bytes = await stream.readline()
                if not line_bytes:
                    break
                _parse_output_line(session, line_bytes.decode("utf-8", errors="replace"))

        # Read both stdout and stderr concurrently.
        stdout_task = asyncio.create_task(read_stream(proc.stdout))
        stderr_task = asyncio.create_task(read_stream(proc.stderr))

        # Poll until we have both URL and code, or the process exits.
        while True:
            if session.verification_url and session.user_code:
                session.status = DeviceAuthStatus.RUNNING
                session.message = (
                    "Open the verification URL and enter the one-time code."
                )
                # Don't cancel the readers — let the process run in background
                # until the user completes auth or the code expires.
                self._attach_exit_tracking(session, stdout_task, stderr_task)
                return _session_to_snapshot(session)

            if proc.returncode is not None:
                # Process exited before we got the code.
                session.status = DeviceAuthStatus.FAILED
                last_line = session.output_lines[-1] if session.output_lines else ""
                session.message = (
                    last_line
                    or f"Codex login exited with code {proc.returncode}"
                )
                raise ProviderAuthError(session.message, provider="codex")

            await asyncio.sleep(0.1)

    def _attach_exit_tracking(
        self,
        session: _DeviceAuthSession,
        stdout_task: asyncio.Task[None],
        stderr_task: asyncio.Task[None],
    ) -> None:
        """Monitor the background codex login process for completion."""

        async def _track() -> None:
            proc = session.process
            if not proc:
                return
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
            return_code = await proc.wait()
            if session.status not in (
                DeviceAuthStatus.STARTING,
                DeviceAuthStatus.RUNNING,
            ):
                return
            if return_code == 0:
                session.status = DeviceAuthStatus.COMPLETED
                session.message = "Codex login completed."
                logger.info("Codex device auth completed successfully")
            else:
                session.status = DeviceAuthStatus.FAILED
                last_line = session.output_lines[-1] if session.output_lines else ""
                session.message = last_line or f"Codex login failed (code={return_code})"
                logger.warning("Codex device auth failed: {}", session.message)

        asyncio.create_task(_track())

    async def disconnect(self) -> DeviceAuthSnapshot:
        """Log out of Codex and clear the active session.

        Returns:
            An idle auth snapshot after logout.

        Raises:
            ProviderAuthError: If logout fails.
        """
        await self._kill_session_process()
        self._session = None

        try:
            command = _get_codex_command()
        except ProviderConnectionError:
            return DeviceAuthSnapshot()

        env = {**os.environ}
        if self._codex_home:
            env["CODEX_HOME"] = self._codex_home

        try:
            proc = await asyncio.create_subprocess_exec(
                command,
                "logout",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            await asyncio.wait_for(
                proc.wait(), timeout=LOGOUT_TIMEOUT_SECONDS
            )
        except (asyncio.TimeoutError, FileNotFoundError, OSError) as exc:
            logger.warning("Codex logout issue: {}", exc)

        return DeviceAuthSnapshot()

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Send a completion request through Codex CLI.

        Uses `codex --prompt` to send a one-shot completion request
        through the user's authenticated Codex session.

        Args:
            request: Provider-agnostic completion request.

        Returns:
            Normalized completion response.

        Raises:
            ProviderAuthError: If not authenticated with Codex.
            ProviderResponseError: If the Codex response cannot be parsed.
            ProviderConnectionError: If the Codex CLI is unavailable.
        """
        if not self.is_authenticated:
            raise ProviderAuthError(
                "Not authenticated with Codex. Run device auth first.",
                provider="codex",
            )

        command = _get_codex_command()
        env = {**os.environ}
        if self._codex_home:
            env["CODEX_HOME"] = self._codex_home

        # Build the prompt from messages. Codex accepts a single prompt string.
        prompt_parts: list[str] = []
        for msg in request.messages:
            if msg.role == "system":
                prompt_parts.insert(0, msg.content)
            else:
                prompt_parts.append(msg.content)
        prompt_text = "\n\n".join(prompt_parts)

        try:
            proc = await asyncio.create_subprocess_exec(
                command,
                "--prompt",
                prompt_text,
                "--no-full-auto",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=CODEX_COMPLETION_TIMEOUT_SECONDS,
            )
        except FileNotFoundError as exc:
            raise ProviderConnectionError(
                "Codex CLI not found", provider="codex"
            ) from exc
        except asyncio.TimeoutError as exc:
            raise ProviderResponseError(
                "Codex completion timed out", provider="codex"
            ) from exc

        stdout_text = stdout_bytes.decode("utf-8", errors="replace").strip()
        stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()

        if proc.returncode != 0:
            error_msg = stderr_text or stdout_text or f"exit code {proc.returncode}"
            if "not logged in" in error_msg.lower() or "auth" in error_msg.lower():
                raise ProviderAuthError(
                    f"Codex auth expired: {error_msg}", provider="codex"
                )
            raise ProviderResponseError(
                f"Codex completion failed: {error_msg}", provider="codex"
            )

        content = stdout_text
        if not content:
            raise ProviderResponseError(
                "Codex returned empty response", provider="codex"
            )

        return CompletionResponse(
            content=content,
            model="codex",
            provider="codex",
        )

    async def validate_credentials(self) -> bool:
        """Test whether Codex auth is valid.

        Returns:
            True if authenticated, False otherwise.
        """
        if not self.is_authenticated:
            return False

        try:
            command = _get_codex_command()
        except ProviderConnectionError:
            return False

        env = {**os.environ}
        if self._codex_home:
            env["CODEX_HOME"] = self._codex_home

        try:
            proc = await asyncio.create_subprocess_exec(
                command,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            await asyncio.wait_for(proc.wait(), timeout=5.0)
            return proc.returncode == 0
        except Exception:
            return False

    async def _kill_session_process(self) -> None:
        """Terminate any active codex login subprocess."""
        if not self._session or not self._session.process:
            return
        proc = self._session.process
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                proc.kill()
        self._session.process = None
