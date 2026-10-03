"""Job-description use-cases: AI enrichment and persistence."""

import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.exceptions import NotFoundError
from app.models.job_description import JobDescription
from app.prompts.templates import EXTRACT_JD_INFO_PROMPT, MAX_PROMPT_CHARS
from app.repositories.job_description_repository import JobDescriptionRepository
from app.schemas.job_description import (
    JobDescriptionInput,
    JobDescriptionResponse,
    JobDescriptionStructuredData,
    JobDescriptionSummary,
)
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)

SNIPPET_LENGTH = 180


def _snippet(text: str, length: int = SNIPPET_LENGTH) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= length else compact[: length - 3].rstrip() + "..."


def _stored_snippet(doc: dict) -> str:
    snippet = doc.get("snippet")
    if snippet:
        return snippet
    # Documents saved before the `snippet` field existed: rebuild one from
    # the stored structure.
    responsibilities = (doc.get("structured_data") or {}).get("responsibilities")
    if not isinstance(responsibilities, list):
        return ""
    return _snippet(", ".join(str(item) for item in responsibilities))


class JobDescriptionService:
    def __init__(self, job_descriptions: JobDescriptionRepository) -> None:
        self._job_descriptions = job_descriptions

    async def create(
        self, db: AsyncIOMotorDatabase, user_id: str, payload: JobDescriptionInput
    ) -> JobDescriptionResponse:
        structured_data = await self._extract_structured_data(payload)

        jd = JobDescription(
            user_id=user_id,
            title=payload.title.strip(),
            company=payload.company.strip(),
            raw_text=payload.raw_text,
            snippet=_snippet(payload.raw_text),
            structured_data=structured_data.model_dump(),
        )
        jd.id = await self._job_descriptions.insert(db, jd)

        return JobDescriptionResponse(
            id=jd.id,
            title=jd.title,
            company=jd.company,
            structured_data=structured_data,
        )

    async def list(
        self, db: AsyncIOMotorDatabase, user_id: str, limit: int
    ) -> list[JobDescriptionSummary]:
        docs = await self._job_descriptions.list_for_user(db, user_id, limit)
        return [
            JobDescriptionSummary(
                id=doc["_id"],
                title=doc.get("title", ""),
                company=doc.get("company", ""),
                snippet=_stored_snippet(doc),
                created_at=doc["created_at"],
            )
            for doc in docs
        ]

    async def get(self, db: AsyncIOMotorDatabase, user_id: str, jd_id: str) -> JobDescription:
        doc = await self._require(db, user_id, jd_id)
        return JobDescription(**doc)

    async def delete(self, db: AsyncIOMotorDatabase, user_id: str, jd_id: str) -> None:
        await self._require(db, user_id, jd_id)
        await self._job_descriptions.delete(db, jd_id, user_id)

    async def _extract_structured_data(
        self, payload: JobDescriptionInput
    ) -> JobDescriptionStructuredData:
        """Enrich a posting with the LLM, but never fail the save because of it."""
        prompt = EXTRACT_JD_INFO_PROMPT.format(text=payload.raw_text[:MAX_PROMPT_CHARS])
        try:
            return await llm_service.generate_structured(
                prompt, JobDescriptionStructuredData, max_retries=2
            )
        except Exception as exc:
            logger.warning(
                "JD extraction unavailable (%s: %s); storing the posting unstructured",
                type(exc).__name__,
                exc,
            )
            return JobDescriptionStructuredData(
                role_title=payload.title,
                required_skills=[],
                responsibilities=[],
            )

    async def _require(self, db: AsyncIOMotorDatabase, user_id: str, jd_id: str) -> dict:
        doc = await self._job_descriptions.find_owned(db, jd_id, user_id)
        if doc is None:
            raise NotFoundError("Job description not found")
        return doc
