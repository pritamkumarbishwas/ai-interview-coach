"""Interview use-cases: creation, state machine and one-at-a-time questions."""

import json
import logging
import uuid
from dataclasses import dataclass

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.exceptions import ConflictError, NotFoundError, ServiceUnavailableError
from app.models.answer import Answer, Evaluation
from app.models.interview import Interview, Question, can_transition
from app.models.report import Report
from app.prompts.templates import (
    EVALUATE_ANSWER_PROMPT,
    GENERATE_NEXT_QUESTION_PROMPT,
    GENERATE_QUESTION_PROMPT,
    GENERATE_REPORT_PROMPT,
    MAX_CONTEXT_CHARS,
    MAX_REPORT_CONTEXT_CHARS,
)
from app.repositories.interview_repository import InterviewRepository
from app.repositories.job_description_repository import JobDescriptionRepository
from app.repositories.resume_repository import ResumeRepository
from app.schemas.answer import AnswerInput, AnswerResultOut, EvaluationGeneration
from app.schemas.interview import (
    DEFAULT_TARGET_QUESTIONS,
    CurrentQuestionOut,
    InterviewCreate,
    InterviewOut,
    InterviewSummary,
    QuestionGeneration,
    QuestionOut,
)
from app.schemas.report import ReportGeneration, ReportOut
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)

# Topic score cutoffs (per-topic scores are means of 0-100 evaluations).
STRONG_TOPIC_MIN_SCORE = 70.0
WEAK_TOPIC_MAX_SCORE = 50.0


def _context_block(data: object, limit: int = MAX_CONTEXT_CHARS) -> str:
    """Compact, bounded JSON for the prompt (structured data is small)."""
    text = json.dumps(data, ensure_ascii=False, default=str)
    if len(text) > limit:
        text = text[:limit] + "..."
    return text


def _question_out(question: Question) -> QuestionOut:
    return QuestionOut(
        id=question.id,
        sequence=question.sequence,
        text=question.text,
        topic=question.topic,
    )


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
        target_questions=interview.target_questions,
        questions=[_question_out(q) for q in interview.questions],
        answers=interview.answers,
        current_question_id=interview.current_question_id,
        created_at=interview.created_at,
        started_at=interview.started_at,
        completed_at=interview.completed_at,
    )


def _covered_topics(interview: Interview) -> list[str]:
    """Unique topics already covered, in order of first appearance."""
    seen: list[str] = []
    for question in interview.questions:
        if question.topic and question.topic not in seen:
            seen.append(question.topic)
    return seen


def _mean(values: list[int] | list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 1)


@dataclass(frozen=True)
class ScoreAggregates:
    """Everything in the final report that is computed in code."""

    overall_score: float
    technical_score: float
    communication_score: float
    strong_topics: list[str]
    weak_topics: list[str]


def aggregate_scores(interview: Interview) -> ScoreAggregates:
    """Average the stored evaluations — the LLM never does this math.

    - overall: mean of each answer's evaluation.overall
    - technical: mean of the `technical` dimension across answers
    - communication: mean of the `structure` + `clarity` dimensions
    - topics bucket into strong (>= 70) / weak (< 50) by their mean score;
      unanswered questions are skipped, as are unlabeled topics.
    """
    answers = interview.answers
    if not answers:
        return ScoreAggregates(0.0, 0.0, 0.0, [], [])

    topic_scores: dict[str, list[int]] = {}
    topics_by_question = {question.id: question.topic for question in interview.questions}
    for answer in answers:
        topic = topics_by_question.get(answer.question_id, "")
        if topic:
            topic_scores.setdefault(topic, []).append(answer.evaluation.overall)
    means = {topic: _mean(values) for topic, values in topic_scores.items()}

    strong = [
        topic
        for topic, score in sorted(means.items(), key=lambda item: -item[1])
        if score >= STRONG_TOPIC_MIN_SCORE
    ]
    weak = [
        topic
        for topic, score in sorted(means.items(), key=lambda item: item[1])
        if score < WEAK_TOPIC_MAX_SCORE
    ]

    return ScoreAggregates(
        overall_score=_mean([answer.evaluation.overall for answer in answers]),
        technical_score=_mean([answer.evaluation.scores.technical for answer in answers]),
        communication_score=_mean(
            [
                score
                for answer in answers
                for score in (
                    answer.evaluation.scores.structure,
                    answer.evaluation.scores.clarity,
                )
            ]
        ),
        strong_topics=strong,
        weak_topics=weak,
    )


