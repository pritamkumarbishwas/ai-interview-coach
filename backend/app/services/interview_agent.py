"""Thin AG-UI adapter around the existing interview answer turn.

AG-UI is only a transport here: the interview state machine, ownership checks,
rate limiting and LLM work stay in :class:`InterviewService`. The adapter
validates the request before any event is streamed, then emits the protocol
events that mirror the single REST answer call.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

from ag_ui.core import (
    BaseEvent,
    RunAgentInput,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    StateSnapshotEvent,
    StepFinishedEvent,
    StepStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    UserMessage,
)
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import ValidationError

from app.core.exceptions import AppError, ConflictError, InvalidInputError
from app.schemas.answer import AnswerInput, AnswerResultOut
from app.schemas.interview import InterviewOut
from app.services.interview_service import InterviewService

logger = logging.getLogger(__name__)

ANSWER_STEP = "answer_submission"


@dataclass(frozen=True)
class AnswerTurn:
    """Validated inputs captured before the SSE response starts."""

    interview: InterviewOut
    question_id: str
    answer: str
    thread_id: str
    run_id: str


def _last_user_text(payload: RunAgentInput) -> str:
    for message in reversed(payload.messages):
        if isinstance(message, UserMessage):
            content = message.content
            if isinstance(content, str):
                return content
            return "".join(
                part.text for part in content if getattr(part, "type", None) == "text"
            )
    raise InvalidInputError("A user message is required.")


def _validated_answer(payload: RunAgentInput) -> str:
    try:
        return AnswerInput(answer=_last_user_text(payload)).answer
    except ValidationError as exc:
        raise InvalidInputError(
            "Answer must be between 1 and 20000 characters."
        ) from exc


def _snapshot(interview: InterviewOut) -> dict:
    """Explicit whitelist; answers, evaluations and reports never leave here."""
    current = None
    if interview.status != "completed":
        current = next(
            (
                question
                for question in interview.questions
                if question.id == interview.current_question_id
            ),
            None,
        )
    return {
        "interview_id": interview.id,
        "status": interview.status,
        "question_number": current.sequence if current else len(interview.questions),
        "total_questions": interview.target_questions,
        "answered_count": len(interview.answers),
        "current_question_id": interview.current_question_id,
        "current_question": (
            current.model_dump(mode="json", by_alias=True) if current else None
        ),
        "started_at": (
            interview.started_at.isoformat() if interview.started_at else None
        ),
        "completed": interview.status == "completed",
    }


async def prepare_answer_turn(
    db: AsyncIOMotorDatabase,
    user_id: str,
    interview_id: str,
    payload: RunAgentInput,
    service: InterviewService,
) -> AnswerTurn:
    """Validate everything that must fail with a normal HTTP error.

    In particular, a stale browser tab submits an old ``question_id``. Rejecting
    it here prevents the answer from being attributed to the current question
    when the SSE response has already committed a 200 status.
    """
    forwarded = payload.forwarded_props
    if not isinstance(forwarded, dict):
        raise InvalidInputError("forwardedProps.question_id is required.")
    question_id = forwarded.get("question_id")
    if not isinstance(question_id, str) or not question_id.strip():
        raise InvalidInputError("forwardedProps.question_id is required.")

    answer = _validated_answer(payload)
    interview = await service.get(db, user_id, interview_id)

    if interview.kind != "practice":
        raise ConflictError("AG-UI is only available for practice interviews.")
    if interview.status != "in_progress":
        raise ConflictError(f"Interview is {interview.status}; it cannot accept answers.")
    if interview.current_question_id != question_id:
        raise ConflictError("Only the current question can be answered.")

    return AnswerTurn(
        interview=interview,
        question_id=question_id,
        answer=answer,
        thread_id=payload.thread_id,
        run_id=payload.run_id,
    )


async def stream_answer_turn(
    db: AsyncIOMotorDatabase,
    user_id: str,
    interview_id: str,
    turn: AnswerTurn,
    service: InterviewService,
) -> AsyncIterator[BaseEvent]:
    """Emit one AG-UI run for a validated answer submission."""
    yield RunStartedEvent(thread_id=turn.thread_id, run_id=turn.run_id)
    yield StateSnapshotEvent(snapshot=_snapshot(turn.interview))
    yield StepStartedEvent(step_name=ANSWER_STEP)

    try:
        result = await service.answer_question(
            db, user_id, turn.question_id, AnswerInput(answer=turn.answer)
        )
    except AppError as exc:
        logger.warning(
            "AG-UI answer failed for interview %s: %s: %s",
            interview_id,
            type(exc).__name__,
            exc.message,
        )
        yield StepFinishedEvent(step_name=ANSWER_STEP)
        yield RunErrorEvent(message=exc.message, code=exc.code)
        return
    except Exception:
        logger.exception("AG-UI answer crashed for interview %s", interview_id)
        yield StepFinishedEvent(step_name=ANSWER_STEP)
        yield RunErrorEvent(message="Internal server error", code="internal_error")
        return

    yield StepFinishedEvent(step_name=ANSWER_STEP)

    try:
        updated = await service.get(db, user_id, interview_id)
        yield StateSnapshotEvent(snapshot=_snapshot(updated))
    except Exception:
        logger.exception("AG-UI snapshot refresh failed for interview %s", interview_id)
        yield RunErrorEvent(
            message="Could not refresh the interview state.", code="internal_error"
        )
        return

    if result.next_question is not None:
        message_id = uuid.uuid4().hex
        yield TextMessageStartEvent(message_id=message_id, role="assistant")
        yield TextMessageContentEvent(
            message_id=message_id, delta=result.next_question.text
        )
        yield TextMessageEndEvent(message_id=message_id)

    yield RunFinishedEvent(
        thread_id=turn.thread_id,
        run_id=turn.run_id,
        result=_result_payload(result),
    )


def _result_payload(result: AnswerResultOut) -> dict:
    return result.model_dump(mode="json", by_alias=True)
