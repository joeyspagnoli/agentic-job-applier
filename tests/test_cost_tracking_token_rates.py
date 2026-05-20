"""Cover token-based cost calculation in `src/utils/cost_tracking.py`.

Purpose:
    Lock the issue #41 item #5 contract — when cost-event metadata
    carries `model`, `prompt_tokens`, and `completion_tokens`, and the
    operator has set per-model rate env vars
    (`COST_RATE_<MODEL>_IN_USD` / `_OUT_USD`), the recorded cost is
    derived from those rates. When the env vars are missing or the
    metadata lacks tokens, the flat stage rate is used and (for
    unknown known-token cases) a warn-once log is emitted.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.utils import cost_tracking


class _FakeCostRecorder:
    """Capture every `record_cost_event` call without touching SQLite.

    Purpose:
        Let unit tests assert on the resolved `cost_usd` argument
        without spinning up a real `DatabaseManager` connection.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def record_cost_event(
        self,
        *,
        stage: str,
        cost_usd: float,
        job_hash: str | None = None,
        run_id: str | None = None,
        metadata_json: str | None = None,
    ) -> None:
        """Append one call snapshot to `self.calls`."""

        self.calls.append(
            {
                "stage": stage,
                "cost_usd": cost_usd,
                "job_hash": job_hash,
                "run_id": run_id,
                "metadata_json": metadata_json,
            }
        )


@pytest.fixture(autouse=True)
def _clear_warned_unknown_models() -> None:
    """Reset the module-level warn-once dedupe set between tests."""

    cost_tracking._WARNED_UNKNOWN_MODELS.clear()


@pytest.fixture(autouse=True)
def _clear_cost_rate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip every `COST_RATE_*` env var so tests start from a blank slate."""

    import os  # noqa: PLC0415 — used only inside the fixture

    for key in list(os.environ):
        if key.startswith("COST_RATE_"):
            monkeypatch.delenv(key, raising=False)


@pytest.mark.asyncio
async def test_records_token_based_cost_when_rates_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Known model + tokens → cost computed from per-1k rates."""

    monkeypatch.setenv("COST_RATE_OPENAI_GPT_5_MINI_IN_USD", "0.002")
    monkeypatch.setenv("COST_RATE_OPENAI_GPT_5_MINI_OUT_USD", "0.008")
    recorder = _FakeCostRecorder()

    await cost_tracking.record_stage_cost_event(
        db=recorder,  # type: ignore[arg-type]
        stage=cost_tracking.PIPELINE_STAGE_TAILOR,
        job_hash="abc",
        run_id="run-1",
        metadata={
            "model": "openai/gpt-5-mini",
            "prompt_tokens": 1000,
            "completion_tokens": 500,
        },
    )

    assert len(recorder.calls) == 1
    expected = (1000 / 1000) * 0.002 + (500 / 1000) * 0.008
    assert recorder.calls[0]["cost_usd"] == pytest.approx(expected)


@pytest.mark.asyncio
async def test_known_model_with_zero_tokens_records_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Known model + 0 tokens → records `0.0`, does NOT fall back to stage rate."""

    monkeypatch.setenv("COST_RATE_OPENAI_GPT_5_MINI_IN_USD", "0.002")
    monkeypatch.setenv("COST_RATE_OPENAI_GPT_5_MINI_OUT_USD", "0.008")
    monkeypatch.setenv("COST_RATE_TAILOR_USD", "0.5")
    recorder = _FakeCostRecorder()

    await cost_tracking.record_stage_cost_event(
        db=recorder,  # type: ignore[arg-type]
        stage=cost_tracking.PIPELINE_STAGE_TAILOR,
        job_hash="abc",
        run_id="run-2",
        metadata={
            "model": "openai/gpt-5-mini",
            "prompt_tokens": 0,
            "completion_tokens": 0,
        },
    )

    assert recorder.calls[0]["cost_usd"] == 0.0


@pytest.mark.asyncio
async def test_unknown_model_falls_back_to_stage_rate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown-model metadata records the flat stage rate as a fallback."""

    monkeypatch.setenv("COST_RATE_TAILOR_USD", "0.25")
    recorder = _FakeCostRecorder()

    await cost_tracking.record_stage_cost_event(
        db=recorder,  # type: ignore[arg-type]
        stage=cost_tracking.PIPELINE_STAGE_TAILOR,
        job_hash="abc",
        run_id="run-3",
        metadata={
            "model": "openai/some-new-model",
            "prompt_tokens": 100,
            "completion_tokens": 50,
        },
    )

    assert recorder.calls[0]["cost_usd"] == 0.25


