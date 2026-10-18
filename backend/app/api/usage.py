"""LLM cost visibility and per-role quota status (Phase 9).

The cost summary is an admin-only aggregate of recorded token usage and
estimated spend; the per-call records themselves are never exposed (they carry
actor ids). The quota view lets any staff member see their own daily usage
against the limits configured for their role.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import get_quota_service, require_admin, require_staff
from app.core.database import get_db
from app.models.user import User
from app.repositories.llm_usage_repository import llm_usage_repository
from app.schemas.quota import QuotaSummary
from app.schemas.usage import ModelUsage, UsageSummary
from app.services.quota_service import QuotaService

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


@router.get("/quotas", response_model=QuotaSummary)
async def get_my_quotas(
    user: User = Depends(require_staff),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: QuotaService = Depends(get_quota_service),
) -> QuotaSummary:
    """The caller's daily usage against each per-role quota."""
    return await service.usage(db, user)

