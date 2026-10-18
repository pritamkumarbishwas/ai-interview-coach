"""LLM price book (Phase 9 cost tracking).

USD per 1M tokens, split into (input, output). These are *defaults* for the
models this deployment ships with and must be reconciled with the provider's
current list prices; deployments can override any entry (and price models the
table does not know) via ``LLM_PRICING_OVERRIDES``. An unknown model is priced
at 0.0 and logged once, so a missing entry never loses token counts.
"""

import logging

logger = logging.getLogger(__name__)

# Known models: {model_name: (usd_per_1m_input, usd_per_1m_output)}.
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    # Groq-hosted open models.
    "openai/gpt-oss-20b": (0.10, 0.50),
    "openai/gpt-oss-120b": (0.15, 0.75),
    "llama-3.3-70b-versatile": (0.59, 0.79),
    "llama-3.1-8b-instant": (0.05, 0.08),
}

# Models already warned about, so a hot path logs each unknown model once.
_warned: set[str] = set()


def resolve_pricing(model: str, overrides: dict[str, tuple[float, float]]) -> tuple[float, float]:
    """Return ``(input, output)`` USD-per-1M-token prices for ``model``."""
    if model in overrides:
        return overrides[model]
    if model in MODEL_PRICING:
        return MODEL_PRICING[model]
    if model not in _warned:
        _warned.add(model)
        logger.warning(
            "No price configured for model %r; recording tokens with cost 0.0", model
        )
    return (0.0, 0.0)


def estimate_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    overrides: dict[str, tuple[float, float]] | None = None,
) -> float:
    """Estimate USD cost for one call, rounded to 6 decimal places."""
    price_in, price_out = resolve_pricing(model, overrides or {})
    cost = (prompt_tokens / 1_000_000) * price_in + (
        completion_tokens / 1_000_000
    ) * price_out
    return round(cost, 6)
