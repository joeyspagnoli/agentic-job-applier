"""Register custom per-model prices with litellm so cost_per_token() returns
the rates this codebase relies on regardless of the installed litellm
version's bundled price map.

Called once at process startup (api/main.py) and once at script startup
(scripts/process_apply_jobs.py __main__). Idempotent.

Prices verified 2026-05-25 against OpenAI's published API pricing.
"""

from __future__ import annotations

from loguru import logger

# Per-token rates ($/token). Multiply by 1e-6 to convert $/1M-tokens.
_M = 1e-6

_PRICES: dict[str, dict[str, float | str]] = {
    "gpt-5-mini": {
        "input_cost_per_token": 0.25 * _M,
        "output_cost_per_token": 2.00 * _M,
        "cache_read_input_token_cost": 0.025 * _M,
        "litellm_provider": "openai",
        "mode": "chat",
    },
    "gpt-5.4": {
        "input_cost_per_token": 2.50 * _M,
        "output_cost_per_token": 15.00 * _M,
        "cache_read_input_token_cost": 0.25 * _M,
        "litellm_provider": "openai",
        "mode": "chat",
    },
    "gpt-5.4-mini": {
        "input_cost_per_token": 0.75 * _M,
        "output_cost_per_token": 4.50 * _M,
        "cache_read_input_token_cost": 0.075 * _M,
        "litellm_provider": "openai",
        "mode": "chat",
    },
}


def register_custom_prices() -> None:
    """Idempotently overlay the codebase's authoritative model prices on top
    of litellm's bundled map. Logs each registration at INFO so a startup
    log line confirms the override.
    """

    try:
        import litellm
    except ImportError:
        logger.warning("litellm not installed; skipping custom price registration")
        return

    litellm.register_model({m: spec for m, spec in _PRICES.items()})
    # Also register the openai/-prefixed form, which is what some call sites
    # pass to cost_per_token.
    litellm.register_model({f"openai/{m}": spec for m, spec in _PRICES.items()})

    for m, spec in _PRICES.items():
        logger.info(
            "Registered price: {} input=${:.4f}/1M output=${:.4f}/1M cache=${:.4f}/1M",
            m,
            float(spec["input_cost_per_token"]) * 1_000_000,
            float(spec["output_cost_per_token"]) * 1_000_000,
            float(spec["cache_read_input_token_cost"]) * 1_000_000,
        )
