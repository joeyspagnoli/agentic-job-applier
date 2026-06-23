"""Protocol defining the contract every notification channel must satisfy."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable


@runtime_checkable
class NotificationChannel(Protocol):
    """Structural interface for a pluggable notification backend."""

    @property
    def name(self) -> str:
        """Channel identifier, e.g. 'ntfy:my-topic' or 'email:resend'."""
        ...

    async def send(
        self,
        *,
        title: str,
        message: str,
        tags: Sequence[str] | None = None,
        priority: str = "default",
    ) -> bool: ...

    async def close(self) -> None: ...


__all__ = ["NotificationChannel"]
