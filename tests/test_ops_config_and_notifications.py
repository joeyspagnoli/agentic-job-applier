"""Validate ops config guardrails and notification helper resilience."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.utils import notifications


@pytest.mark.asyncio
async def test_send_ntfy_notification_returns_false_for_invalid_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify malformed ntfy server config never raises to caller.

    Purpose:
        Keep notification helper fail-safe when environment config contains an
        invalid server URL or unsupported scheme.
    Args:
        monkeypatch: Pytest fixture used to set malformed ntfy environment.
    Output:
        Returns `None`; test passes when helper returns `False` without raising.
    """

    monkeypatch.setenv("NTFY_TOPIC", "alerts")
    monkeypatch.setenv("NTFY_SERVER", "://invalid-url")

    was_sent = await notifications.send_ntfy_notification(
        title="title",
        message="message",
    )

    assert was_sent is False


@pytest.mark.asyncio
async def test_send_ntfy_notification_includes_bearer_header_when_token_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify token-configured notifications include Authorization header.

    Purpose:
        Ensure ntfy authenticated deployments work when `NTFY_TOKEN` is set.
    Args:
        monkeypatch: Pytest fixture used to patch environment and HTTP client.
    Output:
        Returns `None`; test passes when Authorization header is present.
    """

    captured_headers: dict[str, str] = {}

    class FakeResponse:
        """Model a successful httpx response for notification tests."""

        def raise_for_status(self) -> None:
            """Return successfully to emulate HTTP 2xx behavior.

            Purpose:
                Keep notification helper on the success path.
            Args:
                self: Fake response instance.
            Output:
                Returns `None`.
            """

    class FakeAsyncClient:
        """Capture outgoing notification headers without network access."""

        def __init__(self, timeout: float) -> None:
            """Store timeout argument for interface parity.

            Purpose:
                Keep constructor signature compatible with httpx.AsyncClient.
            Args:
                self: Fake client instance.
                timeout: Timeout argument provided by production code.
            Output:
                Returns `None`.
            """

            _ = timeout

        async def __aenter__(self) -> "FakeAsyncClient":
            """Return fake client instance from async context entry.

            Purpose:
                Match httpx async context-manager behavior.
            Args:
                self: Fake client instance.
            Output:
                Returns this instance.
            """

            return self

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc_val: BaseException | None,
            exc_tb: object,
        ) -> None:
            """Provide no-op async context exit behavior.

            Purpose:
                Keep fake client lifecycle compatible with production usage.
            Args:
                self: Fake client instance.
                exc_type: Exception type raised in context, if any.
                exc_val: Exception value raised in context, if any.
                exc_tb: Exception traceback raised in context, if any.
            Output:
                Returns `None`.
            """

            _ = (exc_type, exc_val, exc_tb)

        async def post(
            self, url: str, content: bytes, headers: dict[str, str]
        ) -> FakeResponse:
            """Capture request metadata and emulate successful publish.

            Purpose:
                Assert helper emits expected URL and header payload.
            Args:
                self: Fake client instance.
                url: Publish URL from helper.
                content: Encoded notification body.
                headers: HTTP headers used for publish request.
            Output:
                Returns a fake successful response.
            """

            _ = (url, content)
            captured_headers.update(headers)
            return FakeResponse()

    monkeypatch.setenv("NTFY_TOPIC", "alerts")
    monkeypatch.setenv("NTFY_SERVER", "https://ntfy.example")
    monkeypatch.setenv("NTFY_TOKEN", "secret-token")
    monkeypatch.setattr(notifications.httpx, "AsyncClient", FakeAsyncClient)

    was_sent = await notifications.send_ntfy_notification(
        title="title",
        message="message",
    )

    assert was_sent is True
    assert captured_headers.get("Authorization") == "Bearer secret-token"


def test_worker_and_discovery_units_depend_on_network_online_target() -> None:
    """Verify network-bound systemd units wait for network-online target.

    Purpose:
        Prevent boot-time DNS/connectivity races for discovery and worker units.
    Args:
        None.
    Output:
        Returns `None`; test passes when units include network-online dependencies.
    """

    repo_root = Path(__file__).resolve().parent.parent
    worker_unit = (repo_root / "deploy/job-agent-worker.service").read_text(
        encoding="utf-8"
    )
    discovery_unit = (repo_root / "deploy/job-discovery.service").read_text(
        encoding="utf-8"
    )

    assert "After=network-online.target" in worker_unit
    assert "Wants=network-online.target" in worker_unit
    assert "After=network-online.target" in discovery_unit
    assert "Wants=network-online.target" in discovery_unit


def test_systemd_units_require_env_file_instead_of_optional_load() -> None:
    """Verify production units require `.env` file instead of optional load.

    Purpose:
        Fail fast on missing env configuration instead of silently degrading.
    Args:
        None.
    Output:
        Returns `None`; test passes when units avoid `EnvironmentFile=-...`.
    """

    repo_root = Path(__file__).resolve().parent.parent
    unit_paths = [
        repo_root / "deploy/job-agent-alert@.service",
        repo_root / "deploy/job-agent-worker.service",
        repo_root / "deploy/job-discovery.service",
    ]
    for unit_path in unit_paths:
        unit_text = unit_path.read_text(encoding="utf-8")
        assert "EnvironmentFile=-" not in unit_text
        assert "EnvironmentFile=/path/to/agentic-job-applier/.env" in unit_text


def test_alert_unit_conditionally_supports_ntfy_bearer_token() -> None:
    """Verify alert unit command includes conditional token-auth behavior.

    Purpose:
        Ensure authenticated ntfy endpoints can receive systemd failure alerts.
    Args:
        None.
    Output:
        Returns `None`; test passes when alert command checks `NTFY_TOKEN`.
    """

    repo_root = Path(__file__).resolve().parent.parent
    alert_unit = (repo_root / "deploy/job-agent-alert@.service").read_text(
        encoding="utf-8"
    )

    assert 'if [ -n "$NTFY_TOKEN" ]' in alert_unit
    assert "Authorization: Bearer $NTFY_TOKEN" in alert_unit


def test_env_example_avoids_inline_comments_in_assignment_lines() -> None:
    """Verify `.env.example` keeps comments off assignment lines.

    Purpose:
        Avoid confusing copy/paste mistakes where inline comments become part
        of environment values.
    Args:
        None.
    Output:
        Returns `None`; test passes when assignment lines have no inline `#`.
    """

    env_path = Path(__file__).resolve().parent.parent / ".env.example"
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        assert "#" not in line