@pytest.mark.asyncio
async def test_unknown_model_emits_warning_only_once_per_model(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Repeated calls with the same unknown model warn exactly once.

    Purpose:
        Guard against log flooding when a misconfigured model keeps
        emitting cost events.
    """

    # Forward loguru records through stdlib so caplog can capture them.
    from loguru import logger  # noqa: PLC0415 — local import keeps test self-contained

    handler_id = logger.add(
        caplog.handler, format="{message}", level="WARNING", filter=lambda _r: True
    )

    monkeypatch.setenv("COST_RATE_TAILOR_USD", "0.25")
    recorder = _FakeCostRecorder()

    metadata = {
        "model": "openai/some-new-model",
        "prompt_tokens": 100,
        "completion_tokens": 50,
    }

    try:
        with caplog.at_level("WARNING"):
            await cost_tracking.record_stage_cost_event(
                db=recorder,  # type: ignore[arg-type]
                stage=cost_tracking.PIPELINE_STAGE_TAILOR,
                job_hash="abc",
                run_id="run-4",
                metadata=metadata,
            )
            await cost_tracking.record_stage_cost_event(
                db=recorder,  # type: ignore[arg-type]
                stage=cost_tracking.PIPELINE_STAGE_TAILOR,
                job_hash="abc",
                run_id="run-5",
                metadata=metadata,
            )
    finally:
        logger.remove(handler_id)

    warnings_for_model = [
        record
        for record in caplog.records
        if "openai/some-new-model" in record.getMessage()
    ]
    assert len(warnings_for_model) == 1


@pytest.mark.asyncio
async def test_no_metadata_uses_stage_rate_without_warning(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Apply-stage calls with no model/token metadata keep the existing path."""

    monkeypatch.setenv("COST_RATE_APPLY_USD", "0.10")
    recorder = _FakeCostRecorder()

    with caplog.at_level("WARNING"):
        await cost_tracking.record_stage_cost_event(
            db=recorder,  # type: ignore[arg-type]
            stage=cost_tracking.PIPELINE_STAGE_APPLY,
            job_hash="abc",
            run_id="run-6",
            metadata=None,
        )

    assert recorder.calls[0]["cost_usd"] == 0.10
    no_token_warnings = [
        record for record in caplog.records if "no token rate" in record.getMessage()
    ]
    assert no_token_warnings == []


@pytest.mark.asyncio
async def test_malformed_token_counts_fall_back_to_stage_rate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """String / `None` / negative token fields drop back to the stage rate.

    Purpose:
        A malformed metadata payload must not crash cost recording or
        produce nonsense (e.g. negative) costs.
    """

    monkeypatch.setenv("COST_RATE_OPENAI_GPT_5_MINI_IN_USD", "0.002")
    monkeypatch.setenv("COST_RATE_OPENAI_GPT_5_MINI_OUT_USD", "0.008")
    monkeypatch.setenv("COST_RATE_TAILOR_USD", "0.50")
    recorder = _FakeCostRecorder()

    await cost_tracking.record_stage_cost_event(
        db=recorder,  # type: ignore[arg-type]
        stage=cost_tracking.PIPELINE_STAGE_TAILOR,
        job_hash="abc",
        run_id="run-7",
        metadata={
            "model": "openai/gpt-5-mini",
            "prompt_tokens": "1000",
            "completion_tokens": None,
        },
    )

    assert recorder.calls[0]["cost_usd"] == 0.50


def test_env_var_names_for_model_sanitizes_slashes_dots_and_dashes() -> None:
    """The model-name transform matches the documented pattern."""

    in_env, out_env = cost_tracking._env_var_names_for_model(
        "openai/gpt-5-mini"
    )

    assert in_env == "COST_RATE_OPENAI_GPT_5_MINI_IN_USD"
    assert out_env == "COST_RATE_OPENAI_GPT_5_MINI_OUT_USD"

    # Cover dot sanitization explicitly via a synthetic identifier so the
    # assertion is not coupled to the current default model name.
    in_env_dotted, _ = cost_tracking._env_var_names_for_model("foo/bar.baz")
    assert in_env_dotted == "COST_RATE_FOO_BAR_BAZ_IN_USD"
