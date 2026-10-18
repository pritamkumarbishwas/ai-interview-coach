"""Screening invitations.

``router`` is recruiter-facing (create/list/revoke/remind an invitation);
``public_router`` is the accountless candidate surface, addressed purely by the
magic-link token. Token responses are marked ``Cache-Control: private, no-store``
so an interview link is never cached by a shared proxy or browser history.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import (
    get_retention_service,
    get_screening_service,
    require_admin,
    require_quota,
    require_recruiter,
)
from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.models.analytics import JobAnalytics
from app.models.integrity import IntegrityReport
from app.models.review import ReviewTimeline
from app.models.scorecard import Scorecard
from app.models.shadow import ShadowReport
from app.models.user import User
from app.schemas.answer import AnswerInput, AnswerResultOut
from app.schemas.interview import CurrentQuestionOut, ProctoringEventCreate
from app.schemas.invitation import (
    InvitationCreate,
    InvitationDecision,
    InvitationExtend,
    InvitationOut,
    InvitationSessionOut,
    ShortlistEntry,
    StartInterviewRequest,
)
from app.schemas.privacy import CandidateDataExport
from app.schemas.retention import ErasureResult, PurgeResult
from app.schemas.transcript import TranscriptionOut
from app.services.retention_service import RetentionService
from app.services.screening_service import ScreeningService

router = APIRouter()
public_router = APIRouter()

NO_STORE = "private, no-store"


@router.post("", response_model=InvitationOut, status_code=status.HTTP_201_CREATED)
async def create_invitation(
    payload: InvitationCreate,
    recruiter: User = Depends(require_quota("invitations", require_recruiter)),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ScreeningService = Depends(get_screening_service),
    _: None = Depends(rate_limit("invitation_create")),
) -> InvitationOut:
    return await service.create_invitation(db, recruiter, payload)


@router.get("", response_model=list[InvitationOut])
async def list_invitations(
    job_id: str,
    recruiter: User = Depends(require_recruiter),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ScreeningService = Depends(get_screening_service),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[InvitationOut]:
    return await service.list_invitations(db, recruiter.id or "", job_id, limit)


@router.get("/shortlist", response_model=list[ShortlistEntry])
async def get_job_shortlist(
    job_id: str,
    recruiter: User = Depends(require_recruiter),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ScreeningService = Depends(get_screening_service),
) -> list[ShortlistEntry]:
    """Ranked, advisory shortlist for a job (score + integrity + decision)."""
    return await service.shortlist(db, recruiter, job_id)


@router.get("/analytics", response_model=JobAnalytics)
async def get_job_analytics(
    job_id: str,
    recruiter: User = Depends(require_recruiter),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ScreeningService = Depends(get_screening_service),
) -> JobAnalytics:
    """Aggregate funnel + score/integrity distributions for a job (advisory)."""
    return await service.analytics(db, recruiter, job_id)


@router.get("/shadow", response_model=ShadowReport)
async def get_shadow_report(
    job_id: str,
    recruiter: User = Depends(require_recruiter),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ScreeningService = Depends(get_screening_service),
) -> ShadowReport:
    """How often the advisory AI recommended the decision humans recorded (advisory)."""
    return await service.shadow(db, recruiter, job_id)


@router.get("/export")
async def export_job_candidates(
    job_id: str,
    recruiter: User = Depends(require_quota("exports", require_recruiter)),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ScreeningService = Depends(get_screening_service),
    _: None = Depends(rate_limit("candidate_export")),
) -> Response:
    """Download a job's candidate rows as CSV (recruiter-gated)."""
    csv_text = await service.export_csv(db, recruiter, job_id)
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="candidates.csv"',
            "Cache-Control": NO_STORE,
        },
    )


@router.get("/export.pdf")
async def export_job_candidates_pdf(
    job_id: str,
    recruiter: User = Depends(require_quota("exports", require_recruiter)),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ScreeningService = Depends(get_screening_service),
    _: None = Depends(rate_limit("candidate_export")),
) -> Response:
    """Download a one-page PDF summary of a job's pipeline (recruiter-gated)."""
    data = await service.export_pdf(db, recruiter, job_id)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="screening-summary.pdf"',
            "Cache-Control": NO_STORE,
        },
    )


@router.delete("/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invitation(
    invitation_id: str,
    recruiter: User = Depends(require_recruiter),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ScreeningService = Depends(get_screening_service),
) -> None:
    await service.revoke(db, recruiter, invitation_id)


