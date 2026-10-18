"""Data-retention and right-to-erasure (Phase 9).

Two entry points, both of which destroy the personal data (interview document —
answers, evaluations, proctoring — and its GridFS recording) and *anonymize* the
invitation record rather than deleting it, so aggregate analytics and audit
trails survive:

- ``erase_candidate``: an explicit, recruiter-triggered erasure.
- ``purge_expired``: a batch erasure of sessions past the retention window,
  run from the ``retention.purge`` background job or an admin endpoint.
"""

import logging
import secrets
from datetime import UTC, datetime, timedelta

from fastapi.encoders import jsonable_encoder
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.models.invitation import ScreeningInvitation
from app.models.user import User
from app.repositories.interview_repository import InterviewRepository, interview_repository
from app.repositories.invitation_repository import InvitationRepository, invitation_repository
from app.repositories.job_description_repository import (
    JobDescriptionRepository,
    job_description_repository,
)
from app.repositories.job_repository import JobRepository, job_repository
from app.schemas.retention import ErasureResult
from app.services.audit_service import audit_service
from app.services.job_access import find_accessible_job
from app.services.recording_service import RecordingService, recording_service

logger = logging.getLogger(__name__)

# Background-queue job type that runs the retention purge.
RETENTION_PURGE_JOB = "retention.purge"

ERASED_NAME = "[erased]"
ERASED_EMAIL_DOMAIN = "erased.invalid"


class RetentionService:
    def __init__(
        self,
        invitations: InvitationRepository,
        interviews: InterviewRepository,
        recordings: RecordingService,
        job_descriptions: JobDescriptionRepository,
        jobs: JobRepository,
    ) -> None:
        self._invitations = invitations
        self._interviews = interviews
        self._recordings = recordings
        self._job_descriptions = job_descriptions
        self._jobs = jobs

    async def _require_job_access(
        self, db: AsyncIOMotorDatabase, actor: User, doc: dict
    ) -> None:
        """Gate an invitation's PII on access to its requisition (see access rules)."""
        job = await find_accessible_job(db, self._jobs, doc.get("job_id", ""), actor)
        if job is None:
            raise NotFoundError("Invitation not found")

    async def erase_candidate(
        self, db: AsyncIOMotorDatabase, recruiter: User, invitation_id: str
    ) -> ErasureResult:
        """Recruiter-triggered erasure of one candidate's session data."""
        doc = await self._invitations.get_by_id(db, invitation_id)
        if doc is None:
            raise NotFoundError("Invitation not found")
        await self._require_job_access(db, recruiter, doc)
        result = await self.erase_invitation_data(db, doc)
        await audit_service.record(
            db,
            action="candidate.erased",
            actor_id=recruiter.id,
            target_type="screening_invitation",
            target_id=invitation_id,
            metadata={
                "interview_deleted": result.interview_deleted,
                "recording_chunks_deleted": result.recording_chunks_deleted,
            },
        )
        return result

    async def erase_invitation_data(
        self, db: AsyncIOMotorDatabase, doc: dict
    ) -> ErasureResult:
        """Destroy the session data behind one invitation (idempotent).

        The invitation's PII fields are replaced with anonymized placeholders and
        its magic link is invalidated, so a previously shared link cannot be used
        and the row carries no personal data.
        """
        invitation = ScreeningInvitation(**doc)
        invitation_id = invitation.id or ""
        interview_deleted = False
        chunks = 0

        if invitation.interview_id:
            interview = await self._interviews.get_by_id(db, invitation.interview_id)
            chunks = await self._recordings.purge_interview_recordings(
                db, invitation.interview_id
            )
            interview_deleted = await self._interviews.delete_by_id(
                db, invitation.interview_id
            )
            if interview:
                # The synthesized job description is a per-candidate artifact and
                # is owned by the candidate's guest user; remove it too so erasure
                # leaves no candidate-linked documents behind.
                await self._job_descriptions.delete(
                    db, interview.get("jd_id", ""), interview.get("user_id", "")
                )

        now = datetime.now(UTC)
        await self._invitations.mark_erased(
            db,
            invitation_id,
            {
                "candidate_name": ERASED_NAME,
                "candidate_email": _anonymized_email(invitation_id),
                "decision_note": "",
                "interview_id": None,
                "status": "revoked",
                "token_hash": secrets.token_hex(32),
                "erased_at": now,
            },
        )
        return ErasureResult(
            invitation_id=invitation_id,
            interview_deleted=interview_deleted,
            recording_chunks_deleted=chunks,
            erased_at=now,
        )

    async def export_candidate_data(
        self, db: AsyncIOMotorDatabase, recruiter: User, invitation_id: str
    ) -> dict:
        """Return everything stored about one candidate (right of access).

        Produces a JSON-safe document covering the invitation, the interview
        session (questions, answers, evaluations, report, proctoring) and a
        manifest of the stored recordings. The magic-link ``token_hash`` and the
        guest identity are deliberately excluded.
        """
        doc = await self._invitations.get_by_id(db, invitation_id)
        if doc is None:
            raise NotFoundError("Invitation not found")
        await self._require_job_access(db, recruiter, doc)

        payload: dict = {
            "generated_at": datetime.now(UTC),
            "invitation": _invitation_data(doc),
            "interview": None,
            "recordings": [],
        }
        interview_id = doc.get("interview_id")
        if interview_id:
            raw = await self._interviews.get_by_id(db, interview_id)
            if raw:
                payload["interview"] = _interview_data(raw)
                manifest = await self._recordings.recording_manifest(db, interview_id)
                payload["recordings"] = _recording_data(manifest, raw.get("recordings") or {})

        await audit_service.record(
            db,
            action="candidate.data_exported",
            actor_id=recruiter.id,
            target_type="screening_invitation",
            target_id=invitation_id,
        )
        return jsonable_encoder(payload)

    async def purge_expired(
        self, db: AsyncIOMotorDatabase, now: datetime | None = None
    ) -> int:
        """Erase session data for invitations past the retention window.

        Returns the number of invitations erased. Safe to run repeatedly.
        """
        reference = now or datetime.now(UTC)
        cutoff = (reference - timedelta(days=settings.data_retention_days)).replace(
            tzinfo=None
        )
        rows = await self._invitations.list_erasable(
            db, cutoff, settings.retention_batch_limit
        )
        erased = 0
        for doc in rows:
            await self.erase_invitation_data(db, doc)
            erased += 1
        if erased:
            logger.info("Retention purge erased %d candidate session(s)", erased)
            await audit_service.record(
                db,
                action="retention.purged",
                target_type="screening_invitation",
                metadata={"erased": erased},
            )
        return erased