def _report_out(interview: Interview) -> ReportOut:
    report = interview.report
    assert report is not None  # callers checked before converting
    return ReportOut(
        interview_id=interview.id or "",
        overall_score=report.overall_score,
        technical_score=report.technical_score,
        communication_score=report.communication_score,
        strong_topics=report.strong_topics,
        weak_topics=report.weak_topics,
        topics_to_study=report.topics_to_study,
        narrative=report.narrative,
        preparation_plan=report.preparation_plan,
        generated_at=report.generated_at,
    )


def _performance_payload(interview: Interview) -> dict:
    """Aggregates plus one bounded entry per answered question.

    LLM-produced strings (topics, feedback, weaknesses) are unbounded, so
    every field is truncated here: a 20-question interview must still fit
    inside MAX_REPORT_CONTEXT_CHARS without mid-JSON cuts.
    """
    aggregates = aggregate_scores(interview)
    answers_by_question = {answer.question_id: answer for answer in interview.answers}
    return {
        "role": interview.role,
        "type": interview.type.replace("_", " "),
        "level": interview.level,
        "difficulty": interview.difficulty,
        "overall_score": aggregates.overall_score,
        "technical_score": aggregates.technical_score,
        "communication_score": aggregates.communication_score,
        "strong_topics": [topic[:100] for topic in aggregates.strong_topics],
        "weak_topics": [topic[:100] for topic in aggregates.weak_topics],
        "topics_to_study": [topic[:100] for topic in aggregates.weak_topics],
        "questions": [
            {
                "topic": question.topic[:100],
                "question": question.text[:160],
                "score": answers_by_question[question.id].evaluation.overall,
                "feedback": answers_by_question[question.id].evaluation.feedback[:200],
                "weaknesses": [
                    weakness[:150]
                    for weakness in answers_by_question[question.id].evaluation.weaknesses[:3]
                ],
            }
            for question in interview.questions
            if question.id in answers_by_question
        ],
    }


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
            target_questions=payload.target_questions,
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
                answered_count=len(doc.get("answers") or []),
                target_questions=doc.get("target_questions", DEFAULT_TARGET_QUESTIONS),
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

    async def answer_question(
        self,
        db: AsyncIOMotorDatabase,
        user_id: str,
        question_id: str,
        payload: AnswerInput,
    ) -> AnswerResultOut:
        """Evaluate an answer, record it, and produce the next question.

        The evaluation and next-question LLM calls happen before any write:
        if either fails the client gets a 503 and can resubmit without
        leaving a half-recorded answer. The interview completes automatically
        once `target_questions` answers have been scored; the final report
        is then generated after the write (its failure never blocks
        completion — the report endpoint backfills it later).
        """
        doc = await self._interviews.find_by_question(db, question_id, user_id)
        if doc is None:
            raise NotFoundError("Question not found")
        interview = Interview(**doc)

        if interview.status == "created":
            raise ConflictError("Interview has not been started yet.")
        if interview.status == "completed":
            raise ConflictError("Interview is already completed.")
        if interview.current_question_id != question_id:
            raise ConflictError("Only the current question can be answered.")

        question = interview.current_question
        assert question is not None  # current_question_id matched above

        evaluation = await self._evaluate(interview, question, payload.answer)

        answered = len(interview.answers) + 1
        completing = answered >= interview.target_questions
        next_question = None
        if not completing:
            next_question = await self._generate_next_question(
                db, interview, question, payload.answer, evaluation
            )

        answer = Answer(
            id=uuid.uuid4().hex,
            question_id=question_id,
            text=payload.answer,
            evaluation=evaluation,
        )
        updated_doc = await self._interviews.record_answer(
            db, interview.id or "", user_id, answer, next_question, completing
        )
        if updated_doc is None:  # concurrent/duplicate submission lost the race
            raise ConflictError("This answer was already submitted.")

        updated = Interview(**updated_doc)
        if updated.status == "completed":
            await self._try_cache_report(db, updated)
        return AnswerResultOut(
            question_id=question_id,
            status=updated.status,
            evaluation=evaluation,
            next_question=_question_out(next_question) if next_question else None,
            questions_answered=len(updated.answers),
            target_questions=updated.target_questions,
        )

    async def report(self, db: AsyncIOMotorDatabase, user_id: str, interview_id: str) -> ReportOut:
        """The cached final report, generated on first access if missing."""
        interview = await self._require(db, user_id, interview_id)
        if interview.status != "completed":
            raise ConflictError("The report is available once the interview is completed.")
        if interview.report is not None:
            return _report_out(interview)

        report = await self._generate_report(interview)
        doc = await self._interviews.set_report(db, interview.id or "", user_id, report)
        if doc is None:
            # A concurrent request cached a report first — use that one.
            refreshed = await self._require(db, user_id, interview_id)
            if refreshed.report is None:
                raise ConflictError("Interview is no longer completed.")
            return _report_out(refreshed)
        return _report_out(Interview(**doc))

    async def _try_cache_report(self, db: AsyncIOMotorDatabase, interview: Interview) -> None:
        """Generate the final report right after completion.

        A report failure must never undo a completed interview: the client
        backfills it later through `GET /interviews/{id}/report`.
        """
        try:
            report = await self._generate_report(interview)
            await self._interviews.set_report(db, interview.id or "", interview.user_id, report)
        except Exception as exc:
            logger.warning(
                "Report generation after completion failed: %s: %s", type(exc).__name__, exc
            )

    async def _generate_report(self, interview: Interview) -> Report:
        aggregates = aggregate_scores(interview)
        prompt = GENERATE_REPORT_PROMPT.format(
            type=interview.type.replace("_", " "),
            role=interview.role,
            level=interview.level,
            difficulty=interview.difficulty,
            performance_data=_context_block(
                _performance_payload(interview), MAX_REPORT_CONTEXT_CHARS
            ),
        )
        try:
            result = await llm_service.generate_structured(prompt, ReportGeneration, max_retries=2)
        except Exception as exc:
            logger.error("Report generation failed: %s: %s", type(exc).__name__, exc)
            raise ServiceUnavailableError(
                "AI report generation is unavailable right now. Please try again later."
            ) from exc

        narrative = result.narrative.strip()
        if not narrative:
            raise ServiceUnavailableError("AI returned an empty report. Please try again.")

        return Report(
            overall_score=aggregates.overall_score,
            technical_score=aggregates.technical_score,
            communication_score=aggregates.communication_score,
            strong_topics=aggregates.strong_topics,
            weak_topics=aggregates.weak_topics,
            topics_to_study=list(aggregates.weak_topics),
            narrative=narrative,
            preparation_plan=result.preparation_plan,
        )

    async def _evaluate(
        self, interview: Interview, question: Question, answer_text: str
    ) -> Evaluation:
        prompt = EVALUATE_ANSWER_PROMPT.format(
            type=interview.type.replace("_", " "),
            role=interview.role,
            level=interview.level,
            difficulty=interview.difficulty,
            question=question.text,
            answer=answer_text,
        )
        try:
            result = await llm_service.generate_structured(
                prompt, EvaluationGeneration, max_retries=2
            )
        except Exception as exc:
            logger.error("Answer evaluation failed: %s: %s", type(exc).__name__, exc)
            raise ServiceUnavailableError(
                "AI evaluation is unavailable right now. Please try again later."
            ) from exc
        return Evaluation(
            scores=result.scores,
            overall=result.scores.overall,
            strengths=result.strengths,
            weaknesses=result.weaknesses,
            feedback=result.feedback,
            improved_answer=result.improved_answer,
            next_step=result.next_step,
        )

    async def _generate_next_question(
        self,
        db: AsyncIOMotorDatabase,
        interview: Interview,
        previous: Question,
        answer_text: str,
        evaluation: Evaluation,
    ) -> Question:
        resume_context, jd_context = await self._load_context(db, interview)
        prompt = GENERATE_NEXT_QUESTION_PROMPT.format(
            type=interview.type.replace("_", " "),
            role=interview.role,
            level=interview.level,
            difficulty=interview.difficulty,
            resume_context=resume_context,
            jd_context=jd_context,
            previous_question=previous.text,
            candidate_answer=answer_text,
            feedback=evaluation.feedback,
            decision=evaluation.next_step,
            covered_topics=", ".join(_covered_topics(interview)) or "(none yet)",
        )
        return await self._ask_for_question(interview, prompt)

    async def _generate_question(
        self,
        db: AsyncIOMotorDatabase,
        interview: Interview,
        asked: list[str],
    ) -> Question:
        resume_context, jd_context = await self._load_context(db, interview)
        prompt = GENERATE_QUESTION_PROMPT.format(
            type=interview.type.replace("_", " "),
            role=interview.role,
            level=interview.level,
            difficulty=interview.difficulty,
            resume_context=resume_context,
            jd_context=jd_context,
            asked="\n".join(f"- {text}" for text in asked) or "(none yet)",
        )
        return await self._ask_for_question(interview, prompt)

    async def _load_context(
        self, db: AsyncIOMotorDatabase, interview: Interview
    ) -> tuple[str, str]:
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
        return resume_context, jd_context

    async def _ask_for_question(self, interview: Interview, prompt: str) -> Question:
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
            topic=result.topic.strip(),
        )

    async def _require(
        self, db: AsyncIOMotorDatabase, user_id: str, interview_id: str
    ) -> Interview:
        doc = await self._interviews.find_owned(db, interview_id, user_id)
        if doc is None:
            raise NotFoundError("Interview not found")
        return Interview(**doc)