@router.post("/retention/purge", response_model=PurgeResult)
async def purge_expired_candidates(
    admin: User = Depends(require_admin),
    db: AsyncIOMotorDatabase = Depends(get_db),
    retention: RetentionService = Depends(get_retention_service),
) -> PurgeResult:
    """Erase session data past the retention window (admin-triggered)."""
    return PurgeResult(erased=await retention.purge_expired(db))


@router.post("/{invitation_id}/erase", response_model=ErasureResult)
async def erase_candidate_data(
    invitation_id: str,
    recruiter: User = Depends(require_recruiter),
    db: AsyncIOMotorDatabase = Depends(get_db),
    retention: RetentionService = Depends(get_retention_service),
    _: None = Depends(rate_limit("candidate_erase")),
) -> ErasureResult:
    """Destroy one candidate's interview + recording (right to erasure)."""
    return await retention.erase_candidate(db, recruiter, invitation_id)


@router.get("/{invitation_id}/data", response_model=CandidateDataExport)
async def export_candidate_data(
    invitation_id: str,
    response: Response,
    recruiter: User = Depends(require_quota("exports", require_recruiter)),
    db: AsyncIOMotorDatabase = Depends(get_db),
    retention: RetentionService = Depends(get_retention_service),
    _: None = Depends(rate_limit("candidate_export")),
) -> CandidateDataExport:
    """Export all data held about a candidate (right of access, GDPR Art. 15)."""
    response.headers["Cache-Control"] = NO_STORE
    data = await retention.export_candidate_data(db, recruiter, invitation_id)
    return CandidateDataExport.model_validate(data)


@router.post("/{invitation_id}/remind", response_model=InvitationOut)
async def remind_invitation(
    invitation_id: str,
    recruiter: User = Depends(require_recruiter),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ScreeningService = Depends(get_screening_service),
    _: None = Depends(rate_limit("invitation_remind")),
) -> InvitationOut:
    return await service.remind(db, recruiter, invitation_id)


@router.post("/{invitation_id}/extend", response_model=InvitationOut)
async def extend_invitation(
    invitation_id: str,
    payload: InvitationExtend,
    recruiter: User = Depends(require_recruiter),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ScreeningService = Depends(get_screening_service),
) -> InvitationOut:
    """Grant extra time on an invitation (accessibility accommodation)."""
    return await service.extend(db, recruiter, invitation_id, payload.minutes)


@router.patch("/{invitation_id}/decision", response_model=InvitationOut)
async def decide_invitation(
    invitation_id: str,
    payload: InvitationDecision,
    recruiter: User = Depends(require_recruiter),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ScreeningService = Depends(get_screening_service),
) -> InvitationOut:
    """Record the human decision: advance, hold, decline, or pending (undo)."""
    return await service.decide(
        db, recruiter, invitation_id, payload.decision, payload.note
    )


@router.get("/{invitation_id}/integrity", response_model=IntegrityReport)
async def get_invitation_integrity(
    invitation_id: str,
    recruiter: User = Depends(require_recruiter),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ScreeningService = Depends(get_screening_service),
) -> IntegrityReport:
    """Advisory integrity summary + flagged-moment timeline (never a verdict)."""
    return await service.integrity(db, recruiter, invitation_id)


@router.get("/{invitation_id}/scorecard", response_model=Scorecard)
async def get_invitation_scorecard(
    invitation_id: str,
    recruiter: User = Depends(require_recruiter),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ScreeningService = Depends(get_screening_service),
) -> Scorecard:
    """Advisory, rubric-based competency scorecard with cited evidence."""
    return await service.scorecard(db, recruiter, invitation_id)


@router.get("/{invitation_id}/timeline", response_model=ReviewTimeline)
async def get_invitation_timeline(
    invitation_id: str,
    recruiter: User = Depends(require_recruiter),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ScreeningService = Depends(get_screening_service),
) -> ReviewTimeline:
    """Answers + integrity moments anchored to recording time (advisory)."""
    return await service.timeline(db, recruiter, invitation_id)


@router.get("/{invitation_id}/recordings/{kind}")
async def download_invitation_recording(
    invitation_id: str,
    kind: str,
    recruiter: User = Depends(require_recruiter),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ScreeningService = Depends(get_screening_service),
    _: None = Depends(rate_limit("recording_download")),
) -> Response:
    """Stream a candidate's finalized recording (ownership-gated by invitation)."""
    data, content_type = await service.recording(db, recruiter, invitation_id, kind)
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Content-Length": str(len(data)),
            "Content-Disposition": f'inline; filename="{kind}.webm"',
            "Cache-Control": NO_STORE,
        },
    )


