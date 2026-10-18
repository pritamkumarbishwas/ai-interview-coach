"""Screening invitations: invite a guest, entry, scheduling, and the session.

Candidates are guests with no account. Each invitation owns an internal guest
identity (``guest_user_id``) and a synthesized job description, so the existing
interview engine (which is keyed by ``user_id``) runs unchanged: the screening
service simply acts *as* the guest when it delegates to ``InterviewService``.

The round deadline is server-authoritative: it is set when the candidate starts
and enforced on every subsequent session request.
"""

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError
from app.core.mailer import EmailMessage, get_mailer
from app.core.transcription import get_transcriber
from app.emails.templates import invitation_email, reminder_email
from app.models.interview import Interview
from app.models.invitation import ScreeningInvitation
from app.models.job import Job
from app.models.job_description import JobDescription
from app.models.template import InterviewTemplate
from app.models.template_config import RoundConfig
from app.models.user import User
from app.repositories.interview_repository import InterviewRepository
from app.repositories.invitation_repository import InvitationRepository
from app.repositories.job_description_repository import JobDescriptionRepository
from app.repositories.job_repository import JobRepository
from app.repositories.template_repository import TemplateRepository
from app.schemas.answer import AnswerInput, AnswerResultOut
from app.schemas.interview import CurrentQuestionOut
from app.schemas.invitation import (
    InvitationCreate,
    InvitationOut,
    InvitationSessionOut,
)
from app.services.audit_service import audit_service
from app.services.interview_service import InterviewService
from app.services.recording_service import RecordingService

logger = logging.getLogger(__name__)

DEFAULT_ROUND = RoundConfig(key="screen", label="Screening")
SNIPPET_LENGTH = 180


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


def _naive_utc(value: datetime) -> datetime:
    """Normalize to naive UTC (MongoDB returns naive datetimes)."""
    return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value


def _is_past(value: datetime | None) -> bool:
    if value is None:
        return False
    return _naive_utc(value) < _now().replace(tzinfo=None)


def _interview_url(token: str) -> str:
    return f"{settings.frontend_url.rstrip('/')}/interview/{token}"


def _snippet(text: str) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= SNIPPET_LENGTH else compact[: SNIPPET_LENGTH - 3] + "..."


