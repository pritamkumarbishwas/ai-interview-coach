"""Resume use-cases: validation, durable storage, analysis and retrieval."""

import hashlib
import logging
from datetime import UTC, datetime
from pathlib import Path

from fastapi.concurrency import run_in_threadpool
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.core.config import resolve_storage_dir, settings
from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    NotFoundError,
)
from app.core.jobs import job_queue
from app.models.resume import Resume
from app.repositories.resume_repository import ResumeRepository, resume_repository
from app.schemas.resume import (
    ResumeStructuredData,
    ResumeSummary,
    ResumeTextResponse,
    ResumeUploadResponse,
)
from app.services.parsers import parse_docx, parse_pdf
from app.services.resume_processing import (
    ANALYSIS_VERSION,
    RESUME_PROCESS_JOB,
    ResumeProcessingError,
    resume_processing_service,
    validate_document,
)
from app.services.resume_storage import ResumeStorage, resume_storage

logger = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF-"
DOCX_MAGIC = b"PK\x03\x04"
SUPPORTED_EXTENSIONS = {".pdf": PDF_MAGIC, ".docx": DOCX_MAGIC}
SUPPORTED_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
SKILLS_IN_SUMMARY = 8
TERMINAL_STATUSES = {"ready", "partial", "failed"}


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
    """Compatibility helper retained for callers that only need plain text."""
    parser = parse_pdf if extension == ".pdf" else parse_docx
    try:
        raw_text = await run_in_threadpool(parser, file_bytes)
    except Exception as exc:
        logger.warning("Failed to parse %s upload: %s", extension, exc)
        raise BadRequestError(
            "Failed to parse file: the document may be corrupt or password protected."
        ) from exc
    if not raw_text.strip():
        raise BadRequestError("Could not extract any text from the file.")
    return raw_text


def _remove_stored_file(storage_key: str, user_id: str) -> None:
    """Best-effort removal of a legacy local upload, only if it belongs to this user."""
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


def _analysis_status(doc: dict) -> str:
    status = (doc.get("analysis") or {}).get("status")
    if status:
        return str(status)
    # Documents created before analysis status existed have already been
    # extracted synchronously.
    return "ready" if doc.get("structured_data") else "failed"


