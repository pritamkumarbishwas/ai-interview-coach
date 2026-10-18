from pydantic import BaseModel


class ModelUsage(BaseModel):
    model: str
    calls: int
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float


class UsageSummary(BaseModel):
    """Aggregate LLM token usage and estimated cost over a window."""

    days: int
    calls: int
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    by_model: list[ModelUsage]
