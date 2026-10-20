from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import Response
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import get_current_user, get_interview_service, get_recording_service
from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import PayloadTooLargeError
from app.core.rate_limit import rate_limit
from app.models.user import User
from app.schemas.interview import (
    CurrentQuestionOut,
    InterviewCreate,
    InterviewOut,
    InterviewSummary,
    ProctoringConsent,
    ProctoringEventCreate,
)
from app.schemas.report import ReportOut
from app.schemas.transcript import TranscriptionOut
from app.services.interview_service import InterviewService
from app.services.recording_service import RecordingService

router = APIRouter()


@router.post("", response_model=InterviewOut, status_code=status.HTTP_201_CREATED)
async def create_interview(
    payload: InterviewCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: InterviewService = Depends(get_interview_service),
) -> InterviewOut:
    return await service.create(db, current_user.id, payload)


@router.get("", response_model=list[InterviewSummary])
async def list_interviews(
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: InterviewService = Depends(get_interview_service),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[InterviewSummary]:
    return await service.list(db, current_user.id, limit)


@router.get("/{interview_id}", response_model=InterviewOut)
async def get_interview(
    interview_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: InterviewService = Depends(get_interview_service),
) -> InterviewOut:
    return await service.get(db, current_user.id, interview_id)


@router.delete("/{interview_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_interview(
    interview_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: InterviewService = Depends(get_interview_service),
) -> None:
    """Discard an unfinished interview (and its recordings)."""
    await service.delete(db, current_user.id, interview_id)


@router.post("/{interview_id}/start", response_model=CurrentQuestionOut)
async def start_interview(
    interview_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: InterviewService = Depends(get_interview_service),
    _: None = Depends(rate_limit("interview_start")),
) -> CurrentQuestionOut:
    """Transition `created -> in_progress` and generate the first question."""
    return await service.start(db, current_user.id, interview_id)


@router.post("/{interview_id}/complete", response_model=InterviewOut)
async def complete_interview(
    interview_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: InterviewService = Depends(get_interview_service),
    _: None = Depends(rate_limit("interview_complete")),
) -> InterviewOut:
    """Finish an in-progress interview early and generate its report."""
    return await service.complete(db, current_user.id, interview_id)


@router.post("/{interview_id}/proctoring/consent", status_code=status.HTTP_204_NO_CONTENT)
async def proctoring_consent(
    interview_id: str,
    payload: ProctoringConsent,
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: InterviewService = Depends(get_interview_service),
) -> None:
    await service.record_proctoring_consent(db, current_user.id, interview_id, payload.consent)


@router.post(
    "/{interview_id}/proctoring/events", status_code=status.HTTP_204_NO_CONTENT
)
async def create_proctoring_event(
    interview_id: str,
    payload: ProctoringEventCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: InterviewService = Depends(get_interview_service),
    _: None = Depends(rate_limit("recording_upload")),
) -> None:
    """Record one proctoring event (camera_off, tab_blur, ...) during a session."""
    await service.record_proctoring_event(
        db, current_user.id, interview_id, payload.type, payload.details
    )


@router.get("/{interview_id}/current-question", response_model=CurrentQuestionOut)
async def get_current_question(
    interview_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: InterviewService = Depends(get_interview_service),
    _: None = Depends(rate_limit("interview_question")),
) -> CurrentQuestionOut:
    return await service.current_question(db, current_user.id, interview_id)


@router.get("/{interview_id}/report", response_model=ReportOut)
async def get_interview_report(
    interview_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: InterviewService = Depends(get_interview_service),
    _: None = Depends(rate_limit("interview_report")),
) -> ReportOut:
    """The final report; generated once and cached on the interview document."""
    return await service.report(db, current_user.id, interview_id)


READ_CHUNK = 64 * 1024


async def _read_upload(file: UploadFile, max_bytes: int) -> bytes:
    """Read at most `max_bytes` so a hostile client cannot exhaust memory."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(READ_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise PayloadTooLargeError(
                f"File size exceeds the {max_bytes // (1024 * 1024)}MB limit."
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _parse_optional_datetime(value: str | None) -> datetime | None:
    """Parse a client ISO timestamp; ignore anything malformed."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@router.post(
    "/{interview_id}/recordings/chunk",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def upload_recording_chunk(
    interview_id: str,
    kind: str = Form(...),
    seq: int = Form(...),
    finalize: bool = Form(False),
    content_type: str = Form("video/webm"),
    capture_started_at: str | None = Form(None),
    chunk: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: RecordingService = Depends(get_recording_service),
    _: None = Depends(rate_limit("recording_upload")),
) -> None:
    """Append one recorded chunk; `finalize=true` seals the recording."""
    data = await _read_upload(chunk, settings.max_recording_chunk_bytes)
    await service.append_chunk(
        db,
        current_user.id,
        interview_id,
        kind,
        seq,
        data,
        content_type,
        finalize,
        capture_started_at=_parse_optional_datetime(capture_started_at),
    )


@router.post("/{interview_id}/transcribe", response_model=TranscriptionOut)
async def transcribe_answer(
    interview_id: str,
    audio: UploadFile = File(...),
    content_type: str = Form("audio/webm"),
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: InterviewService = Depends(get_interview_service),
    _: None = Depends(rate_limit("interview_transcribe")),
) -> TranscriptionOut:
    """Server-side speech-to-text for one answer (Safari/Firefox path)."""
    data = await _read_upload(audio, settings.max_recording_chunk_bytes)
    text = await service.transcribe(
        db,
        current_user.id,
        interview_id,
        data,
        audio.filename or "answer.webm",
        content_type,
    )
    return TranscriptionOut(text=text)


@router.get("/{interview_id}/recordings/{kind}")
async def download_recording(
    interview_id: str,
    kind: str,
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: RecordingService = Depends(get_recording_service),
    _: None = Depends(rate_limit("recording_download")),
) -> Response:
    """Stream a finalized recording (ownership-checked)."""
    data, content_type = await service.read_recording(
        db, current_user.id, interview_id, kind
    )
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Content-Length": str(len(data)),
            "Content-Disposition": f'inline; filename="{kind}.webm"',
            "Cache-Control": "private, max-age=3600",
        },
    )