class ResumeService:
    def __init__(
        self,
        resumes: ResumeRepository,
        storage: ResumeStorage | None = None,
    ) -> None:
        self._resumes = resumes
        self._storage = storage or resume_storage

    async def upload(
        self,
        db: AsyncIOMotorDatabase,
        user_id: str,
        *,
        filename: str | None,
        file_bytes: bytes,
        content_type: str | None = None,
    ) -> ResumeUploadResponse:
        extension = _extension_for(filename)
        display_name = Path(filename or "resume").name
        if not file_bytes:
            raise BadRequestError("The file is empty.")
        _assert_magic_bytes(file_bytes, extension)
        try:
            await run_in_threadpool(validate_document, display_name, file_bytes)
        except ResumeProcessingError as exc:
            raise BadRequestError(exc.message) from exc

        sha256 = hashlib.sha256(file_bytes).hexdigest()
        existing = await self._resumes.find_by_sha(db, user_id, sha256)
        if existing is not None:
            return await self._handle_duplicate(db, user_id, existing)

        mime_type = SUPPORTED_MIME_TYPES[extension]
        if content_type and content_type.split(";", 1)[0] == mime_type:
            mime_type = content_type
        resume = Resume(
            user_id=user_id,
            filename=display_name,
            mime_type=mime_type,
            file_size=len(file_bytes),
            sha256=sha256,
            storage_backend="gridfs",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        try:
            resume_id = await self._resumes.insert(db, resume)
        except DuplicateKeyError:
            # Another concurrent request stored the same content first.
            existing = await self._resumes.find_by_sha(db, user_id, sha256)
            if existing is None:
                raise
            return await self._handle_duplicate(db, user_id, existing)

        file_id = ""
        try:
            file_id = await self._storage.put_original(
                db,
                resume_id=resume_id,
                user_id=user_id,
                filename=display_name,
                data=file_bytes,
                sha256=sha256,
                content_type=mime_type,
            )
            await self._resumes.update_fields(
                db,
                resume_id,
                user_id,
                {
                    "original_file_id": file_id,
                    "analysis.status": "pending",
                    "updated_at": datetime.now(UTC),
                },
            )
        except Exception:
            if file_id:
                await self._storage.delete_original(db, file_id)
            await self._resumes.delete(db, resume_id, user_id)
            raise

        await self._process_or_enqueue(db, resume_id, user_id)
        doc = await self._resumes.find_owned(db, resume_id, user_id)
        if doc is None:
            raise NotFoundError("Resume not found")
        return self._upload_response(doc)

    async def _handle_duplicate(
        self, db: AsyncIOMotorDatabase, user_id: str, doc: dict
    ) -> ResumeUploadResponse:
        status = _analysis_status(doc)
        resume_id = str(doc["_id"])
        stored_version = str((doc.get("analysis") or {}).get("version") or "")
        outdated = status == "ready" and stored_version != ANALYSIS_VERSION
        if status in {"pending", "partial", "failed"} or outdated:
            if status == "pending":
                await self._process_or_enqueue(db, resume_id, user_id)
            else:
                # Re-uploading is the user's natural way to retry; never hand
                # back stale or outdated analysis for the same file.
                await self.retry_analysis(db, user_id, resume_id)
            refreshed = await self._resumes.find_owned(db, resume_id, user_id)
            if refreshed is not None:
                doc = refreshed
        return self._upload_response(doc, deduplicated=True)

    async def _process_or_enqueue(
        self, db: AsyncIOMotorDatabase, resume_id: str, user_id: str
    ) -> None:
        if settings.resume_processing_inline:
            await resume_processing_service.process(db, resume_id, user_id)
            return
        try:
            await job_queue.enqueue(
                db,
                RESUME_PROCESS_JOB,
                {"resume_id": resume_id, "user_id": user_id},
                max_attempts=3,
            )
        except Exception:
            # Never strand a stored resume because the queue is unavailable.
            logger.exception("Could not enqueue resume processing; running inline")
            await resume_processing_service.process(db, resume_id, user_id)

    def _upload_response(
        self, doc: dict, *, deduplicated: bool = False
    ) -> ResumeUploadResponse:
        structured = ResumeStructuredData.model_validate(
            doc.get("structured_data") or {}
        )
        return ResumeUploadResponse(
            id=str(doc["_id"]),
            filename=str(doc.get("filename", "resume")),
            structured_data=structured,
            analysis_status=_analysis_status(doc),
            page_count=int(doc.get("page_count") or 0),
            ocr_used=bool(doc.get("ocr_pages")),
            deduplicated=deduplicated,
        )

    async def list(
        self, db: AsyncIOMotorDatabase, user_id: str, limit: int
    ) -> list[ResumeSummary]:
        docs = await self._resumes.list_for_user(db, user_id, limit)
        return [
            ResumeSummary(
                id=doc["_id"],
                filename=doc.get("filename", "resume"),
                file_size=doc.get("file_size", 0),
                mime_type=doc.get("mime_type", ""),
                skills=_skills_summary(doc),
                analysis_status=_analysis_status(doc),
                page_count=int(doc.get("page_count") or 0),
                has_preview=bool(doc.get("previews")),
                ocr_used=bool(doc.get("ocr_pages")),
                created_at=doc["created_at"],
            )
            for doc in docs
        ]

    async def get(
        self, db: AsyncIOMotorDatabase, user_id: str, resume_id: str
    ) -> Resume:
        doc = await self._require(db, user_id, resume_id)
        resume = Resume(**doc)
        # Normalize legacy four-section documents so the API always returns the
        # complete shape (contact, summary, additional_sections, ...).
        resume.structured_data = ResumeStructuredData.model_validate(
            doc.get("structured_data") or {}
        ).model_dump()
        return resume

    async def get_text(
        self, db: AsyncIOMotorDatabase, user_id: str, resume_id: str
    ) -> ResumeTextResponse:
        doc = await self._require(db, user_id, resume_id)
        text = await resume_processing_service.load_full_text(db, doc)
        return ResumeTextResponse(
            id=str(doc["_id"]),
            text=text,
            page_count=int(doc.get("page_count") or 0),
            ocr_pages=[int(page) for page in doc.get("ocr_pages") or []],
        )

    async def get_original(
        self, db: AsyncIOMotorDatabase, user_id: str, resume_id: str
    ) -> tuple[bytes, str, str]:
        doc = await self._require(db, user_id, resume_id)
        data = await self._storage.get_original(
            db, str(doc.get("original_file_id") or "")
        )
        if data is None:
            # Legacy local-disk fallback.
            storage_key = str(doc.get("storage_key") or "")
            if storage_key and "/" not in storage_key and "\\" not in storage_key:
                path = resolve_storage_dir() / storage_key
                if path.exists():
                    data = await run_in_threadpool(path.read_bytes)
        if data is None:
            raise NotFoundError("Stored resume file not found")
        return data, str(doc.get("filename") or "resume"), str(
            doc.get("mime_type") or "application/octet-stream"
        )

    async def get_preview(
        self, db: AsyncIOMotorDatabase, user_id: str, resume_id: str, page: int
    ) -> bytes:
        doc = await self._require(db, user_id, resume_id)
        preview = next(
            (
                item
                for item in doc.get("previews") or []
                if int(item.get("page", 0)) == page
            ),
            None,
        )
        if preview is None:
            raise NotFoundError("Preview not found")
        data = await self._storage.get_preview(db, str(preview.get("file_id") or ""))
        if data is None:
            raise NotFoundError("Preview not found")
        return data

    async def retry_analysis(
        self, db: AsyncIOMotorDatabase, user_id: str, resume_id: str
    ) -> str:
        doc = await self._require(db, user_id, resume_id)
        status = _analysis_status(doc)
        if status in {"pending", "processing"}:
            raise ConflictError("Resume analysis is already running")
        if status == "deleting":
            raise NotFoundError("Resume not found")
        await self._resumes.update_fields(
            db,
            resume_id,
            user_id,
            {
                "analysis.status": "pending",
                "analysis.error_code": "",
                "analysis.error_message": "",
                "updated_at": datetime.now(UTC),
            },
        )
        await self._process_or_enqueue(db, resume_id, user_id)
        refreshed = await self._resumes.find_owned(db, resume_id, user_id)
        return _analysis_status(refreshed or doc)

    async def delete(
        self, db: AsyncIOMotorDatabase, user_id: str, resume_id: str
    ) -> None:
        doc = await self._require(db, user_id, resume_id)
        active = await db.interviews.count_documents(
            {
                "user_id": user_id,
                "resume_id": resume_id,
                "status": {"$in": ["created", "in_progress"]},
            }
        )
        if active:
            raise ConflictError(
                "This resume is used by an active interview. Finish or abandon "
                "that interview before deleting it."
            )
        await self._resumes.update_fields(
            db,
            resume_id,
            user_id,
            {"analysis.status": "deleting", "deleted_at": datetime.now(UTC)},
        )
        file_ids = [doc.get("original_file_id"), doc.get("content_file_id")]
        file_ids.extend(
            item.get("file_id") for item in (doc.get("previews") or [])
        )
        for file_id in file_ids:
            if not file_id:
                continue
            try:
                if file_id == doc.get("content_file_id"):
                    await self._storage.delete_original(db, str(file_id))
                elif file_id == doc.get("original_file_id"):
                    await self._storage.delete_original(db, str(file_id))
                else:
                    await self._storage.delete_preview(db, str(file_id))
            except Exception:
                logger.warning("Could not remove resume asset %s", file_id)
        legacy_key = str(doc.get("storage_key") or "")
        if legacy_key:
            await run_in_threadpool(_remove_stored_file, legacy_key, user_id)
        await self._resumes.delete(db, resume_id, user_id)

    async def _require(
        self, db: AsyncIOMotorDatabase, user_id: str, resume_id: str
    ) -> dict:
        doc = await self._resumes.find_owned(db, resume_id, user_id)
        if doc is None:
            raise NotFoundError("Resume not found")
        return doc


resume_service = ResumeService(resume_repository, resume_storage)
