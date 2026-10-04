from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import get_current_user, get_dashboard_service
from app.core.database import get_db
from app.models.user import User
from app.schemas.dashboard import DashboardStats
from app.services.dashboard_service import DashboardService

router = APIRouter()


@router.get("/stats", response_model=DashboardStats)
async def dashboard_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: DashboardService = Depends(get_dashboard_service),
) -> DashboardStats:
    """Counts, average score, weak/strong topics, and recent interviews."""
    return await service.stats(db, current_user.id)
