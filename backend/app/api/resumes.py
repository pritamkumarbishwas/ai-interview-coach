from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import get_current_user, get_resume_service
from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import PayloadTooLargeError
from app.core.rate_limit import rate_limit
from app.models.resume import Resume
from app.models.user import User
from app.schemas.resume import ResumeSummary, ResumeUploadResponse
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


@router.post(
    "/upload",
    response_model=ResumeUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_resume(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ResumeService = Depends(get_resume_service),
    _: None = Depends(rate_limit("resume_upload")),
) -> ResumeUploadResponse:
    file_bytes = await _read_upload(file, settings.max_upload_bytes)
    return await service.upload(
        db,
        current_user.id,
        filename=file.filename,
        file_bytes=file_bytes,
    )


@router.get("", response_model=list[ResumeSummary])
async def list_resumes(
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ResumeService = Depends(get_resume_service),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[ResumeSummary]:
    return await service.list(db, current_user.id, limit)


@router.get("/{resume_id}", response_model=Resume, response_model_exclude={"storage_key"})
async def get_resume(
    resume_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ResumeService = Depends(get_resume_service),
) -> Resume:
    return await service.get(db, current_user.id, resume_id)


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resume(
    resume_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ResumeService = Depends(get_resume_service),
) -> None:
    await service.delete(db, current_user.id, resume_id)
