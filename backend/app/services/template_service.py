"""Interview-template use-cases: CRUD, question bank, and question preview."""

import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.exceptions import ConflictError, NotFoundError, ServiceUnavailableError
from app.models.template import BankQuestion, InterviewTemplate
from app.models.template_config import RoundConfig
from app.prompts.templates import GENERATE_QUESTION_PROMPT
from app.repositories.job_repository import JobRepository
from app.repositories.template_repository import TemplateRepository
from app.schemas.interview import QuestionGeneration
from app.schemas.template import (
    BankQuestionInput,
    BankQuestionOut,
    TemplateCreate,
    TemplateOut,
    TemplatePreviewOut,
    TemplatePreviewRequest,
    TemplateSummary,
    TemplateUpdate,
)
from app.services.llm_service import llm_service
from app.services.rag_service import rag_service

logger = logging.getLogger(__name__)

# A preview is generation-only (no candidate context), so it is always framed
# as a mid-level practice question.
PREVIEW_LEVEL = "mid"


class TemplateService:
    def __init__(self, templates: TemplateRepository, jobs: JobRepository) -> None:
        self._templates = templates
        self._jobs = jobs

    async def create(
        self, db: AsyncIOMotorDatabase, user_id: str, payload: TemplateCreate
    ) -> TemplateOut:
        template = InterviewTemplate(
            user_id=user_id,
            name=payload.name.strip(),
            description=payload.description,
            config=payload.config,
            question_bank=[self._to_bank_question(q) for q in payload.question_bank],
        )
        template.id = await self._templates.insert(db, template)
        return self._to_out(template)

    async def list(
        self, db: AsyncIOMotorDatabase, user_id: str, limit: int
    ) -> list[TemplateSummary]:
        docs = await self._templates.list_for_user(db, user_id, limit)
        return [
            TemplateSummary(
                id=doc["_id"],
                name=doc.get("name", ""),
                description=doc.get("description", ""),
                proctoring_mode=doc.get("proctoring_mode", "strict"),
                round_count=doc.get("round_count", 0),
                question_count=doc.get("question_count", 0),
                created_at=doc["created_at"],
            )
            for doc in docs
        ]

    async def get(self, db: AsyncIOMotorDatabase, user_id: str, template_id: str) -> TemplateOut:
        return self._to_out(InterviewTemplate(**await self._require(db, user_id, template_id)))

    async def update(
        self,
        db: AsyncIOMotorDatabase,
        user_id: str,
        template_id: str,
        payload: TemplateUpdate,
    ) -> TemplateOut:
        await self._require(db, user_id, template_id)
        fields = self._update_fields(payload)
        if not fields:
            return self._to_out(
                InterviewTemplate(**await self._require(db, user_id, template_id))
            )

        doc = await self._templates.update(db, template_id, user_id, fields)
        if doc is None:  # pragma: no cover - the row existed a moment ago
            raise NotFoundError("Interview template not found")
        return self._to_out(InterviewTemplate(**doc))

    async def delete(self, db: AsyncIOMotorDatabase, user_id: str, template_id: str) -> None:
        await self._require(db, user_id, template_id)
        # Keep requisitions from pointing at a template that no longer exists.
        if await self._jobs.count_for_template(db, user_id, template_id):
            raise ConflictError("Template is attached to one or more jobs")
        await self._templates.delete(db, template_id, user_id)

    async def preview_question(
        self,
        db: AsyncIOMotorDatabase,
        user_id: str,
        template_id: str,
        payload: TemplatePreviewRequest,
    ) -> TemplatePreviewOut:
        """Generate one question from the template, for the builder's preview pane."""
        template = InterviewTemplate(**await self._require(db, user_id, template_id))
        round_ = self._select_round(template, payload.round_key)

        interview_type = (
            payload.interview_type or (round_.interview_type if round_ else None) or "technical"
        )
        difficulty = payload.difficulty or (round_.difficulty if round_ else None) or "intermediate"
        role = payload.role.strip() or template.name

        prompt = GENERATE_QUESTION_PROMPT.format(
            type=interview_type.replace("_", " "),
            role=role,
            level=PREVIEW_LEVEL,
            difficulty=difficulty,
            resume_context="(none)",
            jd_context="(none)",
            knowledge=await self._knowledge_block(role, payload.topic, interview_type),
            asked="(none yet)",
        )
        try:
            result = await llm_service.generate_structured(
                prompt, QuestionGeneration, max_retries=2
            )
        except Exception as exc:
            logger.warning(
                "Question preview failed (%s: %s)", type(exc).__name__, exc
            )
            raise ServiceUnavailableError(
                "Question preview is unavailable right now. Please try again later."
            ) from exc

        return TemplatePreviewOut(
            question=result.question,
            topic=result.topic or payload.topic,
            interview_type=interview_type,
            difficulty=difficulty,
        )

    @staticmethod
    def _select_round(
        template: InterviewTemplate, round_key: str | None
    ) -> RoundConfig | None:
        if not template.config.rounds:
            return None
        if round_key is None:
            return template.config.rounds[0]
        for round_ in template.config.rounds:
            if round_.key == round_key:
                return round_
        raise NotFoundError(f"Round {round_key!r} is not part of this template")

    async def _knowledge_block(self, role: str, topic: str, interview_type: str) -> str:
        """Retrieved knowledge chunks, degrading to a placeholder on any failure."""
        if not rag_service.enabled:
            return "(knowledge base disabled)"
        try:
            chunks = await rag_service.retrieve_context(
                role=role, topic=topic, interview_type=interview_type
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

    @staticmethod
    def _to_bank_question(question: BankQuestionInput) -> BankQuestion:
        return BankQuestion(**question.model_dump())

    @staticmethod
    def _update_fields(payload: TemplateUpdate) -> dict:
        raw = payload.model_dump(exclude_unset=True)
        fields: dict = {}
        if raw.get("name") is not None:
            fields["name"] = raw["name"].strip()
        if raw.get("description") is not None:
            fields["description"] = raw["description"]
        if raw.get("config") is not None:
            # Re-dump through the model so the stored config is always plain data.
            fields["config"] = payload.config.model_dump() if payload.config else None
        # Present-but-null clears the bank; a list replaces it wholesale.
        if "question_bank" in raw:
            fields["question_bank"] = [
                TemplateService._to_bank_question(q).model_dump()
                for q in (payload.question_bank or [])
            ]
        return fields

    @staticmethod
    def _to_out(template: InterviewTemplate) -> TemplateOut:
        return TemplateOut(
            id=template.id or "",
            name=template.name,
            description=template.description,
            config=template.config,
            question_bank=[BankQuestionOut(**q.model_dump()) for q in template.question_bank],
            created_at=template.created_at,
            updated_at=template.updated_at,
        )

    async def _require(
        self, db: AsyncIOMotorDatabase, user_id: str, template_id: str
    ) -> dict:
        doc = await self._templates.find_owned(db, template_id, user_id)
        if doc is None:
            raise NotFoundError("Interview template not found")
        return doc
