"""Screening invitations.

``router`` is recruiter-facing (create/list/revoke/remind an invitation);
``public_router`` is the accountless candidate surface, addressed purely by the
magic-link token. Token responses are marked ``Cache-Control: private, no-store``
so an interview link is never cached by a shared proxy or browser history.
"""

from fastapi import APIRouter, Depends, Query, Response, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import get_screening_service, require_recruiter
from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.models.user import User
from app.schemas.answer import AnswerInput, AnswerResultOut
from app.schemas.interview import CurrentQuestionOut
from app.schemas.invitation import (
    InvitationCreate,
    InvitationOut,
    InvitationSessionOut,
    StartInterviewRequest,
)
from app.services.screening_service import ScreeningService

router = APIRouter()
public_router = APIRouter()

NO_STORE = "private, no-store"


@router.post("", response_model=InvitationOut, status_code=status.HTTP_201_CREATED)
async def create_invitation(
    payload: InvitationCreate,
    recruiter: User = Depends(require_recruiter),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ScreeningService = Depends(get_screening_service),
    _: None = Depends(rate_limit("invitation_create")),
) -> InvitationOut:
    return await service.create_invitation(db, recruiter, payload)


@router.get("", response_model=list[InvitationOut])
async def list_invitations(
    job_id: str,
    recruiter: User = Depends(require_recruiter),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ScreeningService = Depends(get_screening_service),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[InvitationOut]:
    return await service.list_invitations(db, recruiter.id or "", job_id, limit)


@router.delete("/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invitation(
    invitation_id: str,
    recruiter: User = Depends(require_recruiter),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ScreeningService = Depends(get_screening_service),
) -> None:
    await service.revoke(db, recruiter, invitation_id)


@router.post("/{invitation_id}/remind", response_model=InvitationOut)
async def remind_invitation(
    invitation_id: str,
    recruiter: User = Depends(require_recruiter),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ScreeningService = Depends(get_screening_service),
    _: None = Depends(rate_limit("invitation_remind")),
) -> InvitationOut:
    return await service.remind(db, recruiter, invitation_id)


@public_router.get("/{token}", response_model=InvitationSessionOut)
async def get_session(
    token: str,
    response: Response,
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ScreeningService = Depends(get_screening_service),
    _: None = Depends(rate_limit("screening_session")),
) -> InvitationSessionOut:
    """Pre-check: what this interview is and whether it can start now."""
    response.headers["Cache-Control"] = NO_STORE
    return await service.session(db, token)


@public_router.post("/{token}/start", response_model=CurrentQuestionOut)
async def start_interview(
    token: str,
    payload: StartInterviewRequest,
    response: Response,
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ScreeningService = Depends(get_screening_service),
    _: None = Depends(rate_limit("screening_start")),
) -> CurrentQuestionOut:
    response.headers["Cache-Control"] = NO_STORE
    return await service.start(db, token, payload.consent)


@public_router.get("/{token}/current-question", response_model=CurrentQuestionOut)
async def current_question(
    token: str,
    response: Response,
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ScreeningService = Depends(get_screening_service),
    _: None = Depends(rate_limit("screening_session")),
) -> CurrentQuestionOut:
    response.headers["Cache-Control"] = NO_STORE
    return await service.current_question(db, token)


@public_router.post(
    "/{token}/questions/{question_id}/answer", response_model=AnswerResultOut
)
async def answer_question(
    token: str,
    question_id: str,
    payload: AnswerInput,
    response: Response,
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ScreeningService = Depends(get_screening_service),
    _: None = Depends(rate_limit("screening_answer")),
) -> AnswerResultOut:
    response.headers["Cache-Control"] = NO_STORE
    return await service.answer(db, token, question_id, payload)
