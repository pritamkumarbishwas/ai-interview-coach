"""Background-job handler registration.

Handlers are idempotent and safe to register more than once (the tests register
them on their own worker). ``register_default_handlers`` wires the production
handlers onto the shared worker; the lifespan calls it at startup so an
``ats.webhook`` job is delivered by whichever process runs the worker.
"""

import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.crypto import field_cipher
from app.core.jobs import JobWorker, job_worker
from app.core.webhooks import ATS_WEBHOOK_JOB, WebhookDelivery, webhook_sender
from app.integrations import ats
from app.models.interview import Interview
from app.models.invitation import ScreeningInvitation
from app.models.job import Job
from app.repositories.interview_repository import interview_repository
from app.repositories.invitation_repository import invitation_repository
from app.repositories.job_repository import job_repository
from app.services.resume_processing import (
    RESUME_PROCESS_JOB,
    resume_processing_service,
)
from app.services.retention_service import RETENTION_PURGE_JOB, retention_service
from app.services.scorecard_service import scorecard_service

logger = logging.getLogger(__name__)


def _assessment(interview_doc: dict | None) -> tuple[float | None, bool | None]:
    """Advisory score from stored evaluations only (never calls the LLM)."""
    if not interview_doc:
        return None, None
    interview = Interview(**interview_doc)
    if not interview.answers:
        return None, None
    card = scorecard_service.build(interview)
    return card.overall_score, card.meets_threshold


async def deliver_ats_webhook(db: AsyncIOMotorDatabase, payload: dict) -> None:
    """Deliver one queued ``candidate.decided`` webhook for a job.

    A missing job/invitation or a disabled webhook is a no-op (the recruiter may
    have deleted or reconfigured the integration between enqueue and delivery).
    Any transport/HTTP failure propagates so the queue retries with backoff.
    """
    job_doc = await job_repository.get_by_id(db, payload.get("job_id", ""))
    if job_doc is None:
        return
    job = Job(**job_doc)
    if not job.webhook_enabled or not job.webhook_url:
        return

    invitation_doc = await invitation_repository.get_by_id(
        db, payload.get("invitation_id", "")
    )
    if invitation_doc is None:
        return
    invitation = ScreeningInvitation(**invitation_doc)

    interview_doc = None
    if invitation.interview_id:
        interview_doc = await interview_repository.get_by_id(db, invitation.interview_id)
    overall_score, meets_threshold = _assessment(interview_doc)

    body = ats.build_payload(
        job.webhook_provider,
        job,
        invitation,
        overall_score=overall_score,
        meets_threshold=meets_threshold,
    )
    status = await webhook_sender.send(
        WebhookDelivery(
            url=job.webhook_url,
            event=ats.CANDIDATE_DECIDED,
            payload=body,
            secret=field_cipher.decrypt(job.webhook_secret),
        )
    )
    logger.info(
        "Delivered ATS webhook job=%s invitation=%s status=%s",
        job.id,
        invitation.id,
        status,
    )


async def run_retention_purge(db: AsyncIOMotorDatabase, payload: dict) -> None:
    """Erase candidate session data past the retention window."""
    await retention_service.purge_expired(db)


async def process_resume_assets(db: AsyncIOMotorDatabase, payload: dict) -> None:
    """Extract full content, previews, OCR and structured data for a resume."""
    resume_id = str(payload.get("resume_id") or "")
    user_id = str(payload.get("user_id") or "")
    if resume_id and user_id:
        await resume_processing_service.process(db, resume_id, user_id)


def register_default_handlers(worker: JobWorker | None = None) -> None:
    target = worker or job_worker
    target.register(ATS_WEBHOOK_JOB, deliver_ats_webhook)
    target.register(RETENTION_PURGE_JOB, run_retention_purge)
    target.register(RESUME_PROCESS_JOB, process_resume_assets)