@public_router.get("/{token}", response_model=InvitationSessionOut)
async def get_session(
    token: str,
    response: Response,
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ScreeningService = Depends(get_screening_service),
    _: None = Depends(rate_limit("screening_session")),
) -> InvitationSessionOut:
    """Pre-check: what this interview is and whether it can start now."""
    response.headers["Cache-Control"] = NO_STORE
    return await service.session(db, token)


@public_router.post("/{token}/start", response_model=CurrentQuestionOut)
async def start_interview(
    token: str,
    payload: StartInterviewRequest,
    response: Response,
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ScreeningService = Depends(get_screening_service),
    _: None = Depends(rate_limit("screening_start")),
) -> CurrentQuestionOut:
    response.headers["Cache-Control"] = NO_STORE
    return await service.start(db, token, payload.consent)


@public_router.get("/{token}/current-question", response_model=CurrentQuestionOut)
async def current_question(
    token: str,
    response: Response,
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ScreeningService = Depends(get_screening_service),
    _: None = Depends(rate_limit("screening_session")),
) -> CurrentQuestionOut:
    response.headers["Cache-Control"] = NO_STORE
    return await service.current_question(db, token)


@public_router.post(
    "/{token}/questions/{question_id}/answer", response_model=AnswerResultOut
)
async def answer_question(
    token: str,
    question_id: str,
    payload: AnswerInput,
    response: Response,
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ScreeningService = Depends(get_screening_service),
    _: None = Depends(rate_limit("screening_answer")),
) -> AnswerResultOut:
    response.headers["Cache-Control"] = NO_STORE
    return await service.answer(db, token, question_id, payload)


READ_CHUNK = 64 * 1024


def _parse_optional_datetime(value: str | None) -> datetime | None:
    """Parse a client ISO timestamp; ignore anything malformed."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


async def _read_upload(file: UploadFile, max_bytes: int) -> bytes:
    """Read at most `max_bytes` so a hostile client cannot exhaust memory."""
    chunks: list[bytes] = []
    total = 0
    while True:
        block = await file.read(READ_CHUNK)
        if not block:
            break
        total += len(block)
        if total > max_bytes:
            from app.core.exceptions import PayloadTooLargeError

            raise PayloadTooLargeError(
                f"File size exceeds the {max_bytes // (1024 * 1024)}MB limit."
            )
        chunks.append(block)
    return b"".join(chunks)


@public_router.post("/{token}/proctoring/events", status_code=status.HTTP_204_NO_CONTENT)
async def record_proctoring_event(
    token: str,
    payload: ProctoringEventCreate,
    response: Response,
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ScreeningService = Depends(get_screening_service),
    _: None = Depends(rate_limit("screening_recording")),
) -> None:
    """Record one advisory integrity signal for the candidate's session."""
    response.headers["Cache-Control"] = NO_STORE
    await service.record_event(db, token, payload.type, payload.details)


@public_router.post("/{token}/recordings/chunk", status_code=status.HTTP_204_NO_CONTENT)
async def upload_recording_chunk(
    token: str,
    response: Response,
    kind: str = Form(...),
    seq: int = Form(...),
    finalize: bool = Form(False),
    content_type: str = Form("video/webm"),
    capture_started_at: str | None = Form(None),
    chunk: UploadFile = File(...),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ScreeningService = Depends(get_screening_service),
    _: None = Depends(rate_limit("screening_recording")),
) -> None:
    """Append one recorded chunk for a guest session; `finalize=true` seals it."""
    response.headers["Cache-Control"] = NO_STORE
    data = await _read_upload(chunk, settings.max_recording_chunk_bytes)
    await service.append_recording(
        db,
        token,
        kind,
        seq,
        data,
        content_type,
        finalize,
        capture_started_at=_parse_optional_datetime(capture_started_at),
    )


@public_router.post("/{token}/transcribe", response_model=TranscriptionOut)
async def transcribe_answer(
    token: str,
    response: Response,
    audio: UploadFile = File(...),
    content_type: str = Form("audio/webm"),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ScreeningService = Depends(get_screening_service),
    _: None = Depends(rate_limit("screening_transcribe")),
) -> TranscriptionOut:
    """Server-side speech-to-text for one recorded answer (Safari/Firefox path)."""
    response.headers["Cache-Control"] = NO_STORE
    data = await _read_upload(audio, settings.max_recording_chunk_bytes)
    text = await service.transcribe(
        db, token, data, audio.filename or "answer.webm", content_type
    )
    return TranscriptionOut(text=text)
