"""One recorded LLM call, for cost tracking and budgeting (Phase 9).

Append-only and best-effort: a tracking failure must never fail the LLM call it
describes. ``actor_id`` is the staff/practice user behind the request when one
could be resolved; screening guests have no ``User`` and leave it null.
"""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class LlmUsage(BaseModel):
    id: str | None = Field(default=None, alias="_id")
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    actor_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(populate_by_name=True)
