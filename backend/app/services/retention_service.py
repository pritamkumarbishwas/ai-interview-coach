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

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.models.invitation import ScreeningInvitation
from app.models.user import User
from app.repositories.interview_repository import InterviewRepository, interview_repository
from app.repositories.invitation_repository import InvitationRepository, invitation_repository
from app.schemas.retention import ErasureResult
from app.services.audit_service import audit_service
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
    ) -> None:
        self._invitations = invitations
        self._interviews = interviews
        self._recordings = recordings

    async def erase_candidate(
        self, db: AsyncIOMotorDatabase, recruiter: User, invitation_id: str
    ) -> ErasureResult:
        """Recruiter-triggered erasure of one candidate's session data."""
        doc = await self._invitations.find_owned(db, invitation_id, recruiter.id or "")
        if doc is None:
            raise NotFoundError("Invitation not found")
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
            chunks = await self._recordings.purge_interview_recordings(
                db, invitation.interview_id
            )
            interview_deleted = await self._interviews.delete_by_id(
                db, invitation.interview_id
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


def _anonymized_email(invitation_id: str) -> str:
    """A stable, non-identifying placeholder unique to the erased row."""
    token = invitation_id[-8:] or secrets.token_hex(4)
    return f"{ERASED_NAME.strip('[]')}+{token}@{ERASED_EMAIL_DOMAIN}"


retention_service = RetentionService(
    invitation_repository, interview_repository, recording_service
)
