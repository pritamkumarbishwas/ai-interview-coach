from fastapi import APIRouter, Depends, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import get_current_user, get_interview_service
from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.models.user import User
from app.schemas.interview import (
    CurrentQuestionOut,
    InterviewCreate,
    InterviewOut,
    InterviewSummary,
)
from app.schemas.report import ReportOut
from app.services.interview_service import InterviewService

router = APIRouter()


@router.post("", response_model=InterviewOut, status_code=status.HTTP_201_CREATED)
async def create_interview(
    payload: InterviewCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: InterviewService = Depends(get_interview_service),
) -> InterviewOut:
    return await service.create(db, current_user.id, payload)


@router.get("", response_model=list[InterviewSummary])
async def list_interviews(
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: InterviewService = Depends(get_interview_service),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[InterviewSummary]:
    return await service.list(db, current_user.id, limit)


@router.get("/{interview_id}", response_model=InterviewOut)
async def get_interview(
    interview_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: InterviewService = Depends(get_interview_service),
) -> InterviewOut:
    return await service.get(db, current_user.id, interview_id)


@router.post("/{interview_id}/start", response_model=CurrentQuestionOut)
async def start_interview(
    interview_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: InterviewService = Depends(get_interview_service),
    _: None = Depends(rate_limit("interview_start")),
) -> CurrentQuestionOut:
    """Transition `created -> in_progress` and generate the first question."""
    return await service.start(db, current_user.id, interview_id)


@router.get("/{interview_id}/current-question", response_model=CurrentQuestionOut)
async def get_current_question(
    interview_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: InterviewService = Depends(get_interview_service),
    _: None = Depends(rate_limit("interview_question")),
) -> CurrentQuestionOut:
    return await service.current_question(db, current_user.id, interview_id)


@router.get("/{interview_id}/report", response_model=ReportOut)
async def get_interview_report(
    interview_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: InterviewService = Depends(get_interview_service),
    _: None = Depends(rate_limit("interview_report")),
) -> ReportOut:
    """The final report; generated once and cached on the interview document."""
    return await service.report(db, current_user.id, interview_id)
