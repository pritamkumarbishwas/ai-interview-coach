"""Job-requisition use-cases: CRUD and template attachment."""

import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.crypto import field_cipher
from app.core.exceptions import InvalidInputError, NotFoundError
from app.models.job import Job
from app.models.user import User
from app.repositories.job_repository import JobRepository
from app.repositories.template_repository import TemplateRepository
from app.repositories.user_repository import UserRepository
from app.schemas.job import JobCreate, JobOut, JobSummary, JobUpdate
from app.services.audit_service import audit_service
from app.services.job_access import find_accessible_job, find_manageable_job

logger = logging.getLogger(__name__)

# Fields whose values are trimmed before they are stored.
_STRIPPED_FIELDS = ("title", "company", "location")


class JobService:
    def __init__(
        self,
        jobs: JobRepository,
        templates: TemplateRepository,
        users: UserRepository,
    ) -> None:
        self._jobs = jobs
        self._templates = templates
        self._users = users

    async def create(
        self, db: AsyncIOMotorDatabase, actor: User, payload: JobCreate
    ) -> JobOut:
        if payload.template_id is not None:
            await self._require_template(db, actor, payload.template_id)

        job = Job(
            user_id=actor.id or "",
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
        self, db: AsyncIOMotorDatabase, actor: User, limit: int
    ) -> list[JobSummary]:
        if actor.role == "admin":
            docs = await self._jobs.list_all(db, limit)
        elif actor.role == "reviewer":
            docs = await self._jobs.list_for_reviewer(db, actor.id or "", limit)
        else:
            docs = await self._jobs.list_for_user(db, actor.id or "", limit)
        return [
            JobSummary(
                id=doc["_id"],
                title=doc.get("title", ""),
                company=doc.get("company", ""),
                status=doc.get("status", "draft"),
                template_id=doc.get("template_id"),
                reviewer_ids=doc.get("reviewer_ids", []),
                owner_id=doc.get("user_id"),
                created_at=doc["created_at"],
            )
            for doc in docs
        ]

    async def get(self, db: AsyncIOMotorDatabase, actor: User, job_id: str) -> JobOut:
        doc = await self._require_accessible(db, actor, job_id)
        return self._to_out(Job(**doc))

    async def update(
        self, db: AsyncIOMotorDatabase, actor: User, job_id: str, payload: JobUpdate
    ) -> JobOut:
        current = await self._require_manageable(db, actor, job_id)
        fields = self._update_fields(payload)
        if "template_id" in fields and fields["template_id"] is not None:
            await self._require_template(db, actor, fields["template_id"])
        # A webhook cannot be enabled without somewhere to send it.
        enabled = fields.get("webhook_enabled", current.get("webhook_enabled", False))
        url = fields.get("webhook_url", current.get("webhook_url", ""))
        if enabled and not url:
            raise InvalidInputError("A webhook URL is required before enabling the integration.")
        if not fields:
            return self._to_out(Job(**current))

        if actor.role == "admin" and current.get("user_id") != actor.id:
            doc = await self._jobs.update_any(db, job_id, fields)
            await self._audit_admin(db, actor, job_id, "job.updated")
        else:
            doc = await self._jobs.update(db, job_id, actor.id or "", fields)
        if doc is None:  # pragma: no cover - the row existed a moment ago
            raise NotFoundError("Job not found")
        return self._to_out(Job(**doc))

    async def delete(self, db: AsyncIOMotorDatabase, actor: User, job_id: str) -> None:
        current = await self._require_manageable(db, actor, job_id)
        if actor.role == "admin" and current.get("user_id") != actor.id:
            await self._jobs.delete_any(db, job_id)
            await self._audit_admin(db, actor, job_id, "job.deleted")
        else:
            await self._jobs.delete(db, job_id, actor.id or "")

    async def set_reviewers(
        self,
        db: AsyncIOMotorDatabase,
        actor: User,
        job_id: str,
        reviewer_ids: list[str],
    ) -> JobOut:
        """Replace the reviewer assignment list (owner/admin only)."""
        current = await self._require_manageable(db, actor, job_id)
        unique = list(dict.fromkeys(reviewer_ids))
        for reviewer_id in unique:
            user = await self._users.get_by_id(db, reviewer_id)
            if user is None or user.role != "reviewer":
                raise InvalidInputError(
                    "reviewer_ids must reference existing reviewer accounts"
                )
        doc = await self._jobs.set_reviewers(db, job_id, unique)
        if doc is None:  # pragma: no cover - the row existed a moment ago
            raise NotFoundError("Job not found")
        metadata: dict = {"reviewer_ids": unique}
        if actor.role == "admin" and current.get("user_id") != actor.id:
            metadata["cross_owner"] = True
        await audit_service.record(
            db,
            action="job.reviewers_changed",
            actor_id=actor.id,
            target_type="job",
            target_id=job_id,
            metadata=metadata,
        )
        return self._to_out(Job(**doc))

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
            reviewer_ids=job.reviewer_ids,
            owner_id=job.user_id,
            webhook_url=job.webhook_url,
            webhook_provider=job.webhook_provider,
            webhook_enabled=job.webhook_enabled,
            webhook_configured=bool(job.webhook_secret),
            created_at=job.created_at,
            updated_at=job.updated_at,
        )

    async def _require_accessible(
        self, db: AsyncIOMotorDatabase, actor: User, job_id: str
    ) -> dict:
        doc = await find_accessible_job(db, self._jobs, job_id, actor)
        if doc is None:
            raise NotFoundError("Job not found")
        return doc

    async def _require_manageable(
        self, db: AsyncIOMotorDatabase, actor: User, job_id: str
    ) -> dict:
        doc = await find_manageable_job(db, self._jobs, job_id, actor)
        if doc is None:
            raise NotFoundError("Job not found")
        return doc

    async def _require_template(
        self, db: AsyncIOMotorDatabase, actor: User, template_id: str
    ) -> None:
        doc = await self._templates.find_owned(db, template_id, actor.id or "")
        if doc is None and actor.role == "admin":
            doc = await self._templates.get_by_id(db, template_id)
        if doc is None:
            raise NotFoundError("Interview template not found")

    async def _audit_admin(
        self, db: AsyncIOMotorDatabase, actor: User, job_id: str, action: str
    ) -> None:
        await audit_service.record(
            db,
            action=action,
            actor_id=actor.id,
            target_type="job",
            target_id=job_id,
            metadata={"cross_owner": True},
        )
