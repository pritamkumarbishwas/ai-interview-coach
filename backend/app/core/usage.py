"""Per-request LLM usage recording (Phase 9 cost tracking).

The LLM client is a process-wide singleton with no request context, so usage is
attributed through a ``ContextVar`` that the HTTP middleware sets for the
duration of each request. Because ``asyncio`` copies the context when a task is
created, the completion-time scoring task (spawned inside a request) is
attributed to the same request. Recording is best-effort: a write failure is
logged, never raised into the LLM call path.
"""

import logging
from contextvars import ContextVar

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.core.pricing import estimate_cost
from app.models.llm_usage import LlmUsage
from app.repositories.llm_usage_repository import llm_usage_repository

logger = logging.getLogger(__name__)

usage_db: ContextVar[AsyncIOMotorDatabase | None] = ContextVar(
    "usage_db", default=None
)
usage_actor: ContextVar[str | None] = ContextVar("usage_actor", default=None)


async def record_llm_usage(
    provider: str, model: str, prompt_tokens: int, completion_tokens: int
) -> None:
    """Persist one LLM call's token usage and estimated cost (best-effort)."""
    if not settings.llm_cost_tracking_enabled:
        return
    db = usage_db.get()
    if db is None:
        # No request context (e.g. a direct unit call or a CLI task): skip.
        return
    try:
        await llm_usage_repository.insert(
            db,
            LlmUsage(
                provider=provider,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                cost_usd=estimate_cost(
                    model, prompt_tokens, completion_tokens, settings.llm_pricing_overrides
                ),
                actor_id=usage_actor.get(),
            ),
        )
    except Exception as exc:  # tracking must never break the LLM call
        logger.warning("Could not record LLM usage: %s", exc)
