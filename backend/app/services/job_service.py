"""Job-requisition use-cases: CRUD and template attachment."""

import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.crypto import field_cipher
from app.core.exceptions import InvalidInputError, NotFoundError
from app.models.job import Job
from app.repositories.job_repository import JobRepository
from app.repositories.template_repository import TemplateRepository
from app.schemas.job import JobCreate, JobOut, JobSummary, JobUpdate

logger = logging.getLogger(__name__)

# Fields whose values are trimmed before they are stored.
_STRIPPED_FIELDS = ("title", "company", "location")


class JobService:
    def __init__(self, jobs: JobRepository, templates: TemplateRepository) -> None:
        self._jobs = jobs
        self._templates = templates

    async def create(
        self, db: AsyncIOMotorDatabase, user_id: str, payload: JobCreate
    ) -> JobOut:
        if payload.template_id is not None:
            await self._require_template(db, user_id, payload.template_id)

        job = Job(
            user_id=user_id,
            title=payload.title.strip(),
            company=payload.company.strip(),
            location=payload.location.strip(),
            description=payload.description,
            status=payload.status,
            template_id=payload.template_id,
        )
        job.id = await self._jobs.insert(db, job)
        return self._to_out(job)

    async def list(
        self, db: AsyncIOMotorDatabase, user_id: str, limit: int
    ) -> list[JobSummary]:
        docs = await self._jobs.list_for_user(db, user_id, limit)
        return [
            JobSummary(
                id=doc["_id"],
                title=doc.get("title", ""),
                company=doc.get("company", ""),
                status=doc.get("status", "draft"),
                template_id=doc.get("template_id"),
                created_at=doc["created_at"],
            )
            for doc in docs
        ]

    async def get(self, db: AsyncIOMotorDatabase, user_id: str, job_id: str) -> JobOut:
        return self._to_out(Job(**await self._require(db, user_id, job_id)))

    async def update(
        self, db: AsyncIOMotorDatabase, user_id: str, job_id: str, payload: JobUpdate
    ) -> JobOut:
        current = await self._require(db, user_id, job_id)
        fields = self._update_fields(payload)
        if "template_id" in fields and fields["template_id"] is not None:
            await self._require_template(db, user_id, fields["template_id"])
        # A webhook cannot be enabled without somewhere to send it.
        enabled = fields.get("webhook_enabled", current.get("webhook_enabled", False))
        url = fields.get("webhook_url", current.get("webhook_url", ""))
        if enabled and not url:
            raise InvalidInputError("A webhook URL is required before enabling the integration.")
        if not fields:
            return self._to_out(Job(**current))

        doc = await self._jobs.update(db, job_id, user_id, fields)
        if doc is None:  # pragma: no cover - the row existed a moment ago
            raise NotFoundError("Job not found")
        return self._to_out(Job(**doc))

    async def delete(self, db: AsyncIOMotorDatabase, user_id: str, job_id: str) -> None:
        await self._require(db, user_id, job_id)
        await self._jobs.delete(db, job_id, user_id)

    @staticmethod
    def _update_fields(payload: JobUpdate) -> dict:
        raw = payload.model_dump(exclude_unset=True)
        fields: dict = {}
        for key in _STRIPPED_FIELDS:
            if raw.get(key) is not None:
                fields[key] = raw[key].strip()
        if raw.get("description") is not None:
            fields["description"] = raw["description"]
        if raw.get("status") is not None:
            fields["status"] = raw["status"]
        # An explicit `null` detaches the template (validated by the caller).
        if "template_id" in raw:
            fields["template_id"] = raw["template_id"]
        if raw.get("webhook_url") is not None:
            fields["webhook_url"] = raw["webhook_url"].strip()
        if raw.get("webhook_provider") is not None:
            fields["webhook_provider"] = raw["webhook_provider"]
        # An empty string clears the secret; `None`/omitted leaves it unchanged.
        if raw.get("webhook_secret") is not None:
            # The signing secret is encrypted at rest (Phase 9).
            fields["webhook_secret"] = field_cipher.encrypt(raw["webhook_secret"])
        if raw.get("webhook_enabled") is not None:
            fields["webhook_enabled"] = raw["webhook_enabled"]
        return fields

    @staticmethod
    def _to_out(job: Job) -> JobOut:
        return JobOut(
            id=job.id or "",
            title=job.title,
            company=job.company,
            location=job.location,
            description=job.description,
            status=job.status,
            template_id=job.template_id,
            webhook_url=job.webhook_url,
            webhook_provider=job.webhook_provider,
            webhook_enabled=job.webhook_enabled,
            webhook_configured=bool(job.webhook_secret),
            created_at=job.created_at,
            updated_at=job.updated_at,
        )

    async def _require(self, db: AsyncIOMotorDatabase, user_id: str, job_id: str) -> dict:
        doc = await self._jobs.find_owned(db, job_id, user_id)
        if doc is None:
            raise NotFoundError("Job not found")
        return doc

    async def _require_template(
        self, db: AsyncIOMotorDatabase, user_id: str, template_id: str
    ) -> None:
        doc = await self._templates.find_owned(db, template_id, user_id)
        if doc is None:
            raise NotFoundError("Interview template not found")
