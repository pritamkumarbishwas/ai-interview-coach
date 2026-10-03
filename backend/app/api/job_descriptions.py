from fastapi import APIRouter, Depends, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import get_current_user, get_job_description_service
from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.models.job_description import JobDescription
from app.models.user import User
from app.schemas.job_description import (
    JobDescriptionInput,
    JobDescriptionResponse,
    JobDescriptionSummary,
)
from app.services.job_description_service import JobDescriptionService

router = APIRouter()


@router.post("", response_model=JobDescriptionResponse, status_code=status.HTTP_201_CREATED)
async def create_job_description(
    payload: JobDescriptionInput,
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: JobDescriptionService = Depends(get_job_description_service),
    _: None = Depends(rate_limit("job_description_create")),
) -> JobDescriptionResponse:
    return await service.create(db, current_user.id, payload)


@router.get("", response_model=list[JobDescriptionSummary])
async def list_job_descriptions(
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: JobDescriptionService = Depends(get_job_description_service),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[JobDescriptionSummary]:
    return await service.list(db, current_user.id, limit)


@router.get("/{jd_id}", response_model=JobDescription)
async def get_job_description(
    jd_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: JobDescriptionService = Depends(get_job_description_service),
) -> JobDescription:
    return await service.get(db, current_user.id, jd_id)


@router.delete("/{jd_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job_description(
    jd_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: JobDescriptionService = Depends(get_job_description_service),
) -> None:
    await service.delete(db, current_user.id, jd_id)
