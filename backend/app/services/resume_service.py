"""Resume use-cases: file validation, parsing, AI extraction and persistence."""

import logging
import uuid
from pathlib import Path

from fastapi.concurrency import run_in_threadpool
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import resolve_storage_dir
from app.core.exceptions import BadRequestError, NotFoundError, ServiceUnavailableError
from app.models.resume import Resume
from app.prompts.templates import EXTRACT_RESUME_INFO_PROMPT, MAX_PROMPT_CHARS
from app.repositories.resume_repository import ResumeRepository
from app.schemas.resume import ResumeStructuredData, ResumeSummary, ResumeUploadResponse
from app.services.llm_service import llm_service
from app.services.parsers import parse_docx, parse_pdf

logger = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF-"
DOCX_MAGIC = b"PK\x03\x04"
SUPPORTED_EXTENSIONS = {".pdf": PDF_MAGIC, ".docx": DOCX_MAGIC}
SKILLS_IN_SUMMARY = 8


def _extension_for(filename: str | None) -> str:
    if not filename:
        raise BadRequestError("A file name is required.")
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise BadRequestError("Only PDF and DOCX files are supported.")
    return extension


def _assert_magic_bytes(data: bytes, extension: str) -> None:
    if not data.startswith(SUPPORTED_EXTENSIONS[extension]):
        raise BadRequestError("The file content does not match its extension.")


async def _extract_text(extension: str, file_bytes: bytes) -> str:
    """Parse the upload (blocking work runs in the thread pool)."""
    parser = parse_pdf if extension == ".pdf" else parse_docx
    try:
        raw_text = await run_in_threadpool(parser, file_bytes)
    except Exception as exc:  # parser raises library-specific errors
        logger.warning("Failed to parse %s upload: %s", extension, exc)
        raise BadRequestError(
            "Failed to parse file: the document may be corrupt or password protected."
        ) from exc
    if not raw_text.strip():
        raise BadRequestError("Could not extract any text from the file.")
    return raw_text


def _store_file(data: bytes, user_id: str, extension: str) -> Path:
    directory = resolve_storage_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{user_id}_{uuid.uuid4().hex}{extension}"
    path.write_bytes(data)
    return path


def _remove_stored_file(storage_key: str, user_id: str) -> None:
    """Best-effort removal of a stored upload, only if it belongs to this user."""
    if not storage_key or "/" in storage_key or "\\" in storage_key:
        return
    directory = resolve_storage_dir()
    path = directory / storage_key
    if path.parent == directory and storage_key.startswith(f"{user_id}_"):
        path.unlink(missing_ok=True)


def _skills_summary(doc: dict) -> list[str]:
    skills = (doc.get("structured_data") or {}).get("skills")
    if not isinstance(skills, list):
        return []
    return [str(skill) for skill in skills][:SKILLS_IN_SUMMARY]


class ResumeService:
    def __init__(self, resumes: ResumeRepository) -> None:
        self._resumes = resumes

    async def upload(
        self,
        db: AsyncIOMotorDatabase,
        user_id: str,
        *,
        filename: str | None,
        file_bytes: bytes,
    ) -> ResumeUploadResponse:
        extension = _extension_for(filename)
        if not file_bytes:
            raise BadRequestError("The file is empty.")
        _assert_magic_bytes(file_bytes, extension)

        raw_text = await _extract_text(extension, file_bytes)
        structured_data = await self._extract_structured_data(raw_text)
        storage_path = await run_in_threadpool(_store_file, file_bytes, user_id, extension)

        resume = Resume(
            user_id=user_id,
            filename=filename,
            file_size=len(file_bytes),
            storage_key=storage_path.name,
            raw_text=raw_text,
            structured_data=structured_data.model_dump(),
        )
        try:
            resume.id = await self._resumes.insert(db, resume)
        except Exception:
            # Do not leave an orphaned file behind when persistence fails.
            storage_path.unlink(missing_ok=True)
            raise

        return ResumeUploadResponse(
            id=resume.id,
            filename=resume.filename,
            structured_data=structured_data,
        )

    async def list(self, db: AsyncIOMotorDatabase, user_id: str, limit: int) -> list[ResumeSummary]:
        docs = await self._resumes.list_for_user(db, user_id, limit)
        return [
            ResumeSummary(
                id=doc["_id"],
                filename=doc.get("filename", "resume"),
                file_size=doc.get("file_size", 0),
                skills=_skills_summary(doc),
                created_at=doc["created_at"],
            )
            for doc in docs
        ]

    async def get(self, db: AsyncIOMotorDatabase, user_id: str, resume_id: str) -> Resume:
        doc = await self._require(db, user_id, resume_id)
        return Resume(**doc)

    async def delete(self, db: AsyncIOMotorDatabase, user_id: str, resume_id: str) -> None:
        doc = await self._require(db, user_id, resume_id)
        await self._resumes.delete(db, resume_id, user_id)
        await run_in_threadpool(_remove_stored_file, doc.get("storage_key", ""), user_id)

    async def _extract_structured_data(self, raw_text: str) -> ResumeStructuredData:
        prompt = EXTRACT_RESUME_INFO_PROMPT.format(text=raw_text[:MAX_PROMPT_CHARS])
        try:
            return await llm_service.generate_structured(prompt, ResumeStructuredData)
        except Exception as exc:
            logger.error("Resume analysis failed: %s: %s", type(exc).__name__, exc)
            raise ServiceUnavailableError(
                "AI analysis of the resume is unavailable right now. Please try again later."
            ) from exc

    async def _require(self, db: AsyncIOMotorDatabase, user_id: str, resume_id: str) -> dict:
        doc = await self._resumes.find_owned(db, resume_id, user_id)
        if doc is None:
            raise NotFoundError("Resume not found")
        return doc
