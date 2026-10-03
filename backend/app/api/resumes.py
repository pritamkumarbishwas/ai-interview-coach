import logging
import uuid
from pathlib import Path

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import get_current_user
from app.core.config import resolve_storage_dir, settings
from app.core.database import get_db
from app.models.resume import Resume
from app.models.user import User
from app.prompts.templates import EXTRACT_RESUME_INFO_PROMPT
from app.schemas.resume import ResumeStructuredData, ResumeSummary, ResumeUploadResponse
from app.services.llm_service import llm_service
from app.services.parsers import parse_docx, parse_pdf

logger = logging.getLogger(__name__)

router = APIRouter()

PDF_MAGIC = b"%PDF-"
DOCX_MAGIC = b"PK\x03\x04"
READ_CHUNK = 64 * 1024


def _extension_for(filename: str | None) -> str:
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A file name is required.",
        )
    extension = Path(filename).suffix.lower()
    if extension not in {".pdf", ".docx"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF and DOCX files are supported.",
        )
    return extension


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
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File size exceeds the {max_bytes // (1024 * 1024)}MB limit.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _assert_magic_bytes(data: bytes, extension: str) -> None:
    expected = PDF_MAGIC if extension == ".pdf" else DOCX_MAGIC
    if not data.startswith(expected):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The file content does not match its extension.",
        )


def _save_to_disk(data: bytes, user_id: str, extension: str) -> Path:
    directory = resolve_storage_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{user_id}_{uuid.uuid4().hex}{extension}"
    path.write_bytes(data)
    return path


@router.post(
    "/upload",
    response_model=ResumeUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_resume(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> ResumeUploadResponse:
    extension = _extension_for(file.filename)
    file_bytes = await _read_upload(file, settings.max_upload_bytes)
    if not file_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The file is empty.")
    _assert_magic_bytes(file_bytes, extension)

    # Blocking PDF/DOCX parsing runs in the thread pool.
    try:
        if extension == ".pdf":
            raw_text = await run_in_threadpool(parse_pdf, file_bytes)
        else:
            raw_text = await run_in_threadpool(parse_docx, file_bytes)
    except Exception as exc:  # parser raises library-specific errors
        logger.warning("Failed to parse %s upload: %s", extension, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to parse file: the document may be corrupt or password protected.",
        ) from exc

    if not raw_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not extract any text from the file.",
        )

    prompt = EXTRACT_RESUME_INFO_PROMPT.format(text=raw_text)
    structured_data = await llm_service.generate_structured(prompt, ResumeStructuredData)

    filepath = _save_to_disk(file_bytes, current_user.id, extension)

    resume = Resume(
        user_id=current_user.id,
        filename=file.filename,
        file_size=len(file_bytes),
        storage_key=filepath.name,
        raw_text=raw_text,
        structured_data=structured_data.model_dump(),
    )
    try:
        result = await db.resumes.insert_one(resume.model_dump(by_alias=True, exclude={"id"}))
    except Exception:
        # Do not leave an orphaned file behind when persistence fails.
        filepath.unlink(missing_ok=True)
        raise
    resume.id = str(result.inserted_id)

    return ResumeUploadResponse(
        id=resume.id,
        filename=resume.filename,
        structured_data=structured_data,
    )


@router.get("", response_model=list[ResumeSummary])
async def list_resumes(
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[ResumeSummary]:
    cursor = (
        db.resumes.find(
            {"user_id": current_user.id},
            {"raw_text": 0},
        )
        .sort("created_at", -1)
        .limit(limit)
    )
    summaries: list[ResumeSummary] = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        data = doc.get("structured_data") or {}
        summaries.append(
            ResumeSummary(
                id=doc["_id"],
                filename=doc.get("filename", "resume"),
                file_size=doc.get("file_size", 0),
                skills=list(data.get("skills", []))[:8],
                created_at=doc["created_at"],
            )
        )
    return summaries


@router.get(
    "/{resume_id}",
    response_model=Resume,
    response_model_exclude={"storage_key"},
)
async def get_resume(
    resume_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> Resume:
    doc = await _find_resume(db, resume_id, current_user.id)
    doc["_id"] = str(doc["_id"])
    return Resume(**doc)


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resume(
    resume_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> None:
    doc = await _find_resume(db, resume_id, current_user.id)
    await db.resumes.delete_one({"_id": doc["_id"]})
    _delete_stored_file(doc.get("storage_key", ""), current_user.id)


async def _find_resume(db: AsyncIOMotorDatabase, resume_id: str, user_id: str) -> dict:
    try:
        object_id = ObjectId(resume_id)
    except (InvalidId, TypeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found"
        ) from None
    doc = await db.resumes.find_one({"_id": object_id, "user_id": user_id})
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")
    return doc


def _delete_stored_file(storage_key: str, user_id: str) -> None:
    """Best-effort removal of the stored upload."""
    if not storage_key or "/" in storage_key or "\\" in storage_key:
        return
    directory = resolve_storage_dir()
    path = directory / storage_key
    # Only ever delete a file that belongs to this user.
    if path.parent == directory and storage_key.startswith(f"{user_id}_"):
        path.unlink(missing_ok=True)
