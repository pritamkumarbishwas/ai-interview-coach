import re
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import get_current_user, get_resume_service
from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import PayloadTooLargeError
from app.core.rate_limit import rate_limit
from app.models.resume import Resume
from app.models.user import User
from app.schemas.resume import (
    ResumeActionResponse,
    ResumeSummary,
    ResumeTextResponse,
    ResumeUploadResponse,
)
from app.services.resume_service import ResumeService

router = APIRouter()

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


def _content_disposition(filename: str) -> str:
    ascii_name = re.sub(r"[^A-Za-z0-9._-]", "_", filename) or "resume"
    return (
        f'attachment; filename="{ascii_name}"; '
        f"filename*=UTF-8''{quote(filename, safe='')}"
    )


@router.post(
    "/upload",
    response_model=ResumeUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_resume(
    response: Response,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ResumeService = Depends(get_resume_service),
    _: None = Depends(rate_limit("resume_upload")),
) -> ResumeUploadResponse:
    file_bytes = await _read_upload(file, settings.max_upload_bytes)
    result = await service.upload(
        db,
        current_user.id,
        filename=file.filename,
        file_bytes=file_bytes,
        content_type=file.content_type,
    )
    if result.deduplicated:
        response.status_code = status.HTTP_200_OK
    elif result.analysis_status == "pending":
        response.status_code = status.HTTP_202_ACCEPTED
    return result


@router.get("", response_model=list[ResumeSummary])
async def list_resumes(
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ResumeService = Depends(get_resume_service),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[ResumeSummary]:
    return await service.list(db, current_user.id, limit)


@router.get(
    "/{resume_id}",
    response_model=Resume,
    response_model_exclude={
        "storage_key": True,
        "original_file_id": True,
        "content_file_id": True,
        "storage_backend": True,
        "previews": {"__all__": {"file_id"}},
    },
)
async def get_resume(
    resume_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ResumeService = Depends(get_resume_service),
) -> Resume:
    return await service.get(db, current_user.id, resume_id)


@router.get("/{resume_id}/text", response_model=ResumeTextResponse)
async def get_resume_text(
    resume_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ResumeService = Depends(get_resume_service),
) -> ResumeTextResponse:
    return await service.get_text(db, current_user.id, resume_id)


@router.get("/{resume_id}/file")
async def download_resume_file(
    resume_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ResumeService = Depends(get_resume_service),
) -> Response:
    data, filename, mime_type = await service.get_original(
        db, current_user.id, resume_id
    )
    return Response(
        content=data,
        media_type=mime_type,
        headers={
            "Content-Disposition": _content_disposition(filename),
            "Content-Length": str(len(data)),
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{resume_id}/preview/{page}")
async def get_resume_preview(
    resume_id: str,
    page: int,
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ResumeService = Depends(get_resume_service),
) -> Response:
    data = await service.get_preview(db, current_user.id, resume_id, page)
    return Response(
        content=data,
        media_type="image/png",
        headers={
            "Cache-Control": "private, max-age=300",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/{resume_id}/analyze", response_model=ResumeActionResponse)
async def retry_resume_analysis(
    resume_id: str,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ResumeService = Depends(get_resume_service),
    _: None = Depends(rate_limit("resume_analyze")),
) -> ResumeActionResponse:
    analysis_status = await service.retry_analysis(db, current_user.id, resume_id)
    if analysis_status == "pending":
        response.status_code = status.HTTP_202_ACCEPTED
    return ResumeActionResponse(id=resume_id, analysis_status=analysis_status)


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resume(
    resume_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ResumeService = Depends(get_resume_service),
) -> None:
    await service.delete(db, current_user.id, resume_id)