def _invitation_data(doc: dict) -> dict:
    """Project the candidate-facing fields of an invitation (no token hash)."""
    return {
        "id": str(doc.get("_id", "")),
        "job_id": doc.get("job_id", ""),
        "template_id": doc.get("template_id"),
        "candidate_name": doc.get("candidate_name", ""),
        "candidate_email": doc.get("candidate_email", ""),
        "role": doc.get("role", ""),
        "company": doc.get("company", ""),
        "interview_type": doc.get("interview_type", ""),
        "difficulty": doc.get("difficulty", ""),
        "target_questions": doc.get("target_questions", 0),
        "proctoring_mode": doc.get("proctoring_mode", ""),
        "round_minutes": doc.get("round_minutes", 0),
        "rubric": doc.get("rubric", []),
        "pass_threshold": doc.get("pass_threshold", 0.0),
        "status": doc.get("status", ""),
        "decision": doc.get("decision", ""),
        "decision_note": doc.get("decision_note", ""),
        "expires_at": doc.get("expires_at"),
        "created_at": doc.get("created_at"),
        "started_at": doc.get("started_at"),
        "completed_at": doc.get("completed_at"),
        "erased_at": doc.get("erased_at"),
    }


def _interview_data(raw: dict) -> dict:
    """Project the candidate's interview session (answers, report, proctoring)."""
    return {
        "id": str(raw.get("_id", "")),
        "status": raw.get("status", ""),
        "type": raw.get("type", ""),
        "difficulty": raw.get("difficulty", ""),
        "proctoring_mode": raw.get("proctoring_mode", ""),
        "rubric": raw.get("rubric", []),
        "pass_threshold": raw.get("pass_threshold", 0.0),
        "target_questions": raw.get("target_questions", 0),
        "created_at": raw.get("created_at"),
        "started_at": raw.get("started_at"),
        "completed_at": raw.get("completed_at"),
        "questions": raw.get("questions", []),
        "answers": raw.get("answers", []),
        "report": raw.get("report"),
        "proctoring_session": raw.get("proctoring_session"),
    }


def _recording_data(manifest: list[dict], doc_meta: dict) -> list[dict]:
    """A manifest of stored recordings (metadata only, never the bytes)."""
    rows = []
    for entry in manifest:
        kind = entry["kind"]
        meta = doc_meta.get(kind, {})
        rows.append(
            {
                "kind": kind,
                "file_id": meta.get("file_id", entry.get("file_id", "")),
                "content_type": meta.get("content_type", entry.get("content_type", "")),
                "size_bytes": entry.get("size_bytes", 0),
                "chunk_count": entry.get("chunk_count", 0),
                "finalized": meta.get("finalized", False),
                "created_at": meta.get("created_at", entry.get("created_at")),
            }
        )
    return rows


def _anonymized_email(invitation_id: str) -> str:
    """A stable, non-identifying placeholder unique to the erased row."""
    token = invitation_id[-8:] or secrets.token_hex(4)
    return f"{ERASED_NAME.strip('[]')}+{token}@{ERASED_EMAIL_DOMAIN}"


retention_service = RetentionService(
    invitation_repository,
    interview_repository,
    recording_service,
    job_description_repository,
    job_repository,
)
