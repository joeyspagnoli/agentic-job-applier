"""Enforce test-hygiene guardrails from the repository test plan."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from scripts import process_new_jobs


def test_orchestrator_failure_tests_avoid_unordered_limit_queries() -> None:
    """Verify orchestrator failure tests use deterministic `ORDER BY` clauses.

    Purpose:
        Prevent nondeterministic assertion reads as crawl-history test coverage
        expands over time.
    Args:
        None.
    Output:
        Returns `None`; test passes when `LIMIT 1` queries include `ORDER BY`.
    """

    file_path = Path(__file__).resolve().parent / "test_orchestrator_failures.py"
    content = file_path.read_text(encoding="utf-8")

    assert "LIMIT 1" in content
    assert "ORDER BY id DESC LIMIT 1" in content
    assert "ORDER BY date DESC" in content


@pytest.mark.asyncio
async def test_process_once_public_interface_delegates_to_private_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify public `process_once` API delegates with identical arguments.

    Purpose:
        Encourage test coverage to target public worker interfaces while still
        ensuring argument flow remains correct. The `provider` kwarg is optional
        on the public wrapper; when omitted the wrapper resolves it from env.
    Args:
        monkeypatch: Pytest fixture used to intercept private helper call.
    Output:
        Returns `None`; test passes when delegation preserves all arguments.
    """

    captured: dict[str, object] = {}
    sentinel_provider = object()

    async def fake_process_once(
        *,
        db: object,
        limit: int,
        provider: object,
        max_retries: int,
        backoff_seconds: int,
        backoff_multiplier: int,
    ) -> int:
        """Capture delegated arguments from public wrapper for assertions.

        Purpose:
            Validate argument forwarding behavior without running live logic.
        Args:
            db: Database manager provided by caller.
            limit: Batch size from caller.
            provider: Configured AI provider forwarded from public wrapper.
            max_retries: Max retries from caller.
            backoff_seconds: Base retry delay from caller.
            backoff_multiplier: Retry multiplier from caller.
        Output:
            Returns deterministic processed count.
        """

        _ = db
        captured["limit"] = limit
        captured["provider"] = provider
        captured["max_retries"] = max_retries
        captured["backoff_seconds"] = backoff_seconds
        captured["backoff_multiplier"] = backoff_multiplier
        return 9

    monkeypatch.setattr(process_new_jobs, "_process_once", fake_process_once)
    # Stub `build_provider_from_env` so we can assert provider forwarding
    # without needing a real API key in the test environment.
    monkeypatch.setattr(
        process_new_jobs,
        "build_provider_from_env",
        lambda: sentinel_provider,
    )

    processed = await process_new_jobs.process_once(
        db=object(),  # type: ignore[arg-type]
        limit=7,
        max_retries=4,
        backoff_seconds=11,
        backoff_multiplier=5,
    )

    assert processed == 9
    assert captured["limit"] == 7
    assert captured["provider"] is sentinel_provider
    assert captured["max_retries"] == 4
    assert captured["backoff_seconds"] == 11
    assert captured["backoff_multiplier"] == 5


def test_apply_decider_tests_use_structural_prompt_assertions() -> None:
    """Verify prompt tests assert stable structural markers, not profile prose.

    Purpose:
        Keep prompt payload tests resilient to user-customized candidate profile
        content while preserving meaningful section-level assertions.
    Args:
        None.
    Output:
        Returns `None`; test passes when brittle profile phrase is absent.
    """

    file_path = Path(__file__).resolve().parent / "test_apply_decider.py"
    content = file_path.read_text(encoding="utf-8")

    assert "Prompt-Safety Rules" in content
    assert "US roles only" not in content


def test_process_once_public_signature_is_documented_and_stable() -> None:
    """Verify public `process_once` signature retains expected parameters.

    Purpose:
        Guard against accidental API churn in script-facing helper signatures.
        The `provider` kwarg was added in Phase G to accept a pre-built provider
        for testing; it is optional (defaults to env resolution).
    Args:
        None.
    Output:
        Returns `None`; test passes when expected keyword parameters exist.
    """

    signature = inspect.signature(process_new_jobs.process_once)
    expected_params = {
        "db",
        "limit",
        "provider",
        "max_retries",
        "backoff_seconds",
        "backoff_multiplier",
    }
    assert set(signature.parameters.keys()) == expected_params
