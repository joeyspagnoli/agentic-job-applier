"""Enforce dependency-policy and test-discovery guardrails."""

from __future__ import annotations

import tomllib
from pathlib import Path

import scripts.test_fetchers as smoke_script


def test_uv_lock_excludes_known_vulnerable_versions() -> None:
    """Verify lockfile does not contain known vulnerable package versions.

    Purpose:
        Keep dependency CVE regressions from re-entering the lockfile.
    Args:
        None.
    Output:
        Returns `None`; the test passes when vulnerable versions are absent.
    """

    lock_path = Path(__file__).resolve().parent.parent / "uv.lock"
    with open(lock_path, "rb") as lock_file:
        lock_data = tomllib.load(lock_file)

    installed_versions = {
        package["name"]: package["version"] for package in lock_data.get("package", [])
    }

    assert installed_versions.get("authlib") != "1.6.6"
    assert installed_versions.get("cryptography") != "46.0.3"
    assert installed_versions.get("markdownify") != "0.13.1"
    assert installed_versions.get("protobuf") != "6.33.4"
    assert installed_versions.get("python-multipart") != "0.0.21"


def test_manual_smoke_script_is_not_pytest_collectable() -> None:
    """Verify manual smoke script stays out of automated pytest collection.

    Purpose:
        Prevent `scripts/test_fetchers.py` from being treated as automated unit
        tests in full-suite runs.
    Args:
        None.
    Output:
        Returns `None`; the test passes when module-level collection is disabled
        and no callable uses a `test_` prefix.
    """

    assert smoke_script.__test__ is False

    callable_names = [
        name for name, value in vars(smoke_script).items() if callable(value)
    ]
    assert all(not name.startswith("test_") for name in callable_names)

