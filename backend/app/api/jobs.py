from fastapi import APIRouter, Depends, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import get_job_service, require_recruiter, require_staff
from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.models.user import User
from app.schemas.job import (
    JobCreate,
    JobOut,
    JobSummary,
    JobUpdate,
    ReviewerAssignment,
)
from app.services.job_service import JobService

router = APIRouter()


@router.post("", response_model=JobOut, status_code=status.HTTP_201_CREATED)
async def create_job(
    payload: JobCreate,
    current_user: User = Depends(require_recruiter),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: JobService = Depends(get_job_service),
    _: None = Depends(rate_limit("job_create")),
) -> JobOut:
    return await service.create(db, current_user, payload)


@router.get("", response_model=list[JobSummary])
async def list_jobs(
    current_user: User = Depends(require_staff),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: JobService = Depends(get_job_service),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[JobSummary]:
    """Recruiters see their own jobs, admins all, reviewers their assignments."""
    return await service.list(db, current_user, limit)


@router.get("/{job_id}", response_model=JobOut)
async def get_job(
    job_id: str,
    current_user: User = Depends(require_staff),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: JobService = Depends(get_job_service),
) -> JobOut:
    return await service.get(db, current_user, job_id)


@router.patch("/{job_id}", response_model=JobOut)
async def update_job(
    job_id: str,
    payload: JobUpdate,
    current_user: User = Depends(require_recruiter),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: JobService = Depends(get_job_service),
) -> JobOut:
    return await service.update(db, current_user, job_id, payload)


@router.put("/{job_id}/reviewers", response_model=JobOut)
async def set_job_reviewers(
    job_id: str,
    payload: ReviewerAssignment,
    current_user: User = Depends(require_recruiter),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: JobService = Depends(get_job_service),
) -> JobOut:
    """Assign the reviewers who may read this job's pipeline and decide."""
    return await service.set_reviewers(db, current_user, job_id, payload.reviewer_ids)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: str,
    current_user: User = Depends(require_recruiter),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: JobService = Depends(get_job_service),
) -> None:
    await service.delete(db, current_user, job_id)
