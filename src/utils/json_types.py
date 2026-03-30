"""Shared JSON type aliases used across dynamic API and DB boundaries.

Purpose:
    Provide reusable recursive JSON typing so modules can model unstructured
    payloads without falling back to `Any`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypeAlias

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | dict[str, "JSONValue"] | list["JSONValue"]
JSONObject: TypeAlias = dict[str, JSONValue]
JSONArray: TypeAlias = list[JSONValue]


def get_str(data: Mapping[str, object], key: str, default: str = "") -> str:
    """Return the string value at key, or default if missing or wrong type."""
    val = data.get(key)
    return val if isinstance(val, str) else default


def get_str_opt(data: Mapping[str, object], key: str) -> str | None:
    """Return the string value at key, or None if missing or wrong type."""
    val = data.get(key)
    return val if isinstance(val, str) else None


def get_dict(data: Mapping[str, object], key: str) -> dict[str, object] | None:
    """Return the dict value at key, or None if missing or wrong type."""
    val = data.get(key)
    return val if isinstance(val, dict) else None


def get_list_of_dicts(
    data: Mapping[str, object], key: str
) -> list[dict[str, object]]:
    """Return a list of dict items at key, filtering out non-dict elements."""
    val = data.get(key)
    if not isinstance(val, list):
        return []
    return [item for item in val if isinstance(item, dict)]


def get_float_opt(data: Mapping[str, object], key: str) -> float | None:
    """Return a float value at key (converting int/float), or None otherwise."""
    val = data.get(key)
    if isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    return None
