"""Ntfy push-notification adapter."""

from __future__ import annotations

from collections.abc import Sequence
from urllib.parse import quote

import httpx
from loguru import logger


class NtfyAdapter:
    """Sends notifications to an ntfy topic over HTTP."""

    def __init__(
        self,
        *,
        topic: str,
        server: str = "https://ntfy.sh",
        token: str | None = None,
        default_priority: str = "default",
    ) -> None:
        self._topic = topic
        self._server = server.rstrip("/")
        self._token = token
        self._default_priority = default_priority

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Human-readable adapter identifier."""
        return f"ntfy:{self._topic}"

    async def send(
        self,
        *,
        title: str,
        message: str,
        tags: Sequence[str] | None = None,
        priority: str = "default",
    ) -> bool:
        """Publish a single notification to the configured ntfy topic."""
        effective_priority = priority if priority != "default" else self._default_priority

        headers: dict[str, str] = {
            "Title": title,
            "Priority": effective_priority,
        }
        if tags:
            headers["Tags"] = ",".join(tags)
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        url = f"{self._server}/{quote(self._topic, safe='')}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    url,
                    content=message.encode("utf-8"),
                    headers=headers,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("ntfy publish failed: {}", exc)
            return False
        except Exception as exc:
            logger.warning(
                "ntfy publish failed with unexpected error {}: {}",
                type(exc).__name__,
                exc,
            )
            return False

        return True

    async def close(self) -> None:
        """Release resources (no-op for ntfy)."""
