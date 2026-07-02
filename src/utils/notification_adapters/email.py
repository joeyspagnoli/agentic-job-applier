"""Resend email notification adapter."""

from __future__ import annotations

from collections.abc import Sequence

import httpx
from loguru import logger

_RESEND_URL = "https://api.resend.com/emails"


class EmailAdapter:
    """Sends email notifications via the Resend API."""

    def __init__(
        self,
        *,
        api_key: str,
        from_address: str,
        to_addresses: list[str],
        subject_prefix: str = "[Jobs]",
    ) -> None:
        self._api_key = api_key
        self._from = from_address
        self._to = to_addresses
        self._prefix = subject_prefix

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Human-readable adapter identifier."""
        return "email:resend"

    async def send(
        self,
        *,
        title: str,
        message: str,
        tags: Sequence[str] | None = None,
        priority: str = "default",
    ) -> bool:
        """Send a single email via Resend."""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "from": self._from,
            "to": self._to,
            "subject": f"{self._prefix} {title}",
            "html": message,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    _RESEND_URL,
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("resend email failed: {}", exc)
            return False
        except Exception as exc:
            logger.warning(
                "resend email failed with unexpected error {}: {}",
                type(exc).__name__,
                exc,
            )
            return False

        return True

    async def close(self) -> None:
        """Release resources (no-op for Resend)."""