class ScreeningService:
    def __init__(
        self,
        invitations: InvitationRepository,
        jobs: JobRepository,
        templates: TemplateRepository,
        job_descriptions: JobDescriptionRepository,
        interviews: InterviewRepository,
        interview_service: InterviewService,
        recordings: RecordingService,
    ) -> None:
        self._invitations = invitations
        self._jobs = jobs
        self._templates = templates
        self._job_descriptions = job_descriptions
        self._interviews = interviews
        self._interview_service = interview_service
        self._recordings = recordings

    # --- Recruiter-facing --------------------------------------------------
    async def create_invitation(
        self, db: AsyncIOMotorDatabase, recruiter: User, payload: InvitationCreate
    ) -> InvitationOut:
        job = Job(**await self._require_job(db, recruiter.id or "", payload.job_id))
        template = await self._load_template(db, recruiter.id or "", job.template_id)
        round_config = self._select_round(template, payload.round_key)

        # The guest identity is internal: no User record, and the prefix keeps it
        # from ever colliding with a real ObjectId.
        guest_user_id = f"guest_{secrets.token_hex(12)}"
        jd_id = await self._synthesize_jd(db, guest_user_id, job)

        token = secrets.token_urlsafe(32)
        ttl_days = payload.expires_in_days or settings.invitation_ttl_days
        invitation = ScreeningInvitation(
            job_id=job.id or "",
            template_id=job.template_id,
            guest_user_id=guest_user_id,
            jd_id=jd_id,
            candidate_name=payload.candidate_name.strip(),
            candidate_email=payload.candidate_email.strip().lower(),
            token_hash=_hash_token(token),
            role=job.title,
            company=job.company,
            interview_type=round_config.interview_type,
            difficulty=round_config.difficulty,
            target_questions=round_config.target_questions,
            proctoring_mode=template.config.proctoring_mode if template else "strict",
            round_minutes=round_config.duration_minutes + payload.extra_minutes,
            expires_at=_now() + timedelta(days=ttl_days),
            start_window_start=payload.start_window_start,
            start_window_end=payload.start_window_end,
            created_by=recruiter.id or "",
        )
        invitation.id = await self._invitations.insert(db, invitation)

        url = _interview_url(token)
        await self._send_invitation_email(invitation, url)
        await audit_service.record(
            db,
            action="invitation.created",
            actor_id=recruiter.id,
            target_type="screening_invitation",
            target_id=invitation.id,
            metadata={"job_id": job.id, "email": invitation.candidate_email},
        )
        return self._to_out(invitation, accept_url=url)

    async def list_invitations(
        self, db: AsyncIOMotorDatabase, recruiter_id: str, job_id: str, limit: int
    ) -> list[InvitationOut]:
        await self._require_job(db, recruiter_id, job_id)
        docs = await self._invitations.list_for_job(db, job_id, limit)
        return [
            InvitationOut(
                id=doc["_id"],
                job_id=doc["job_id"],
                candidate_name=doc.get("candidate_name", ""),
                candidate_email=doc["candidate_email"],
                role=doc.get("role", ""),
                status=doc["status"],
                expires_at=doc["expires_at"],
                round_minutes=doc.get("round_minutes", 30),
                round_deadline=doc.get("round_deadline"),
                interview_id=doc.get("interview_id"),
                created_at=doc["created_at"],
            )
            for doc in docs
        ]

    async def revoke(
        self, db: AsyncIOMotorDatabase, recruiter: User, invitation_id: str
    ) -> None:
        doc = await self._invitations.find_owned(db, invitation_id, recruiter.id or "")
        if doc is None:
            raise NotFoundError("Invitation not found")
        await self._invitations.set_status(db, invitation_id, "revoked")
        await audit_service.record(
            db,
            action="invitation.revoked",
            actor_id=recruiter.id,
            target_type="screening_invitation",
            target_id=invitation_id,
        )

    async def remind(
        self, db: AsyncIOMotorDatabase, recruiter: User, invitation_id: str
    ) -> InvitationOut:
        doc = await self._invitations.find_owned(db, invitation_id, recruiter.id or "")
        if doc is None:
            raise NotFoundError("Invitation not found")
        invitation = ScreeningInvitation(**doc)
        if invitation.status != "pending":
            raise ConflictError("Only pending invitations can be reminded.")

        # A reminder must carry a working link, so the token is rotated (the
        # raw token is never stored, only its hash).
        token = secrets.token_urlsafe(32)
        await self._invitations.rotate_token(db, invitation_id, _hash_token(token))
        url = _interview_url(token)
        await self._send_reminder_email(invitation, url)
        await audit_service.record(
            db,
            action="invitation.reminded",
            actor_id=recruiter.id,
            target_type="screening_invitation",
            target_id=invitation_id,
        )
        return self._to_out(invitation, accept_url=url)

    async def extend(
        self, db: AsyncIOMotorDatabase, recruiter: User, invitation_id: str, minutes: int
    ) -> InvitationOut:
        """Grant extra time (accommodation) by pushing the round deadline out.

        Works on pending and started invitations; the interview itself is
        unchanged — the deadline lives on the invitation, so the extension
        applies to the candidate's remaining time.
        """
        doc = await self._invitations.find_owned(db, invitation_id, recruiter.id or "")
        if doc is None:
            raise NotFoundError("Invitation not found")
        invitation = ScreeningInvitation(**doc)
        if invitation.status in ("revoked", "completed"):
            raise ConflictError("This invitation can no longer be extended.")

        base = invitation.round_deadline or _now()
        new_deadline = _naive_utc(base) + timedelta(minutes=minutes)
        await self._invitations.set_deadline(db, invitation_id, new_deadline)
        # Enforcing an expired deadline flips the status to "expired"; an
        # extension must reopen the invitation so the candidate can continue.
        if invitation.status == "expired":
            restored = "started" if invitation.interview_id else "pending"
            await self._invitations.set_status(db, invitation_id, restored)
            invitation.status = restored
        await audit_service.record(
            db,
            action="invitation.extended",
            actor_id=recruiter.id,
            target_type="screening_invitation",
            target_id=invitation_id,
            metadata={"minutes": minutes},
        )
        invitation.round_deadline = new_deadline
        return self._to_out(invitation)

    # --- Candidate-facing (token) ------------------------------------------
    async def session(self, db: AsyncIOMotorDatabase, token: str) -> InvitationSessionOut:
        invitation = await self._require_token(db, token)
        return InvitationSessionOut(
            status=invitation.status,
            role=invitation.role,
            company=invitation.company,
            interview_type=invitation.interview_type,
            difficulty=invitation.difficulty,
            proctoring_mode=invitation.proctoring_mode,
            consent_required=invitation.proctoring_mode != "off",
            total_questions=invitation.target_questions,
            started=invitation.interview_id is not None,
            expires_at=invitation.expires_at,
            start_window_start=invitation.start_window_start,
            start_window_end=invitation.start_window_end,
            round_deadline=invitation.round_deadline,
        )

    async def start(
        self, db: AsyncIOMotorDatabase, token: str, consent: bool
    ) -> CurrentQuestionOut:
        invitation = await self._require_token(db, token)

        # Idempotent: a refresh resumes the existing session instead of failing.
        if invitation.interview_id:
            return await self._interview_service.current_question(
                db, invitation.guest_user_id, invitation.interview_id
            )

        self._check_window(invitation)
        if invitation.proctoring_mode != "off" and not consent:
            raise ConflictError("Proctoring consent is required to start the interview.")

        deadline = _now() + timedelta(minutes=invitation.round_minutes)
        interview = Interview(
            user_id=invitation.guest_user_id,
            resume_id="",
            jd_id=invitation.jd_id,
            role=invitation.role,
            kind="screening",
            type=invitation.interview_type,
            difficulty=invitation.difficulty,
            proctoring_mode=invitation.proctoring_mode,
            target_questions=invitation.target_questions,
        )
        interview.id = await self._interviews.insert(db, interview)
        await self._invitations.mark_started(db, invitation.id or "", interview.id, deadline)
        if invitation.proctoring_mode != "off":
            await self._interview_service.record_proctoring_consent(
                db, invitation.guest_user_id, interview.id, True
            )
        await audit_service.record(
            db,
            action="invitation.started",
            target_type="screening_invitation",
            target_id=invitation.id,
            metadata={"interview_id": interview.id},
        )
        return await self._interview_service.start(
            db, invitation.guest_user_id, interview.id or ""
        )

    async def current_question(
        self, db: AsyncIOMotorDatabase, token: str
    ) -> CurrentQuestionOut:
        invitation = await self._require_token(db, token)
        if not invitation.interview_id:
            raise ConflictError("The interview has not been started yet.")
        await self._enforce_deadline(db, invitation)
        return await self._interview_service.current_question(
            db, invitation.guest_user_id, invitation.interview_id
        )

    async def answer(
        self,
        db: AsyncIOMotorDatabase,
        token: str,
        question_id: str,
        payload: AnswerInput,
    ) -> AnswerResultOut:
        invitation = await self._require_token(db, token)
        if not invitation.interview_id:
            raise ConflictError("The interview has not been started yet.")
        await self._enforce_deadline(db, invitation)
        result = await self._interview_service.answer_question(
            db, invitation.guest_user_id, question_id, payload
        )
        if result.status == "completed":
            await self._invitations.set_status(db, invitation.id or "", "completed")
        return result

    async def append_recording(
        self,
        db: AsyncIOMotorDatabase,
        token: str,
        kind: str,
        seq: int,
        data: bytes,
        content_type: str,
        finalize: bool,
    ) -> None:
        """Store one recorded chunk for the guest's interview (token-addressed).

        Recording is a diagnostic side channel, so the round deadline is not
        enforced here: a chunk that arrives just as time expires must still be
        kept rather than discarded.
        """
        invitation = await self._require_token(db, token)
        if not invitation.interview_id:
            raise ConflictError("The interview has not been started yet.")
        await self._recordings.append_chunk(
            db,
            invitation.guest_user_id,
            invitation.interview_id,
            kind,
            seq,
            data,
            content_type,
            finalize,
        )

    async def record_event(
        self,
        db: AsyncIOMotorDatabase,
        token: str,
        event_type: str,
        details: dict,
    ) -> None:
        """Record one advisory integrity signal (camera_off, tab_blur, ...)."""
        invitation = await self._require_token(db, token)
        if not invitation.interview_id:
            raise ConflictError("The interview has not been started yet.")
        await self._interview_service.record_proctoring_event(
            db, invitation.guest_user_id, invitation.interview_id, event_type, details
        )

    async def transcribe(
        self,
        db: AsyncIOMotorDatabase,
        token: str,
        data: bytes,
        filename: str,
        content_type: str,
    ) -> str:
        """Server-side STT for one recorded answer (portable alternative to Web Speech)."""
        invitation = await self._require_token(db, token)
        if not invitation.interview_id:
            raise ConflictError("The interview has not been started yet.")
        await self._enforce_deadline(db, invitation)
        return await get_transcriber().transcribe(data, filename, content_type)

    # --- Helpers -----------------------------------------------------------
    async def _require_token(
        self, db: AsyncIOMotorDatabase, token: str
    ) -> ScreeningInvitation:
        doc = await self._invitations.find_by_token_hash(db, _hash_token(token))
        if doc is None:
            raise NotFoundError("Invitation not found")
        invitation = ScreeningInvitation(**doc)
        if invitation.status == "revoked":
            raise ConflictError("This invitation has been revoked.")
        if invitation.status == "expired" or (
            invitation.status == "pending" and _is_past(invitation.expires_at)
        ):
            raise ConflictError("This invitation has expired.")
        return invitation

    async def _enforce_deadline(
        self, db: AsyncIOMotorDatabase, invitation: ScreeningInvitation
    ) -> None:
        if _is_past(invitation.round_deadline):
            await self._invitations.set_status(db, invitation.id or "", "expired")
            raise ConflictError("The interview time limit has been reached.")

    @staticmethod
    def _check_window(invitation: ScreeningInvitation) -> None:
        now = _now().replace(tzinfo=None)
        if invitation.start_window_start and _naive_utc(invitation.start_window_start) > now:
            raise ConflictError("This interview is not open yet.")
        if invitation.start_window_end and _naive_utc(invitation.start_window_end) < now:
            raise ConflictError("The interview window has closed.")

    async def _require_job(
        self, db: AsyncIOMotorDatabase, user_id: str, job_id: str
    ) -> dict:
        doc = await self._jobs.find_owned(db, job_id, user_id)
        if doc is None:
            raise NotFoundError("Job not found")
        return doc

    async def _load_template(
        self, db: AsyncIOMotorDatabase, user_id: str, template_id: str | None
    ) -> InterviewTemplate | None:
        if not template_id:
            return None
        doc = await self._templates.find_owned(db, template_id, user_id)
        return InterviewTemplate(**doc) if doc else None

    @staticmethod
    def _select_round(
        template: InterviewTemplate | None, round_key: str | None
    ) -> RoundConfig:
        if template is None or not template.config.rounds:
            return DEFAULT_ROUND
        if round_key is None:
            return template.config.rounds[0]
        for round_ in template.config.rounds:
            if round_.key == round_key:
                return round_
        raise NotFoundError(f"Round {round_key!r} is not part of this template")

    async def _synthesize_jd(
        self, db: AsyncIOMotorDatabase, guest_user_id: str, job: Job
    ) -> str:
        jd = JobDescription(
            user_id=guest_user_id,
            title=job.title,
            company=job.company,
            raw_text=job.description or f"{job.title} at {job.company}".strip(),
            snippet=_snippet(job.description or job.title),
            structured_data={
                "role_title": job.title,
                "required_skills": [],
                "responsibilities": [],
            },
        )
        return await self._job_descriptions.insert(db, jd)

    async def _send_invitation_email(
        self, invitation: ScreeningInvitation, interview_url: str
    ) -> None:
        content = invitation_email(
            candidate_name=invitation.candidate_name,
            role=invitation.role,
            company=invitation.company,
            interview_url=interview_url,
            expires_at=invitation.expires_at,
        )
        await self._send(invitation.candidate_email, content)

    async def _send_reminder_email(
        self, invitation: ScreeningInvitation, interview_url: str
    ) -> None:
        content = reminder_email(
            candidate_name=invitation.candidate_name,
            role=invitation.role,
            company=invitation.company,
            interview_url=interview_url,
            expires_at=invitation.expires_at,
        )
        await self._send(invitation.candidate_email, content)

    async def _send(self, to: str, content) -> None:
        try:
            await get_mailer().send(
                EmailMessage(to=to, subject=content.subject, text=content.text, html=content.html)
            )
        except Exception as exc:
            # Email is a side channel; the recruiter still gets the accept URL.
            logger.warning("Could not send screening invitation email: %s", exc)

    @staticmethod
    def _to_out(
        invitation: ScreeningInvitation, accept_url: str | None = None
    ) -> InvitationOut:
        return InvitationOut(
            id=invitation.id or "",
            job_id=invitation.job_id,
            candidate_name=invitation.candidate_name,
            candidate_email=invitation.candidate_email,
            role=invitation.role,
            status=invitation.status,
            expires_at=invitation.expires_at,
            round_minutes=invitation.round_minutes,
            round_deadline=invitation.round_deadline,
            interview_id=invitation.interview_id,
            created_at=invitation.created_at,
            accept_url=accept_url,
        )
