"""Interview use-cases: creation, state machine and one-at-a-time questions."""

import json
import logging
import uuid

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.exceptions import ConflictError, NotFoundError, ServiceUnavailableError
from app.models.interview import Interview, Question, can_transition
from app.prompts.templates import (
    GENERATE_QUESTION_PROMPT,
    MAX_CONTEXT_CHARS,
)
from app.repositories.interview_repository import InterviewRepository
from app.repositories.job_description_repository import JobDescriptionRepository
from app.repositories.resume_repository import ResumeRepository
from app.schemas.interview import (
    CurrentQuestionOut,
    InterviewCreate,
    InterviewOut,
    InterviewSummary,
    QuestionGeneration,
    QuestionOut,
)
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)


def _context_block(data: object) -> str:
    """Compact, bounded JSON for the prompt (structured data is small)."""
    text = json.dumps(data, ensure_ascii=False, default=str)
    if len(text) > MAX_CONTEXT_CHARS:
        text = text[:MAX_CONTEXT_CHARS] + "..."
    return text


def _question_out(question: Question) -> QuestionOut:
    return QuestionOut(id=question.id, sequence=question.sequence, text=question.text)


def _interview_out(interview: Interview) -> InterviewOut:
    return InterviewOut(
        id=interview.id or "",
        resume_id=interview.resume_id,
        jd_id=interview.jd_id,
        role=interview.role,
        level=interview.level,
        type=interview.type,
        difficulty=interview.difficulty,
        status=interview.status,
        questions=[_question_out(q) for q in interview.questions],
        current_question_id=interview.current_question_id,
        created_at=interview.created_at,
        started_at=interview.started_at,
        completed_at=interview.completed_at,
    )


class InterviewService:
    def __init__(
        self,
        interviews: InterviewRepository,
        resumes: ResumeRepository,
        job_descriptions: JobDescriptionRepository,
    ) -> None:
        self._interviews = interviews
        self._resumes = resumes
        self._job_descriptions = job_descriptions

    async def create(
        self, db: AsyncIOMotorDatabase, user_id: str, payload: InterviewCreate
    ) -> InterviewOut:
        resume = await self._resumes.find_owned(db, payload.resume_id, user_id)
        if resume is None:
            raise NotFoundError("Resume not found")
        jd = await self._job_descriptions.find_owned(db, payload.jd_id, user_id)
        if jd is None:
            raise NotFoundError("Job description not found")

        interview = Interview(
            user_id=user_id,
            resume_id=payload.resume_id,
            jd_id=payload.jd_id,
            role=payload.role,
            level=payload.level,
            type=payload.type,
            difficulty=payload.difficulty,
        )
        interview.id = await self._interviews.insert(db, interview)
        return _interview_out(interview)

    async def list(
        self, db: AsyncIOMotorDatabase, user_id: str, limit: int
    ) -> list[InterviewSummary]:
        docs = await self._interviews.list_for_user(db, user_id, limit)
        return [
            InterviewSummary(
                id=doc["_id"],
                role=doc.get("role", ""),
                type=doc.get("type", "technical"),
                difficulty=doc.get("difficulty", "intermediate"),
                status=doc.get("status", "created"),
                question_count=len(doc.get("questions") or []),
                created_at=doc["created_at"],
            )
            for doc in docs
        ]

    async def get(self, db: AsyncIOMotorDatabase, user_id: str, interview_id: str) -> InterviewOut:
        interview = await self._require(db, user_id, interview_id)
        return _interview_out(interview)

    async def start(
        self, db: AsyncIOMotorDatabase, user_id: str, interview_id: str
    ) -> CurrentQuestionOut:
        """`created -> in_progress`, generating the first question.

        The question is generated *before* the transition, so a failed LLM
        call leaves the interview in `created` and the client can retry.
        """
        interview = await self._require(db, user_id, interview_id)
        if not can_transition(interview.status, "in_progress"):
            raise ConflictError(
                f"Interview is {interview.status}; only a created interview can be started."
            )

        first = await self._generate_question(db, interview, asked=[])
        doc = await self._interviews.start(db, interview_id, user_id, first)
        if doc is None:  # lost a concurrent start race
            raise ConflictError("Interview was already started.")

        started = Interview(**doc)
        question = started.current_question
        assert question is not None  # start() just pushed it
        return CurrentQuestionOut(
            interview_id=started.id or "",
            status=started.status,
            question=_question_out(question),
            question_number=question.sequence,
            total_asked=len(started.questions),
        )

    async def current_question(
        self, db: AsyncIOMotorDatabase, user_id: str, interview_id: str
    ) -> CurrentQuestionOut:
        interview = await self._require(db, user_id, interview_id)
        if interview.status == "created":
            raise ConflictError("Interview has not been started yet.")
        if interview.status == "completed":
            raise ConflictError("Interview is already completed.")

        question = interview.current_question
        if question is None:
            # Defensive path: an in-progress interview without a stored
            # question (e.g. written by an older version) — generate one now.
            question = await self._generate_question(db, interview, asked=[])
            doc = await self._interviews.append_question(db, interview_id, user_id, question)
            if doc is None:
                raise ConflictError("Interview is no longer in progress.")
            interview = Interview(**doc)
            question = interview.current_question
            assert question is not None

        return CurrentQuestionOut(
            interview_id=interview.id or "",
            status=interview.status,
            question=_question_out(question),
            question_number=question.sequence,
            total_asked=len(interview.questions),
        )

    async def _generate_question(
        self,
        db: AsyncIOMotorDatabase,
        interview: Interview,
        asked: list[str],
    ) -> Question:
        resume = await self._resumes.find_owned(db, interview.resume_id, interview.user_id)
        jd = await self._job_descriptions.find_owned(db, interview.jd_id, interview.user_id)
        if resume is None or jd is None:
            raise NotFoundError("Resume or job description no longer exists")

        resume_context = _context_block(resume.get("structured_data") or {})
        jd_context = _context_block(
            {
                "title": jd.get("title", ""),
                "company": jd.get("company", ""),
                "structured_data": jd.get("structured_data") or {},
            }
        )
        prompt = GENERATE_QUESTION_PROMPT.format(
            type=interview.type.replace("_", " "),
            role=interview.role,
            level=interview.level,
            difficulty=interview.difficulty,
            resume_context=resume_context,
            jd_context=jd_context,
            asked="\n".join(f"- {text}" for text in asked) or "(none yet)",
        )
        try:
            result = await llm_service.generate_structured(
                prompt, QuestionGeneration, max_retries=2
            )
        except Exception as exc:
            logger.error("Question generation failed: %s: %s", type(exc).__name__, exc)
            raise ServiceUnavailableError(
                "AI question generation is unavailable right now. Please try again later."
            ) from exc

        text = result.question.strip()
        if not text:
            raise ServiceUnavailableError("AI returned an empty question. Please try again.")
        return Question(
            id=uuid.uuid4().hex,
            sequence=len(interview.questions) + 1,
            text=text,
        )

    async def _require(
        self, db: AsyncIOMotorDatabase, user_id: str, interview_id: str
    ) -> Interview:
        doc = await self._interviews.find_owned(db, interview_id, user_id)
        if doc is None:
            raise NotFoundError("Interview not found")
        return Interview(**doc)
