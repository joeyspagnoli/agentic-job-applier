"""Environment-key (.env file) read/write helpers for API key endpoints."""

from __future__ import annotations

import os

from api.config import ALLOWED_API_KEY_NAMES
from api.config import SETTINGS_ENV_PATH


def _read_env_pairs() -> list[tuple[str, str]]:
    """Parse the project .env file into an ordered list of key-value pairs.

    Purpose:
        Provide a low-level reader so API key endpoints can inspect and
        modify individual entries without destroying comments or ordering.
    Args:
        None.
    Output:
        Returns a list of (line_text, key_or_empty) tuples where the second
        element is non-empty only for KEY=VALUE lines.
    """

    if not SETTINGS_ENV_PATH.exists():
        return []
    raw_lines = SETTINGS_ENV_PATH.read_text(encoding="utf-8").splitlines()
    pairs: list[tuple[str, str]] = []
    for line in raw_lines:
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            pairs.append((line, ""))
        else:
            key = stripped.split("=", 1)[0].strip()
            pairs.append((line, key))
    return pairs


def _read_env_key_statuses() -> dict[str, bool]:
    """Return configured status for all allowed API key names.

    Purpose:
        Drive the API keys status list in the settings UI without exposing
        secret values.
    Args:
        None.
    Output:
        Returns a dict mapping each allowed key name to True when a non-empty
        value is present in the .env file.
    """

    status: dict[str, bool] = {name: False for name in ALLOWED_API_KEY_NAMES}
    if not SETTINGS_ENV_PATH.exists():
        return status
    for line, key in _read_env_pairs():
        if key in ALLOWED_API_KEY_NAMES:
            value = line.split("=", 1)[1].strip() if "=" in line else ""
            status[key] = value not in (
                "",
                "your_google_api_key_here",
                "your_anthropic_key_here",
            )
    return status


def _write_env_key(key_name: str, key_value: str) -> None:
    """Add or replace one API key entry in the .env file.

    Purpose:
        Persist a new secret value while preserving comments and all other
        key entries so the .env file remains human-readable.
    Args:
        key_name: Environment variable name (must be in ALLOWED_API_KEY_NAMES).
        key_value: New secret value to write.
    Output:
        Returns None after writing the updated .env file.
    """

    pairs = _read_env_pairs()
    found = False
    new_lines: list[str] = []
    for line, key in pairs:
        if key == key_name:
            new_lines.append(f"{key_name}={key_value}")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{key_name}={key_value}")
    SETTINGS_ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    # Reload into the running process so subsequent pipeline calls see the new key.
    os.environ[key_name] = key_value


def _delete_env_key(key_name: str) -> None:
    """Remove one API key entry from the .env file.

    Purpose:
        Allow users to fully revoke a stored key from settings UI without
        leaving a placeholder that could mislead status checks.
    Args:
        key_name: Environment variable name to remove.
    Output:
        Returns None after writing the updated .env file.
    """

    pairs = _read_env_pairs()
    new_lines = [line for line, key in pairs if key != key_name]
    SETTINGS_ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    os.environ.pop(key_name, None)


def _build_api_keys_response() -> dict[str, object]:
    """Build the canonical API keys status response payload.

    Purpose:
        Return a consistent response shape for all API key endpoints so the
        frontend can refresh its status list after any mutation.
    Args:
        None.
    Output:
        Returns dict with 'ok' and 'keys' list of name/configured pairs.
    """

    statuses = _read_env_key_statuses()
    return {
        "ok": True,
        "keys": [
            {"name": name, "configured": statuses.get(name, False)}
            for name in sorted(ALLOWED_API_KEY_NAMES)
        ],
    }
