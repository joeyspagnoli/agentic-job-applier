"""Late-bound fetcher-class resolution shared by per-fetcher modules.

Existing tests monkey-patch fetcher classes on the top-level ``main``
module (e.g. ``monkeypatch.setattr(main, "GreenhouseFetcher", FakeFetcher)``
and ``patch("main.LinkedInFetcher", ...)``).  Because the per-fetcher
modules call into the underlying class indirectly, they perform the
lookup through ``main`` at call time so the patched attribute is honored
while keeping the production import path intact.
"""

from __future__ import annotations

import sys
from typing import TypeVar, cast

_T = TypeVar("_T")


def resolve_fetcher_attr(name: str, default: _T) -> _T:
    """Resolve a fetcher attribute via the ``main`` module with fallback.

    Purpose:
        Honor the existing test pattern of patching fetcher classes on
        ``main`` while still letting per-fetcher modules use the production
        implementation when no patch is in effect.
    Args:
        name: Attribute name to look up on the ``main`` module (for example
            ``"GreenhouseFetcher"``).
        default: Production value used when ``main`` is not yet imported or
            does not expose the requested attribute.
    Output:
        Returns the patched attribute when present, otherwise ``default``.
    """

    main_module = sys.modules.get("main")
    if main_module is None:
        return default
    candidate = getattr(main_module, name, None)
    if candidate is None:
        return default
    # ``getattr`` strips static typing back to ``Any``; cast back to the
    # documented attribute type so callers stay strictly typed.
    return cast(_T, candidate)
