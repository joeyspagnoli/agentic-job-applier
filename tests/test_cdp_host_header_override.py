"""Regression tests for the CDP Host header override (Bug 3).

Chrome 148+ refuses ``GET /json/version`` (and the subsequent WS
upgrade) when the inbound Host header is neither ``localhost`` nor an
IP literal. The container-default ``host.docker.internal:9222`` URL
trips this rule. ``check_chrome_reachable`` now rewrites the Host
header to ``localhost:<port>`` regardless of the URL hostname, and
``apply_to_job`` does the same for the Playwright WS handshake.

The tests use a stdlib ``http.server`` running on a random local port
that mimics Chrome 148+'s strictness — 500 on any non-``localhost:<port>``
Host header. A passing probe proves the override is wired.
"""

from __future__ import annotations

import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from src.agents.apply_worker.browser import (
    _cdp_localhost_host_header,
    check_chrome_reachable,
)


def _free_port() -> int:
    """Pick an available TCP port on localhost.

    Returns:
        A free port number suitable for binding the stub HTTP server.
    """

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _build_strict_host_handler(allowed_host: str) -> type[BaseHTTPRequestHandler]:
    """Build a request handler that 500s on non-matching Host headers.

    Purpose:
        Mimic Chrome 148+'s host-check. Returns a Chrome-shaped JSON
        payload only when the inbound Host header equals ``allowed_host``.
    Args:
        allowed_host: The Host header value that should succeed.
    Returns:
        A ``BaseHTTPRequestHandler`` subclass ready for ``HTTPServer``.
    """

    class _StrictHostHandler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: Any) -> None:
            """Suppress stdlib http.server stderr noise during tests."""

        def do_GET(self) -> None:  # noqa: N802 — http.server contract
            inbound = self.headers.get("Host", "")
            if inbound != allowed_host:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b"host header rejected")
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"Browser":"Chrome/148.0"}')

    return _StrictHostHandler


@pytest.fixture
def strict_host_server() -> Any:
    """Start a chrome-148-mimicking server, yield ``(port, allowed_host)``.

    Purpose:
        Centralize the lifecycle of the stub HTTP server so each test
        starts a fresh one on its own port. The fixture cleans up the
        thread + socket regardless of test outcome.
    Yields:
        ``(port, allowed_host)`` so the test can build URLs against the
        IP literal while asserting the Host override forwards
        ``localhost:<port>``.
    """

    port = _free_port()
    allowed_host = f"localhost:{port}"
    handler_cls = _build_strict_host_handler(allowed_host)
    server = HTTPServer(("127.0.0.1", port), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield port, allowed_host
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


def test_cdp_localhost_host_header_returns_localhost_port_for_known_url() -> None:
    """The helper produces ``{"Host": "localhost:<port>"}`` for a parseable URL.

    Purpose:
        Guard the contract Playwright + httpx both rely on so a
        casual refactor cannot regress the header shape.
    """

    headers = _cdp_localhost_host_header("http://host.docker.internal:9222")
    assert headers == {"Host": "localhost:9222"}


def test_cdp_localhost_host_header_returns_empty_for_port_less_url() -> None:
    """No port → no override; Chrome's port-less form is non-standard.

    Purpose:
        Document the intentional fallback. A port-less URL means the
        caller is bypassing the standard CDP discovery and we should
        not impose a Host header guess.
    """

    headers = _cdp_localhost_host_header("http://example.com")
    assert headers == {}


@pytest.mark.asyncio
async def test_check_chrome_reachable_overrides_host_header(
    strict_host_server: tuple[int, str],
) -> None:
    """Probe succeeds when the URL hostname differs from the Host header.

    Purpose:
        Lock the Bug 3 regression — before the fix this returned False
        because the probe sent ``Host: host.docker.internal:9222`` and
        the stub (mirroring Chrome 148+) replied with 500.
    """

    port, _allowed_host = strict_host_server
    # Use an IP-literal hostname in the URL. The stub only accepts
    # ``Host: localhost:<port>``; the override must force that value
    # for the probe to land 200.
    cdp_url = f"http://127.0.0.1:{port}"

    reachable = await check_chrome_reachable(cdp_url)

    assert reachable is True, (
        "Bug 3 regression: probe must override the Host header so "
        "Chrome 148+ accepts the request even when the URL uses "
        "host.docker.internal or another non-localhost name."
    )


@pytest.mark.asyncio
async def test_check_chrome_reachable_returns_false_when_server_rejects() -> None:
    """A real reject (no override path) still surfaces as False.

    Purpose:
        Confirm the Host override does not mask a real outage — when
        no server is listening at all, the probe still returns False.
    """

    port = _free_port()  # nothing listening
    reachable = await check_chrome_reachable(f"http://127.0.0.1:{port}")
    assert reachable is False
