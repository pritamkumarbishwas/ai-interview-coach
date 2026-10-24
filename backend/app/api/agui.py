"""AG-UI transport endpoint for the practice interview answer turn."""

from ag_ui.core import RunAgentInput
from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from sse_starlette import EventSourceResponse, ServerSentEvent

from app.api.deps import get_current_user, get_interview_service
from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import FeatureUnavailableError
from app.core.rate_limit import rate_limit
from app.models.user import User
from app.services.interview_agent import prepare_answer_turn, stream_answer_turn
from app.services.interview_service import InterviewService

router = APIRouter()


def _sse(event) -> ServerSentEvent:
    return ServerSentEvent(data=event.model_dump_json(by_alias=True), sep="\n")


@router.post("/interviews/{interview_id}")
async def answer_interview(
    interview_id: str,
    payload: RunAgentInput,
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: InterviewService = Depends(get_interview_service),
    _: None = Depends(rate_limit("answer_submission")),
) -> EventSourceResponse:
    """Stream one AG-UI run that records an answer and returns the next question."""
    if not settings.agui_enabled:
        raise FeatureUnavailableError("AG-UI is not enabled on this deployment.")

    turn = await prepare_answer_turn(
        db, current_user.id, interview_id, payload, service
    )

    async def events():
        async for event in stream_answer_turn(
            db, current_user.id, interview_id, turn, service
        ):
            yield _sse(event)

    return EventSourceResponse(events(), ping=15)
