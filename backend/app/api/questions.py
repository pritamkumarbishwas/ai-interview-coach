from fastapi import APIRouter, Depends, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import get_current_user, get_interview_service
from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.models.user import User
from app.schemas.answer import AnswerInput, AnswerResultOut
from app.services.interview_service import InterviewService

router = APIRouter()


@router.post(
    "/{question_id}/answer",
    response_model=AnswerResultOut,
    status_code=status.HTTP_200_OK,
)
async def submit_answer( 
    question_id: str,
    payload: AnswerInput,
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: InterviewService = Depends(get_interview_service),
    _: None = Depends(rate_limit("answer_submission")),
) -> AnswerResultOut:
    """Score the candidate's answer and return it with the next question."""
    return await service.answer_question(db, current_user.id, question_id, payload)
