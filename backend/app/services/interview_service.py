"""Interview use-cases: creation, state machine and one-at-a-time questions."""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from weakref import WeakValueDictionary

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError, ServiceUnavailableError
from app.core.transcription import get_transcriber
from app.models.answer import Answer, Evaluation
from app.models.interview import (
    Interview,
    ProctoringEvent,
    ProctoringSession,
    Question,
    can_transition,
)
from app.models.report import Report
from app.prompts.templates import (
    EVALUATE_ANSWER_PROMPT,
    GENERATE_NEXT_QUESTION_EVALFREE_PROMPT,
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
    InterviewListOut,
    InterviewOut,
    InterviewResultsOut,
    InterviewSummary,
    QuestionGeneration,
    QuestionOut,
    ResultsSort,
)
from app.schemas.report import ReportGeneration, ReportOut
from app.services.llm_service import llm_service
from app.services.rag_service import rag_service
from app.services.recording_service import RecordingService

logger = logging.getLogger(__name__)

# Topic score cutoffs (per-topic scores are means of 0-100 evaluations).
STRONG_TOPIC_MIN_SCORE = 70.0
WEAK_TOPIC_MAX_SCORE = 50.0

# Values written by older versions/tests. Normalizing on read keeps one bad
# legacy document from turning a whole list response into a 500.
_DIFFICULTIES = {"beginner", "intermediate", "advanced"}
_DIFFICULTY_ALIASES = {
    "easy": "beginner",
    "medium": "intermediate",
    "hard": "advanced",
}
_INTERVIEW_TYPES = {"technical", "behavioral", "hr", "mixed", "system_design"}
_INTERVIEW_STATUSES = {"created", "in_progress", "completed"}
_INTERVIEW_KINDS = {"practice", "screening"}
_PROCTORING_MODES = {"off", "camera_only", "strict"}

# Cap the verbatim quotes stored per answer so a chatty model cannot bloat the
# evaluation document.
MAX_EVIDENCE_QUOTES = 5
MAX_RUBRIC_CHARS = 600

# Deferred-evaluation pipeline: bounded concurrency for the end-of-exam
# parallel evaluation calls, plus strong references so fire-and-forget
# background tasks are not garbage-collected mid-run.
_EVAL_CONCURRENCY = 4
_eval_semaphore = asyncio.Semaphore(_EVAL_CONCURRENCY)
_background_tasks: set[asyncio.Task] = set()
# Per-interview locks: the report backfill must not run the same interview's
# evaluation twice under concurrent requests.
# Weak values let locks disappear once no request/task references them, so the
# map does not grow without bound as interviews are created.
_report_locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()


def _report_lock(interview_id: str) -> asyncio.Lock:
    lock = _report_locks.get(interview_id)
    if lock is None:
        lock = asyncio.Lock()
        _report_locks[interview_id] = lock
    return lock


def _has_pending_evaluations(interview: Interview) -> bool:
    return any(answer.evaluation is None for answer in interview.answers)


def _rubric_block(interview: Interview) -> str:
    """Rubric dimensions for the evaluation prompt, bounded and safe.

    Practice interviews have no rubric, so the model picks its own label.
    """
    names = [" ".join(name.split()) for name in interview.rubric if name.strip()]
    if not names:
        return "(no fixed rubric — label the answer with the competency it best measures)"
    return ", ".join(names)[:MAX_RUBRIC_CHARS]


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
        created_at=question.created_at,
    )


