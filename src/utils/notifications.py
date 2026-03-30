"""Send operational notifications to ntfy.sh when configured.

Purpose:
    Provide a small, dependency-light helper for publishing terminal worker
    failures to ntfy without coupling core pipeline logic to transport details.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from urllib.parse import quote

import httpx
from loguru import logger

DEFAULT_NTFY_SERVER = "https://ntfy.sh"
DEFAULT_NTFY_PRIORITY = "default"


def is_ntfy_enabled() -> bool:
    """Return whether ntfy notifications are enabled via environment config.

    Purpose:
        Let call sites decide quickly whether to attempt outbound notifications
        without duplicating topic checks.
    Args:
        None.
    Output:
        Returns `True` when `NTFY_TOPIC` is configured, otherwise `False`.
    """

    return bool(os.getenv("NTFY_TOPIC", "").strip())


def _build_ntfy_publish_url(server: str, topic: str) -> str:
    """Build the HTTP publish endpoint for the configured ntfy topic.

    Purpose:
        Centralize URL construction and topic escaping so all notification calls
        hit the same endpoint shape.
    Args:
        server: Base ntfy server URL.
        topic: Topic name configured for message delivery.
    Output:
        Returns an absolute publish URL for the target ntfy topic.
    """

    normalized_server = server.rstrip("/")
    escaped_topic = quote(topic, safe="")
    return f"{normalized_server}/{escaped_topic}"


async def send_ntfy_notification(
    *,
    title: str,
    message: str,
    tags: Sequence[str] | None = None,
    priority: str | None = None,
) -> bool:
    """Publish one ntfy notification if topic configuration exists.

    Purpose:
        Emit operational alerts for terminal worker failures while ensuring that
        notification transport failures do not break the processing loop.
    Args:
        title: Short title displayed by notification clients.
        message: Main notification body text.
        tags: Optional tag list displayed by ntfy clients.
        priority: Optional ntfy priority value; defaults to env or "default".
    Output:
        Returns `True` when a notification is successfully published.
        Returns `False` when notifications are disabled or publishing fails.
    """

    topic = os.getenv("NTFY_TOPIC", "").strip()
    if not topic:
        return False

    server = (
        os.getenv("NTFY_SERVER", DEFAULT_NTFY_SERVER).strip() or DEFAULT_NTFY_SERVER
    )
    token = os.getenv("NTFY_TOKEN", "").strip()
    configured_priority = os.getenv("NTFY_PRIORITY", DEFAULT_NTFY_PRIORITY)
    effective_priority = (priority or configured_priority).strip() or DEFAULT_NTFY_PRIORITY

    headers: dict[str, str] = {
        "Title": title,
        "Priority": effective_priority,
    }
    if tags:
        headers["Tags"] = ",".join(tags)
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                _build_ntfy_publish_url(server, topic),
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


__all__ = [
    "httpx",
    "is_ntfy_enabled",
    "send_ntfy_notification",
]
