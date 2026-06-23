"""Fan-out dispatcher that reads channel config from YAML and sends to all channels."""

from __future__ import annotations

import asyncio
import os
import re

import yaml
from loguru import logger

from src.utils.notification_adapters.email import EmailAdapter
from src.utils.notification_adapters.ntfy import NtfyAdapter
from src.utils.notification_protocol import NotificationChannel

# Maps the "type" key in notifications.yaml to the adapter class that handles it.
ADAPTER_REGISTRY: dict[str, type] = {
    "ntfy": NtfyAdapter,
    "email": EmailAdapter,
}

# Matches bare ($VAR) and braced (${VAR}) environment variable references.
_ENV_VAR_RE = re.compile(r"^\$\{?([A-Z_][A-Z0-9_]*)\}?$")


def _resolve_env(value: object) -> object:
    """Substitute an env-var placeholder with its runtime value.

    Args:
        value: Any config value. Only strings matching $VAR or ${VAR} are
            substituted; all other values are returned unchanged.

    Returns:
        The environment variable's value if the placeholder is set, the
        original placeholder string if it is not set, or the original value
        unchanged for non-string inputs.
    """
    if not isinstance(value, str):
        return value
    match = _ENV_VAR_RE.match(value)
    if not match:
        return value
    return os.environ.get(match.group(1), value)


def _interpolate(mapping: dict[str, object]) -> dict[str, object]:
    """Resolve env-var placeholders in every value of a flat config dict.

    Args:
        mapping: A flat dictionary of adapter constructor kwargs whose string
            values may contain $VAR or ${VAR} placeholders.

    Returns:
        A new dictionary with the same keys and all placeholders resolved.
    """
    return {k: _resolve_env(v) for k, v in mapping.items()}


class NotificationDispatcher:
    """Sends a notification to every configured channel in parallel.

    Attributes:
        _channels: The list of adapter instances to fan out to.

    Example:
        dispatcher = NotificationDispatcher.from_yaml("config/notifications.yaml")
        results = await dispatcher.send(title="New jobs", message="3 matches found")
        await dispatcher.close()
    """

    def __init__(self, channels: list[NotificationChannel]) -> None:
        """Initialise the dispatcher with a pre-built list of channels.

        Args:
            channels: Adapter instances that satisfy the NotificationChannel
                protocol.
        """
        self._channels = channels

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_yaml(cls, config_path: str) -> NotificationDispatcher:
        """Build a dispatcher by parsing a YAML config file.

        Reads the top-level ``channels`` list from the YAML. Each entry must
        have a ``type`` key matching ADAPTER_REGISTRY; remaining keys are
        passed as constructor kwargs. String values of the form ``$VAR`` or
        ``${VAR}`` are resolved from the environment; entries whose required
        env vars are unset are silently skipped.

        Falls back to constructing a single NtfyAdapter from NTFY_TOPIC,
        NTFY_SERVER, and NTFY_TOKEN environment variables when no ``channels``
        key is present, preserving backward compatibility.

        Args:
            config_path: Absolute or relative path to the notifications YAML
                file.

        Returns:
            A NotificationDispatcher wired with all successfully constructed
            adapters. Returns a no-op dispatcher (empty channel list) when
            neither ``channels`` nor NTFY_TOPIC is available.
        """
        with open(config_path) as fh:
            raw: dict[str, object] = yaml.safe_load(fh) or {}

        channel_configs: list[dict[str, object]] = raw.get("channels") or []  # type: ignore[assignment]

        if channel_configs:
            return cls(_build_channels(channel_configs))

        # Backward-compat: fall back to env vars for ntfy
        topic = os.environ.get("NTFY_TOPIC")
        if topic:
            server = os.environ.get("NTFY_SERVER", "https://ntfy.sh")
            token = os.environ.get("NTFY_TOKEN")
            return cls([NtfyAdapter(topic=topic, server=server, token=token)])

        logger.warning("No notification channels configured; dispatcher is a no-op")
        return cls([])

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def send(
        self,
        *,
        title: str,
        message: str,
        tags: list[str] | None = None,
        priority: str = "default",
    ) -> dict[str, bool]:
        """Fan out a notification to all channels concurrently.

        Args:
            title: Short subject line for the notification.
            message: Full notification body.
            tags: Optional list of tag strings passed to each adapter.
            priority: Delivery priority hint; adapters interpret this
                per-protocol. Defaults to ``"default"``.

        Returns:
            A mapping of ``channel.name`` to ``True`` (sent) or ``False``
            (failed). Returns an empty dict when no channels are configured.
        """
        if not self._channels:
            return {}

        results = await asyncio.gather(
            *[
                ch.send(title=title, message=message, tags=tags, priority=priority)
                for ch in self._channels
            ],
            return_exceptions=True,
        )

        outcome: dict[str, bool] = {}
        for ch, result in zip(self._channels, results):
            if isinstance(result, BaseException):
                logger.warning(
                    "Channel {} raised {}: {}", ch.name, type(result).__name__, result
                )
                outcome[ch.name] = False
            else:
                outcome[ch.name] = bool(result)

        return outcome

    async def close(self) -> None:
        """Close all underlying channel connections.

        Errors from individual adapters are suppressed so a single failing
        close does not prevent the others from releasing their resources.
        """
        await asyncio.gather(
            *[ch.close() for ch in self._channels],
            return_exceptions=True,
        )


# ------------------------------------------------------------------
# Module-private helpers
# ------------------------------------------------------------------


def _build_channels(
    channel_configs: list[dict[str, object]],
) -> list[NotificationChannel]:
    """Instantiate adapter objects from a list of raw config dicts.

    Args:
        channel_configs: Each dict must contain a ``type`` key whose value
            matches ADAPTER_REGISTRY. Remaining keys become adapter kwargs.

    Returns:
        A list of successfully constructed adapters. Entries with unknown
        types, unresolved required env vars, or bad kwargs are skipped with
        a warning.
    """
    channels: list[NotificationChannel] = []

    for raw_entry in channel_configs:
        entry = dict(raw_entry)
        raw_type = entry.pop("type", None)
        channel_type = raw_type if isinstance(raw_type, str) else None

        if channel_type not in ADAPTER_REGISTRY:
            logger.warning(
                "Unknown notification channel type {!r} — skipping", channel_type
            )
            continue

        kwargs = _interpolate(entry)
        # Drop keys whose env var placeholder was not set at runtime.
        resolved_kwargs = {
            k: v
            for k, v in kwargs.items()
            if not (isinstance(v, str) and _ENV_VAR_RE.match(v))
        }

        try:
            adapter = ADAPTER_REGISTRY[channel_type](**resolved_kwargs)
            channels.append(adapter)
        except TypeError as exc:
            logger.warning("Failed to instantiate {} adapter: {}", channel_type, exc)

    return channels


__all__ = ["ADAPTER_REGISTRY", "NotificationDispatcher"]
