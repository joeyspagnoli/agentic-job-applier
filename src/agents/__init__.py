"""ADK agents used by the application.

This package is intentionally lightweight: agents should be importable without
requiring model credentials.
"""

from .root_apply_decider import build_root_agent

__all__ = ["build_root_agent"]
