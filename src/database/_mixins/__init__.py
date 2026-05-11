"""Internal mixin modules for `DatabaseManager`.

The mixins split the monolithic database manager into concern-focused
classes that share a small `_BaseMixin` for typed access to the active
SQLite connection. The public `DatabaseManager` class composes every
mixin in `src/database/db_manager.py`.
"""

from __future__ import annotations

from src.database._mixins.agent_gate import AgentGateMixin
from src.database._mixins.apply import ApplyMixin
from src.database._mixins.base import _BaseMixin
from src.database._mixins.costs import CostsMixin
from src.database._mixins.failure_resets import FailureResetsMixin
from src.database._mixins.jobs import JobsMixin
from src.database._mixins.review import ReviewMixin
from src.database._mixins.system_settings import SystemSettingsMixin
from src.database._mixins.tailor import TailorMixin
from src.database._mixins.telemetry import TelemetryMixin

__all__ = [
    "AgentGateMixin",
    "ApplyMixin",
    "CostsMixin",
    "FailureResetsMixin",
    "JobsMixin",
    "ReviewMixin",
    "SystemSettingsMixin",
    "TailorMixin",
    "TelemetryMixin",
    "_BaseMixin",
]