def _interview_out(interview: Interview) -> InterviewOut:
    return InterviewOut(
        id=interview.id or "",
        resume_id=interview.resume_id,
        jd_id=interview.jd_id,
        role=interview.role,
        kind=interview.kind,
        level=interview.level,
        type=interview.type,
        difficulty=interview.difficulty,
        status=interview.status,
        proctoring_mode=interview.proctoring_mode,
        proctoring_session=interview.proctoring_session,
        target_questions=interview.target_questions,
        questions=[_question_out(q) for q in interview.questions],
        answers=interview.answers,
        recordings=interview.recordings,
        transcription_enabled=settings.transcription_provider != "none",
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
    - answers whose evaluation is still `None` (deferred, not yet run) are
      skipped entirely so a partially-evaluated interview never crashes.
    """
    answers = [a for a in interview.answers if a.evaluation is not None]
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
    evaluated = sum(1 for answer in interview.answers if answer.evaluation is not None)
    total = len(interview.answers)
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
        partial=evaluated < total,
        evaluated_answers=evaluated,
        total_answers=total,
    )


def _normalize_choice(value: object, allowed: set[str], default: str) -> str:
    return value if isinstance(value, str) and value in allowed else default


def _normalize_difficulty(value: object) -> str:
    text = value.strip().lower() if isinstance(value, str) else ""
    text = _DIFFICULTY_ALIASES.get(text, text)
    return text if text in _DIFFICULTIES else "intermediate"


def _normalize_target_questions(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        return DEFAULT_TARGET_QUESTIONS
    return max(1, min(20, value))


def _summary_out(doc: dict) -> InterviewSummary:
    report = doc.get("report")
    raw_score = report.get("overall_score") if isinstance(report, dict) else None
    score = (
        float(raw_score)
        if isinstance(raw_score, (int, float)) and not isinstance(raw_score, bool)
        else None
    )
    created_at = doc.get("created_at")
    if not isinstance(created_at, datetime):
        # The repository derives this from the ObjectId when possible; this is
        # the last-resort guard for documents with an unparseable id.
        created_at = datetime.now(UTC)
    completed_at = doc.get("completed_at")
    if not isinstance(completed_at, datetime):
        completed_at = None
    questions = doc.get("questions")
    answers = doc.get("answers")
    return InterviewSummary(
        id=str(doc["_id"]),
        role=str(doc.get("role") or "Interview"),
        kind=_normalize_choice(doc.get("kind"), _INTERVIEW_KINDS, "practice"),
        type=_normalize_choice(doc.get("type"), _INTERVIEW_TYPES, "technical"),
        difficulty=_normalize_difficulty(doc.get("difficulty")),
        status=_normalize_choice(doc.get("status"), _INTERVIEW_STATUSES, "created"),
        proctoring_mode=_normalize_choice(
            doc.get("proctoring_mode"), _PROCTORING_MODES, "off"
        ),
        question_count=len(questions) if isinstance(questions, list) else 0,
        answered_count=len(answers) if isinstance(answers, list) else 0,
        target_questions=_normalize_target_questions(doc.get("target_questions")),
        score=score,
        created_at=created_at,
        completed_at=completed_at,
    )


def _performance_payload(interview: Interview) -> dict:
    """Aggregates plus one bounded entry per answered question.

    LLM-produced strings (topics, feedback, weaknesses) are unbounded, so
    every field is truncated here: a 20-question interview must still fit
    inside MAX_REPORT_CONTEXT_CHARS without mid-JSON cuts.

    Answers whose evaluation is still `None` are skipped (deferred scoring
    has not finished for them yet).
    """
    aggregates = aggregate_scores(interview)
    answers_by_question = {
        answer.question_id: answer
        for answer in interview.answers
        if answer.evaluation is not None
    }
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
        recordings: RecordingService,
    ) -> None:
        self._interviews = interviews
        self._resumes = resumes
        self._job_descriptions = job_descriptions
        self._recordings = recordings

    async def create(
        self, db: AsyncIOMotorDatabase, user_id: str, payload: InterviewCreate
    ) -> InterviewOut:
        resume_id = payload.resume_id or ""
        if resume_id:
            resume = await self._resumes.find_owned(db, resume_id, user_id)
            if resume is None:
                raise NotFoundError("Resume not found")
            status = (resume.get("analysis") or {}).get("status")
            if status in {"pending", "processing"}:
                raise ConflictError(
                    "Resume analysis is still running. Try again when it is ready."
                )
            if status == "deleting":
                raise NotFoundError("Resume not found")
        jd = await self._job_descriptions.find_owned(db, payload.jd_id, user_id)
        if jd is None:
            raise NotFoundError("Job description not found")

        interview = Interview(
            user_id=user_id,
            resume_id=resume_id,
            jd_id=payload.jd_id,
            role=payload.role,
            level=payload.level,
            type=payload.type,
            difficulty=payload.difficulty,
            proctoring_mode=payload.proctoring_mode,
            target_questions=payload.target_questions,
        )
        interview.id = await self._interviews.insert(db, interview)
        return _interview_out(interview)

    async def list(
        self,
        db: AsyncIOMotorDatabase,
        user_id: str,
        limit: int,
        *,
        offset: int = 0,
        status: str | None = None,
        interview_type: str | None = None,
        query: str | None = None,
    ) -> InterviewListOut:
        docs, total = await self._interviews.list_for_user(
            db,
            user_id,
            limit,
            offset=offset,
            status=status,
            interview_type=interview_type,
            query=query,
        )
        items = [_summary_out(doc) for doc in docs]
        return InterviewListOut(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
            has_more=offset + len(items) < total,
        )

    async def results(
        self,
        db: AsyncIOMotorDatabase,
        user_id: str,
        sort: ResultsSort = "recent",
        limit: int = 50,
    ) -> InterviewResultsOut:
        docs, stats = await self._interviews.results_for_user(
            db, user_id, sort, limit
        )
        average = stats.get("average_score")
        best = stats.get("best_score")
        return InterviewResultsOut(
            items=[_summary_out(doc) for doc in docs],
            total=int(stats.get("total") or 0),
            scored_count=int(stats.get("scored_count") or 0),
            average_score=(
                round(float(average), 1)
                if isinstance(average, (int, float))
                else None
            ),
            best_score=round(float(best), 1) if isinstance(best, (int, float)) else None,
        )

    async def get(self, db: AsyncIOMotorDatabase, user_id: str, interview_id: str) -> InterviewOut:
        interview = await self._require(db, user_id, interview_id)
        return _interview_out(interview)

    async def delete(
        self, db: AsyncIOMotorDatabase, user_id: str, interview_id: str
    ) -> None:
        """Discard an unfinished interview and its recordings.

        Completed interviews are kept as reports/evidence. Discarding an
        abandoned `created`/`in_progress` session releases its job description
        for deletion.
        """
        interview = await self._require(db, user_id, interview_id)
        if interview.status == "completed":
            raise ConflictError(
                "Completed interviews are kept as reports and cannot be discarded."
            )
        try:
            await self._recordings.purge_interview_recordings(db, interview_id)
        except Exception:
            logger.warning("Could not remove recordings for discarded interview %s", interview_id)
        await self._interviews.delete_by_id(db, interview_id)

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

        if interview.proctoring_mode != "off":
            consent = interview.proctoring_session and interview.proctoring_session.consent_given_at
            if not consent:
                raise ConflictError("Proctoring consent must be recorded before starting.")

        first = await self._generate_question(db, interview, asked=[])
        doc = await self._interviews.start(db, interview_id, user_id, first)
        if doc is None:  # lost a concurrent start race
            raise ConflictError("Interview was already started.")

        started = Interview(**doc)
        if started.proctoring_mode != "off":
            await self.start_proctoring_session(db, user_id, interview_id)
            started = await self._require(db, user_id, interview_id)
        question = started.current_question
        assert question is not None  # start() just pushed it
        return CurrentQuestionOut(
            interview_id=started.id or "",
            status=started.status,
            question=_question_out(question),
            question_number=question.sequence,
            total_asked=len(started.questions),
        )

    async def complete(
        self, db: AsyncIOMotorDatabase, user_id: str, interview_id: str
    ) -> InterviewOut:
        """End a practice session early and generate its report from answers so far.

        Idempotent: finishing an already-completed interview returns its current
        state. At least one answer is required, otherwise there is nothing to
        evaluate and the client should discard the session instead.
        """
        interview = await self._require(db, user_id, interview_id)
        if interview.status == "completed":
            return _interview_out(interview)
        if interview.status != "in_progress":
            raise ConflictError("Interview has not been started yet.")
        if not interview.answers:
            raise ConflictError("Answer at least one question before ending the interview.")

        doc = await self._interviews.complete_early(db, interview_id, user_id)
        if doc is None:
            latest = await self._require(db, user_id, interview_id)
            if latest.status == "completed":
                return _interview_out(latest)
            raise ConflictError("Interview is no longer in progress.")

        completed = Interview(**doc)
        if completed.proctoring_mode != "off":
            try:
                await self.end_proctoring_session(db, user_id, interview_id)
            except Exception as exc:
                logger.warning(
                    "Could not end proctoring session for interview %s: %s",
                    interview_id,
                    exc,
                )
        self._spawn_evaluation_task(db, completed)
        return _interview_out(completed)

    async def transcribe(
        self,
        db: AsyncIOMotorDatabase,
        user_id: str,
        interview_id: str,
        data: bytes,
        filename: str,
        content_type: str,
    ) -> str:
        """Server-side STT for one answer (Safari/Firefox fallback path)."""
        interview = await self._require(db, user_id, interview_id)
        if interview.status != "in_progress":
            raise ConflictError("Transcription is only available during the interview.")
        return await get_transcriber().transcribe(data, filename, content_type)

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
        """Record an answer and produce the next question (no scoring yet).

        Evaluation is deferred to the end of the exam. The request path makes
        at most one LLM call (next-question generation) — zero on the final
        answer. If the next-question call fails the client gets a 503 and can
        resubmit without leaving a half-recorded answer. The interview
        completes automatically once `target_questions` answers are stored;
        a background task then evaluates all answers in parallel and caches
        the report (the report endpoint backfills if that task fails).
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

        answered = len(interview.answers) + 1
        completing = answered >= interview.target_questions
        next_question = None
        if not completing:
            next_question = await self._generate_next_question(
                db, interview, question, payload.answer
            )

        answer = Answer(
            id=uuid.uuid4().hex,
            question_id=question_id,
            text=payload.answer,
            evaluation=None,  # deferred: scored at exam end
        )
        updated_doc = await self._interviews.record_answer(
            db, interview.id or "", user_id, answer, next_question, completing
        )
        if updated_doc is None:  # concurrent/duplicate submission lost the race
            raise ConflictError("This answer was already submitted.")

        updated = Interview(**updated_doc)
        if updated.status == "completed":
            if updated.proctoring_mode != "off":
                await self.end_proctoring_session(db, user_id, interview.id or "")
            self._spawn_evaluation_task(db, updated)
        return AnswerResultOut(
            question_id=question_id,
            status=updated.status,
            evaluation=None,
            next_question=_question_out(next_question) if next_question else None,
            questions_answered=len(updated.answers),
            target_questions=updated.target_questions,
        )

    async def report(self, db: AsyncIOMotorDatabase, user_id: str, interview_id: str) -> ReportOut:
        """The cached final report, generated on first access if missing.

        Acts as the safety net for the deferred-evaluation pipeline: if any
        answer is still unevaluated (background task failed or still running),
        backfill the missing evaluations behind a per-interview lock, then
        generate and cache the report.
        """
        interview = await self._require(db, user_id, interview_id)
        if interview.status != "completed":
            raise ConflictError("The report is available once the interview is completed.")
        if interview.report is not None and not _has_pending_evaluations(interview):
            return _report_out(interview)

        async with _report_lock(interview_id):
            # Re-read inside the lock: a concurrent request (or the background
            # task) may have finished the work while we waited.
            interview = await self._require(db, user_id, interview_id)
            if interview.report is not None and not _has_pending_evaluations(interview):
                return _report_out(interview)

            failures = await self._ensure_evaluations(db, interview)
            refreshed = await self._require(db, user_id, interview_id)
            if _has_pending_evaluations(refreshed):
                if refreshed.report is not None:
                    # Legacy partial report: keep it readable rather than
                    # blocking the candidate behind a permanently failing eval.
                    logger.warning(
                        "Returning cached report for %s with %s unevaluated answer(s)",
                        interview_id,
                        failures,
                    )
                    return _report_out(refreshed)
                raise ServiceUnavailableError(
                    "Some answers could not be evaluated yet. Please try again."
                )

            report = await self._generate_report(refreshed)
            doc = await self._interviews.set_report(
                db,
                interview.id or "",
                user_id,
                report,
                replace=refreshed.report is not None,
            )
            if doc is None:
                # A concurrent request cached a report first — use that one.
                latest = await self._require(db, user_id, interview_id)
                if latest.report is None:
                    raise ConflictError("Interview is no longer completed.")
                return _report_out(latest)
            return _report_out(Interview(**doc))

    async def ensure_evaluations(
        self, db: AsyncIOMotorDatabase, interview_id: str, user_id: str
    ) -> None:
        """Evaluate any answers still pending scoring (idempotent, self-healing).

        The screening scorecard calls this so a reviewer opening it never
        depends on the completion-time background task having finished.
        """
        async with _report_lock(interview_id):
            doc = await self._interviews.find_owned(db, interview_id, user_id)
            if doc is None:
                return
            await self._ensure_evaluations(db, Interview(**doc))

    def _spawn_evaluation_task(
        self, db: AsyncIOMotorDatabase, interview: Interview
    ) -> None:
        """Fire-and-forget: evaluate all answers, then cache the report.

        Runs after the completion response is sent so the request path stays
        fast. A failure here is logged only — `GET /report` backfills later.
        """
        task = asyncio.create_task(
            self._finalize_interview(db, interview.id or "", interview.user_id)
        )
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    async def _finalize_interview(
        self, db: AsyncIOMotorDatabase, interview_id: str, user_id: str
    ) -> None:
        """Background pipeline: evaluate all answers, then cache the report."""
        try:
            async with _report_lock(interview_id):
                doc = await self._interviews.find_owned(db, interview_id, user_id)
                if doc is None:
                    return
                interview = Interview(**doc)
                if interview.report is not None and not _has_pending_evaluations(interview):
                    return
                failures = await self._ensure_evaluations(db, interview)
                if failures:
                    logger.warning(
                        "Skipping report for interview %s: %s answer evaluation(s) failed",
                        interview_id,
                        failures,
                    )
                    return
                refreshed_doc = await self._interviews.find_owned(db, interview_id, user_id)
                if refreshed_doc is None:
                    return
                refreshed = Interview(**refreshed_doc)
                if _has_pending_evaluations(refreshed):
                    logger.warning(
                        "Skipping report for interview %s: evaluations still pending",
                        interview_id,
                    )
                    return
                report = await self._generate_report(refreshed)
                await self._interviews.set_report(
                    db,
                    interview_id,
                    user_id,
                    report,
                    replace=refreshed.report is not None,
                )
        except Exception as exc:
            logger.warning(
                "Background evaluation/report for interview %s failed: %s: %s",
                interview_id,
                type(exc).__name__,
                exc,
            )

    async def _ensure_evaluations(
        self, db: AsyncIOMotorDatabase, interview: Interview
    ) -> int:
        """Evaluate every answer that is still unevaluated.

        Runs in parallel under a bounded semaphore and persists each
        evaluation incrementally the moment it finishes — a crash mid-run
        keeps the completed work. Answers already evaluated are skipped, so
        this is safe to call multiple times. Returns the number of answers
        that could not be evaluated.
        """
        question_map = {question.id: question for question in interview.questions}
        pending = [a for a in interview.answers if a.evaluation is None]
        if not pending:
            return 0

        async def _eval_one(answer: Answer) -> None:
            question = question_map.get(answer.question_id)
            if question is None:
                raise ValueError(f"Question {answer.question_id} is missing")
            async with _eval_semaphore:
                evaluation = await self._evaluate(interview, question, answer.text)
            await self._interviews.set_answer_evaluation(
                db, interview.id or "", interview.user_id, answer.id, evaluation
            )

        results = await asyncio.gather(
            *(_eval_one(answer) for answer in pending), return_exceptions=True
        )
        failures = 0
        for answer, result in zip(pending, results, strict=False):
            if isinstance(result, Exception):
                failures += 1
                logger.error(
                    "Evaluation failed for answer %s: %s: %s",
                    answer.id,
                    type(result).__name__,
                    result,
                )
        return failures

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
            prompt="",
            question=question.text,
            answer=answer_text,
            rubric=_rubric_block(interview),
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
            competency=result.competency.strip(),
            evidence=[quote.strip() for quote in result.evidence if quote.strip()][
                :MAX_EVIDENCE_QUOTES
            ],
        )

    async def _generate_next_question(
        self,
        db: AsyncIOMotorDatabase,
        interview: Interview,
        previous: Question,
        answer_text: str,
    ) -> Question:
        resume_context, jd_context = await self._load_context(db, interview)
        prompt = GENERATE_NEXT_QUESTION_EVALFREE_PROMPT.format(
            type=interview.type.replace("_", " "),
            role=interview.role,
            level=interview.level,
            difficulty=interview.difficulty,
            resume_context=resume_context,
            jd_context=jd_context,
            knowledge=await self._knowledge_block(interview, previous.topic),
            previous_question=previous.text,
            candidate_answer=answer_text,
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
            knowledge=await self._knowledge_block(interview, topic=""),
            asked="\n".join(f"- {text}" for text in asked) or "(none yet)",
        )
        return await self._ask_for_question(interview, prompt)

    async def _knowledge_block(self, interview: Interview, topic: str) -> str:
        """Retrieved knowledge chunks for a question prompt.

        RAG must never break question generation: a disabled flag, an empty
        store, or an unreachable Qdrant all degrade to a placeholder block.
        """
        if not rag_service.enabled:
            return "(knowledge base disabled)"
        try:
            chunks = await rag_service.retrieve_context(
                role=interview.role,
                topic=topic,
                interview_type=interview.type,
            )
        except Exception as exc:
            logger.warning(
                "RAG retrieval failed, continuing without knowledge: %s: %s",
                type(exc).__name__,
                exc,
            )
            return "(knowledge base unavailable)"
        if not chunks:
            return "(no matching knowledge found)"
        return "\n".join(f"- [{chunk.topic}] {chunk.text[:600]}" for chunk in chunks)

    async def _load_context(
        self, db: AsyncIOMotorDatabase, interview: Interview
    ) -> tuple[str, str]:
        # The resume is optional (and may have been deleted) — the JD is not.
        resume = None
        if interview.resume_id:
            resume = await self._resumes.find_owned(db, interview.resume_id, interview.user_id)
        jd = await self._job_descriptions.find_owned(db, interview.jd_id, interview.user_id)
        if jd is None:
            raise NotFoundError("Job description no longer exists")

        resume_context = "{}"
        if resume:
            structured = resume.get("structured_data") or {}
            status = (resume.get("analysis") or {}).get("status")
            raw_text = str(resume.get("raw_text") or "")
            if structured and status not in {"failed"}:
                resume_context = _context_block(structured)
            elif raw_text:
                resume_context = _context_block({"resume_text": raw_text})
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

    async def record_proctoring_consent(
        self, db: AsyncIOMotorDatabase, user_id: str, interview_id: str, consent: bool
    ) -> None:
        interview = await self._require(db, user_id, interview_id)
        if interview.status != "created":
            raise ConflictError("Can only record consent before the interview starts.")

        if not consent:
            raise ConflictError("Proctoring consent is required to continue.")

        now = datetime.now(UTC)
        if interview.proctoring_session is None:
            interview.proctoring_session = ProctoringSession(consent_given_at=now)
        else:
            interview.proctoring_session.consent_given_at = now

        await self._interviews.update_proctoring_session(
            db, interview_id, user_id, interview.proctoring_session.model_dump()
        )

    async def record_proctoring_event(
        self, db: AsyncIOMotorDatabase, user_id: str, interview_id: str,
        event_type: str, details: dict,
    ) -> None:
        """Append one proctoring event (e.g. camera_off, tab_blur).

        Events are only meaningful once the interview is in progress; they are
        appended race-safely via `$push` so concurrent track toggles cannot
        clobber each other.
        """
        interview = await self._require(db, user_id, interview_id)
        if interview.status not in ("in_progress", "completed"):
            raise ConflictError("Proctoring events are only recorded during the interview.")
        event = ProctoringEvent(type=event_type, details=details)
        pushed = await self._interviews.push_proctoring_event(
            db, interview_id, user_id, event.model_dump()
        )
        if not pushed:
            raise NotFoundError("Interview not found")

    async def start_proctoring_session(
        self, db: AsyncIOMotorDatabase, user_id: str, interview_id: str
    ) -> None:
        """Mark the proctoring session active (called when the interview starts).

        No-op for ``proctoring_mode == "off"``. Practice sessions are strict,
        so they record consent before this runs.
        """
        interview = await self._require(db, user_id, interview_id)
        if interview.proctoring_mode == "off":
            return
        session = interview.proctoring_session or ProctoringSession()
        session.started_at = datetime.now(UTC)
        session.status = "active"
        await self._interviews.update_proctoring_session(
            db, interview_id, user_id, session.model_dump()
        )

    async def end_proctoring_session(
        self, db: AsyncIOMotorDatabase, user_id: str, interview_id: str
    ) -> None:
        """Seal the proctoring session (called when the interview completes)."""
        interview = await self._require(db, user_id, interview_id)
        if interview.proctoring_mode == "off" or interview.proctoring_session is None:
            return
        session = interview.proctoring_session
        session.ended_at = datetime.now(UTC)
        session.status = "completed"
        await self._interviews.update_proctoring_session(
            db, interview_id, user_id, session.model_dump()
        )
