"""Public read-only API for ATS / integration partners (Phase 8).

Authenticated with an ``X-API-Key`` header rather than a user session. A key
acts on behalf of the staff user that created it, so every response is scoped to
that user's own jobs and candidates — a key can never read another tenant's
data. The surface is intentionally read-only: all writes (decisions, invites)
stay in the human UI.
"""

from fastapi import APIRouter, Depends, Query, Response
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import (
    get_job_service,
    get_screening_service,
    require_api_key,
)
from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.models.analytics import JobAnalytics
from app.models.api_key import ApiKey
from app.models.user import User
from app.schemas.invitation import ShortlistEntry
from app.schemas.job import JobSummary
from app.services.job_service import JobService
from app.services.screening_service import ScreeningService

router = APIRouter()

NO_STORE = "private, no-store"


def _owner(key: ApiKey) -> User:
    """A stand-in identity for the key's owner.

    Deliberately *owner-scoped only*: even an admin's key must not read another
    user's data through the public API, so the stand-in never carries an
    elevated role (a ``recruiter`` resolves to owner-only access everywhere).
    """
    return User(
        id=key.created_by,
        name="api-key",
        email="",
        password_hash="",
        role="recruiter",
    )


@router.get("/jobs", response_model=list[JobSummary])
async def list_jobs(
    response: Response,
    key: ApiKey = Depends(require_api_key),
    db: AsyncIOMotorDatabase = Depends(get_db),
    jobs: JobService = Depends(get_job_service),
    limit: int = Query(default=50, ge=1, le=200),
    _: None = Depends(rate_limit("public_api")),
) -> list[JobSummary]:
    """List the requisitions visible to the key's owner."""
    response.headers["Cache-Control"] = NO_STORE
    return await jobs.list(db, _owner(key), limit)


@router.get("/jobs/{job_id}/candidates", response_model=list[ShortlistEntry])
async def list_job_candidates(
    job_id: str,
    response: Response,
    key: ApiKey = Depends(require_api_key),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ScreeningService = Depends(get_screening_service),
    _: None = Depends(rate_limit("public_api")),
) -> list[ShortlistEntry]:
    """Ranked, advisory candidates for one requisition (read-only)."""
    response.headers["Cache-Control"] = NO_STORE
    return await service.shortlist(db, _owner(key), job_id)


@router.get("/jobs/{job_id}/metrics", response_model=JobAnalytics)
async def job_metrics(
    job_id: str,
    response: Response,
    key: ApiKey = Depends(require_api_key),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ScreeningService = Depends(get_screening_service),
    _: None = Depends(rate_limit("public_api")),
) -> JobAnalytics:
    """Aggregate funnel + distribution metrics for one requisition."""
    response.headers["Cache-Control"] = NO_STORE
    return await service.analytics(db, _owner(key), job_id)
