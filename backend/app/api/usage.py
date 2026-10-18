"""LLM cost visibility (Phase 9).

Admin-only aggregate of recorded token usage and estimated spend. The per-call
records themselves are never exposed (they carry actor ids); this is a rollup
for budgeting.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import require_admin
from app.core.database import get_db
from app.models.user import User
from app.repositories.llm_usage_repository import llm_usage_repository
from app.schemas.usage import ModelUsage, UsageSummary

router = APIRouter()


@router.get("/summary", response_model=UsageSummary)
async def get_usage_summary(
    _: User = Depends(require_admin),
    db: AsyncIOMotorDatabase = Depends(get_db),
    days: int = Query(default=30, ge=1, le=365),
) -> UsageSummary:
    """Estimated LLM spend over the last `days` (admin-only)."""
    since = (datetime.now(UTC) - timedelta(days=days)).replace(tzinfo=None)
    totals = await llm_usage_repository.totals(db, since)
    by_model = await llm_usage_repository.by_model(db, since)
    return UsageSummary(
        days=days,
        calls=totals["calls"],
        prompt_tokens=totals["prompt_tokens"],
        completion_tokens=totals["completion_tokens"],
        cost_usd=totals["cost_usd"],
        by_model=[ModelUsage(**row) for row in by_model],
    )
