"""Resume ingestion: complete content extraction, OCR, previews and LLM analysis.

The original upload is never modified. Everything in this module is a derived
artifact that can be regenerated from the original file. A failure in OCR or
the LLM records a failed/partial analysis state but does not discard the
resume.
"""

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.concurrency import run_in_threadpool
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import resolve_storage_dir, settings
from app.models.resume import ResumePreview
from app.prompts.templates import EXTRACT_RESUME_INFO_PROMPT
from app.repositories.resume_repository import ResumeRepository, resume_repository
from app.schemas.resume import ContactInfo, ContactLink, ResumeStructuredData
from app.services.llm_service import llm_service
from app.services.parsers import (
    clean_text,
    parse_docx_blocks,
    parse_pdf_pages,
    validate_docx,
    validate_pdf,
)
from app.services.resume_storage import ResumeStorage, resume_storage

logger = logging.getLogger(__name__)

ANALYSIS_VERSION = "resume-v2"
RESUME_PROCESS_JOB = "resume.process"
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(
    r"(?<!\d)(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-])\d{3,4}[\s.-]\d{4}(?!\d)"
)
URL_RE = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)


class ResumeProcessingError(Exception):
    """A safe-to-report processing failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def validate_document(filename: str, data: bytes) -> None:
    """Open the upload once so corrupt or encrypted files fail before storage."""
    extension = Path(filename).suffix.lower()
    try:
        if extension == ".pdf":
            validate_pdf(data)
        elif extension == ".docx":
            validate_docx(data)
        else:
            raise ResumeProcessingError(
                "unsupported_type", "Only PDF and DOCX files are supported."
            )
    except ResumeProcessingError:
        raise
    except Exception as exc:
        raise ResumeProcessingError(
            "parse_failed",
            "Failed to parse file: the document may be corrupt or password protected.",
        ) from exc


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _ocr_available() -> bool:
    if not settings.resume_ocr_enabled:
        return False
    return shutil.which(settings.tesseract_cmd) is not None


def _run_tesseract(png: bytes) -> str:
    command = [
        settings.tesseract_cmd,
        "stdin",
        "stdout",
        "-l",
        settings.resume_ocr_languages,
        "--psm",
        "3",
    ]
    try:
        completed = subprocess.run(
            command,
            input=png,
            capture_output=True,
            timeout=settings.resume_ocr_timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ResumeProcessingError("ocr_failed", "OCR timed out or was unavailable.") from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", "ignore").strip()[:300]
        raise ResumeProcessingError("ocr_failed", f"OCR failed: {detail or 'unknown error'}")
    return completed.stdout.decode("utf-8", "ignore")


def _render_pdf_assets(
    file_bytes: bytes,
    ocr_pages: set[int],
    max_pages: int,
) -> tuple[list[dict[str, Any]], dict[int, bytes]]:
    """Render preview/OCR images in one blocking operation."""
    import fitz

    previews: list[dict[str, Any]] = []
    ocr_images: dict[int, bytes] = {}
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        if doc.needs_pass:
            raise ResumeProcessingError("parse_failed", "The PDF is password protected.")
        for index, page in enumerate(doc):
            if index >= max_pages:
                break
            number = index + 1
            if index < settings.resume_max_previews:
                try:
                    pix = page.get_pixmap(
                        dpi=settings.resume_preview_dpi,
                        colorspace=fitz.csRGB,
                        alpha=False,
                    )
                    previews.append(
                        {
                            "page": number,
                            "data": pix.tobytes("png"),
                            "width": pix.width,
                            "height": pix.height,
                            "dpi": settings.resume_preview_dpi,
                        }
                    )
                except Exception as exc:
                    logger.warning("Could not render resume page %s: %s", number, exc)
            if number in ocr_pages:
                try:
                    pix = page.get_pixmap(
                        dpi=settings.resume_ocr_dpi,
                        colorspace=fitz.csGRAY,
                        alpha=False,
                    )
                    ocr_images[number] = pix.tobytes("png")
                except Exception as exc:
                    logger.warning("Could not render OCR page %s: %s", number, exc)
    return previews, ocr_images


def _convert_docx_to_pdf(file_bytes: bytes) -> bytes | None:
    if not settings.resume_docx_preview_conversion:
        return None
    if shutil.which(settings.libreoffice_cmd) is None:
        return None
    with tempfile.TemporaryDirectory(prefix="resume-docx-") as directory:
        source = Path(directory) / "resume.docx"
        source.write_bytes(file_bytes)
        env = {"HOME": directory, "TMPDIR": directory}
        try:
            completed = subprocess.run(
                [
                    settings.libreoffice_cmd,
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    directory,
                    str(source),
                ],
                capture_output=True,
                timeout=120,
                check=False,
                env={**os.environ, **env},
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning("DOCX preview conversion failed: %s", exc)
            return None
        if completed.returncode != 0:
            logger.warning(
                "DOCX preview conversion returned %s: %s",
                completed.returncode,
                completed.stderr.decode("utf-8", "ignore")[:300],
            )
            return None
        output = Path(directory) / "resume.pdf"
        if not output.exists():
            return None
        return output.read_bytes()


def _extract_contact(text: str) -> ContactInfo:
    emails = [match.group(0) for match in EMAIL_RE.finditer(text)]
    phones = [match.group(0).strip() for match in PHONE_RE.finditer(text)]
    links: list[ContactLink] = []
    seen: set[str] = set()
    for match in URL_RE.finditer(text):
        url = match.group(0).rstrip(".,;:)]}")
        if url not in seen:
            seen.add(url)
            links.append(ContactLink(url=url))
    return ContactInfo(
        email=emails[0] if emails else "",
        phone=phones[0] if phones else "",
        links=links[:12],
    )


def _redact_contact_pii(text: str) -> str:
    text = EMAIL_RE.sub("[email redacted]", text)
    text = PHONE_RE.sub("[phone redacted]", text)
    return text


def _chunk_text(text: str) -> list[str]:
    if len(text) <= settings.resume_extraction_chunk_chars:
        return [text] if text.strip() else []
    chunks: list[str] = []
    start = 0
    limit = settings.resume_extraction_chunk_chars
    while start < len(text) and len(chunks) < settings.resume_max_extraction_chunks:
        end = min(len(text), start + limit)
        if end < len(text):
            newline = text.rfind("\n", start + limit // 2, end)
            if newline > start:
                end = newline
        chunks.append(text[start:end])
        start = end
    return chunks


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = str(value).strip()
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result


def _merge_list_values(values: list[Any]) -> list[Any]:
    """De-duplicate a list while preserving dict entries such as links."""
    seen: set[str] = set()
    result: list[Any] = []
    for value in values:
        if isinstance(value, str):
            key = f"str:{value.strip().casefold()}"
        else:
            key = f"json:{json.dumps(value, sort_keys=True, default=str)}"
        if key in seen:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        seen.add(key)
        result.append(value)
    return result


def _merge_objects(
    items: list[dict[str, Any]],
    key_fields: tuple[str, ...],
) -> list[dict[str, Any]]:
    merged: dict[tuple[str, ...], dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        key = tuple(str(item.get(field, "")).strip().casefold() for field in key_fields)
        if not any(key):
            key = (json.dumps(item, sort_keys=True, default=str)[:200],)
        if key not in merged:
            merged[key] = dict(item)
            continue
        current = merged[key]
        for field, value in item.items():
            if isinstance(value, list) and isinstance(current.get(field), list):
                current[field] = _merge_list_values(current[field] + value)
            elif field == "content" and isinstance(value, str) and value:
                existing = str(current.get(field) or "").strip()
                if value.strip() and value.strip() not in existing:
                    current[field] = "\n".join(
                        part for part in (existing, value.strip()) if part
                    )
            elif not current.get(field) and value:
                current[field] = value
    return list(merged.values())


def _merge_structured(
    results: list[ResumeStructuredData], contact: ContactInfo
) -> ResumeStructuredData:
    merged: dict[str, Any] = {
        "version": 2,
        "contact": contact.model_dump(),
        "summary": "",
        "skills": [],
        "experience": [],
        "projects": [],
        "education": [],
        "certifications": [],
        "awards": [],
        "publications": [],
        "languages": [],
        "volunteer": [],
        "interests": [],
        "additional_sections": [],
    }
    for result in results:
        data = result.model_dump()
        if data.get("summary") and not merged["summary"]:
            merged["summary"] = data["summary"]
        for field in ("skills", "interests"):
            merged[field].extend(str(v) for v in data.get(field, []))
        for field in (
            "experience",
            "projects",
            "education",
            "certifications",
            "awards",
            "publications",
            "languages",
            "volunteer",
        ):
            merged[field].extend(data.get(field, []))
        merged["additional_sections"].extend(data.get("additional_sections", []))

    for field in ("skills", "interests"):
        merged[field] = _dedupe_strings(merged[field])
    for field, key_fields in (
        ("experience", ("company", "role", "duration")),
        ("projects", ("name",)),
        ("education", ("institution", "degree")),
        ("certifications", ("name", "issuer")),
        ("awards", ("title", "issuer")),
        ("publications", ("title",)),
        ("languages", ("language",)),
        ("volunteer", ("company", "role", "duration")),
    ):
        merged[field] = _merge_objects(merged[field], key_fields)
    merged["additional_sections"] = _merge_objects(
        merged["additional_sections"], ("heading",)
    )
    # Keep deterministic contact details even when the LLM was given redacted
    # text and could not see them.
    merged["contact"] = {
        **merged["contact"],
        **{k: v for k, v in contact.model_dump().items() if v},
    }
    return ResumeStructuredData.model_validate(merged)


def _analysis_fields(
    status: str,
    *,
    warnings: list[str] | None = None,
    failed_chunks: int = 0,
    error_code: str = "",
    error_message: str = "",
    started_at: datetime | None = None,
) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "analysis.status": status,
        "analysis.version": ANALYSIS_VERSION,
        "analysis.warnings": warnings or [],
        "analysis.failed_chunks": failed_chunks,
        "analysis.error_code": error_code,
        "analysis.error_message": error_message,
        "updated_at": datetime.now(UTC),
    }
    if started_at is not None:
        fields["analysis.started_at"] = started_at
    if status in {"ready", "partial", "failed"}:
        fields["analysis.completed_at"] = datetime.now(UTC)
    return fields


class ResumeProcessingService:
    def __init__(
        self,
        resumes: ResumeRepository,
        storage: ResumeStorage,
    ) -> None:
        self._resumes = resumes
        self._storage = storage

    async def process(
        self,
        db: AsyncIOMotorDatabase,
        resume_id: str,
        user_id: str,
    ) -> None:
        doc = await self._resumes.find_owned(db, resume_id, user_id)
        if doc is None:
            return
        if (doc.get("analysis") or {}).get("status") == "deleting":
            return
        started_at = datetime.now(UTC)
        await self._resumes.update_fields(
            db,
            resume_id,
            user_id,
            _analysis_fields(
                "processing",
                warnings=[],
                started_at=started_at,
                error_code="",
                error_message="",
            ),
        )
        try:
            original = await self._load_original(db, doc)
            if original is None:
                raise ResumeProcessingError(
                    "missing_file", "The stored resume file could not be found."
                )
            warnings: list[str] = []
            pages, raw_text, ocr_pages, has_text_layer = await self._extract_content(
                db, doc, original, warnings
            )
            await self._persist_content(
                db,
                doc,
                pages=pages,
                raw_text=raw_text,
                ocr_pages=ocr_pages,
                has_text_layer=has_text_layer,
                warnings=warnings,
            )
            structured, failed_chunks = await self._extract_structured(raw_text)
            status = "partial" if failed_chunks else "ready"
            chunk_budget = (
                settings.resume_extraction_chunk_chars
                * settings.resume_max_extraction_chunks
            )
            if len(raw_text) > chunk_budget:
                warnings.append(
                    "Structured extraction covers the first "
                    f"{chunk_budget:,} characters; the full text is still stored."
                )
            if not raw_text.strip():
                warnings.append("No readable text was extracted from this resume.")
                status = "partial"
            await self._resumes.update_fields(
                db,
                resume_id,
                user_id,
                {
                    "structured_data": structured.model_dump(),
                    **_analysis_fields(
                        status,
                        warnings=warnings,
                        failed_chunks=failed_chunks,
                        started_at=started_at,
                    ),
                },
            )
        except ResumeProcessingError as exc:
            logger.warning("Resume processing failed (%s): %s", resume_id, exc.message)
            await self._resumes.update_fields(
                db,
                resume_id,
                user_id,
                _analysis_fields(
                    "failed",
                    warnings=[],
                    error_code=exc.code,
                    error_message=exc.message,
                    started_at=started_at,
                ),
            )
        except Exception as exc:
            logger.exception("Unexpected resume processing failure (%s)", resume_id)
            await self._resumes.update_fields(
                db,
                resume_id,
                user_id,
                _analysis_fields(
                    "failed",
                    warnings=[],
                    error_code="processing_failed",
                    error_message="Resume processing failed. You can retry analysis.",
                    started_at=started_at,
                ),
            )
            logger.debug("Resume processing exception detail", exc_info=exc)

    async def _load_original(
        self, db: AsyncIOMotorDatabase, doc: dict
    ) -> bytes | None:
        file_id = str(doc.get("original_file_id") or "")
        if file_id:
            return await self._storage.get_original(db, file_id)
        # Legacy document from the local-disk storage era.
        storage_key = str(doc.get("storage_key") or "")
        if storage_key and "/" not in storage_key and "\\" not in storage_key:
            path = resolve_storage_dir() / storage_key
            if path.exists():
                return await run_in_threadpool(path.read_bytes)
        return None

    async def _extract_content(
        self,
        db: AsyncIOMotorDatabase,
        doc: dict,
        original: bytes,
        warnings: list[str],
    ) -> tuple[list[dict[str, Any]], str, list[int], bool]:
        filename = str(doc.get("filename") or "")
        extension = Path(filename).suffix.lower()
        if extension == ".pdf":
            return await self._extract_pdf_content(db, doc, original, warnings)
        if extension == ".docx":
            return await self._extract_docx_content(db, doc, original, warnings)
        raise ResumeProcessingError("unsupported_type", "Only PDF and DOCX files are supported.")

    async def _extract_pdf_content(
        self,
        db: AsyncIOMotorDatabase,
        doc: dict,
        original: bytes,
        warnings: list[str],
    ) -> tuple[list[dict[str, Any]], str, list[int], bool]:
        pages = await run_in_threadpool(parse_pdf_pages, original)
        if len(pages) > settings.resume_max_pages:
            pages = pages[: settings.resume_max_pages]
            warnings.append(
                f"Content extraction is limited to {settings.resume_max_pages} pages."
            )
        ocr_numbers = {
            page["number"]
            for page in pages
            if len(str(page.get("text", "")).strip()) < settings.resume_ocr_min_chars
        }
        previews, ocr_images = await run_in_threadpool(
            _render_pdf_assets, original, ocr_numbers, settings.resume_max_pages
        )
        if len(pages) > settings.resume_max_previews:
            warnings.append(
                f"Preview generation is limited to {settings.resume_max_previews} pages."
            )
        ocr_pages: list[int] = []
        if ocr_numbers and not _ocr_available():
            warnings.append("OCR is not installed; image-only pages were kept as previews.")
        else:
            for number in sorted(ocr_numbers):
                png = ocr_images.get(number)
                if png is None:
                    continue
                try:
                    text = clean_text(await run_in_threadpool(_run_tesseract, png))
                except ResumeProcessingError as exc:
                    warnings.append(exc.message)
                    continue
                if text:
                    page = pages[number - 1]
                    page["text"] = text
                    page["method"] = "ocr"
                    page["ocr"] = True
                    ocr_pages.append(number)
        full_text = clean_text("\n\n".join(str(page["text"]) for page in pages))
        has_text_layer = any(page.get("method") == "text_layer" for page in pages)
        await self._replace_previews(db, doc, previews)
        return pages, full_text, ocr_pages, has_text_layer

    async def _extract_docx_content(
        self,
        db: AsyncIOMotorDatabase,
        doc: dict,
        original: bytes,
        warnings: list[str],
    ) -> tuple[list[dict[str, Any]], str, list[int], bool]:
        blocks = await run_in_threadpool(parse_docx_blocks, original)
        native_text = clean_text("\n".join(block["text"] for block in blocks))
        pdf_bytes = await run_in_threadpool(_convert_docx_to_pdf, original)
        if pdf_bytes is None:
            warnings.append(
                "DOCX page previews are unavailable (LibreOffice is not installed)."
            )
            pages = [
                {
                    "number": 1,
                    "text": native_text,
                    "blocks": [block["text"] for block in blocks],
                    "method": "docx" if native_text else "none",
                }
            ]
            full_text = native_text
            return pages, full_text, [], bool(native_text)

        pages = await run_in_threadpool(parse_pdf_pages, pdf_bytes)
        if len(pages) > settings.resume_max_pages:
            pages = pages[: settings.resume_max_pages]
            warnings.append(
                f"Content extraction is limited to {settings.resume_max_pages} pages."
            )
        ocr_numbers = {
            page["number"]
            for page in pages
            if len(str(page.get("text", "")).strip()) < settings.resume_ocr_min_chars
        }
        previews, ocr_images = await run_in_threadpool(
            _render_pdf_assets, pdf_bytes, ocr_numbers, settings.resume_max_pages
        )
        ocr_pages: list[int] = []
        if ocr_numbers and not _ocr_available():
            warnings.append("OCR is not installed; image-only DOCX pages were kept as previews.")
        else:
            for number in sorted(ocr_numbers):
                png = ocr_images.get(number)
                if png is None:
                    continue
                try:
                    text = clean_text(await run_in_threadpool(_run_tesseract, png))
                except ResumeProcessingError as exc:
                    warnings.append(exc.message)
                    continue
                if text:
                    page = pages[number - 1]
                    page["text"] = text
                    page["method"] = "ocr"
                    page["ocr"] = True
                    ocr_pages.append(number)
        await self._replace_previews(db, doc, previews)
        # Native DOCX text is authoritative; PDF text fills image-only gaps.
        full_text = clean_text(
            "\n\n".join(str(page["text"]) for page in pages)
        ) or native_text
        if native_text and len(native_text) > len(full_text):
            pages[0]["text"] = native_text
            pages[0]["method"] = "docx"
            full_text = native_text
        return pages, full_text, ocr_pages, bool(native_text)

    async def _replace_previews(
        self,
        db: AsyncIOMotorDatabase,
        doc: dict,
        previews: list[dict[str, Any]],
    ) -> None:
        resume_id = str(doc.get("_id") or "")
        user_id = str(doc.get("user_id") or "")
        old = [ResumePreview.model_validate(item) for item in doc.get("previews", [])]
        new_models: list[ResumePreview] = []
        for preview in previews:
            file_id = await self._storage.put_preview(
                db,
                resume_id=resume_id,
                user_id=user_id,
                page=int(preview["page"]),
                data=preview["data"],
                width=int(preview["width"]),
                height=int(preview["height"]),
                dpi=int(preview["dpi"]),
            )
            new_models.append(
                ResumePreview(
                    page=int(preview["page"]),
                    file_id=file_id,
                    width=int(preview["width"]),
                    height=int(preview["height"]),
                    dpi=int(preview["dpi"]),
                )
            )
        await self._resumes.update_fields(
            db,
            resume_id,
            user_id,
            {"previews": [item.model_dump() for item in new_models]},
        )
        for item in old:
            await self._storage.delete_preview(db, item.file_id)

    async def _persist_content(
        self,
        db: AsyncIOMotorDatabase,
        doc: dict,
        *,
        pages: list[dict[str, Any]],
        raw_text: str,
        ocr_pages: list[int],
        has_text_layer: bool,
        warnings: list[str],
    ) -> None:
        resume_id = str(doc.get("_id") or "")
        user_id = str(doc.get("user_id") or "")
        text_sha = _sha256(raw_text.encode())
        content = {
            "version": 2,
            "raw_text": raw_text,
            "text_sha256": text_sha,
            "pages": pages,
            "ocr_pages": ocr_pages,
            "warnings": warnings,
            "parser_version": ANALYSIS_VERSION,
        }
        content_file_id = await self._storage.put_content(
            db,
            resume_id=resume_id,
            user_id=user_id,
            content=content,
            sha256=text_sha,
        )
        old_content_id = str(doc.get("content_file_id") or "")
        await self._resumes.update_fields(
            db,
            resume_id,
            user_id,
            {
                "content_file_id": content_file_id,
                "raw_text": raw_text[: settings.resume_max_inline_text_chars],
                "text_sha256": text_sha,
                "page_count": len(pages),
                "ocr_pages": ocr_pages,
                "has_text_layer": has_text_layer,
                "updated_at": datetime.now(UTC),
            },
        )
        if old_content_id and old_content_id != content_file_id:
            await self._storage.delete_original(db, old_content_id)

    async def _extract_structured(
        self, raw_text: str
    ) -> tuple[ResumeStructuredData, int]:
        contact = _extract_contact(raw_text)
        chunks = _chunk_text(_redact_contact_pii(raw_text))
        if not chunks:
            return ResumeStructuredData(contact=contact), 0
        results: list[ResumeStructuredData] = []
        failed = 0
        for chunk in chunks:
            prompt = EXTRACT_RESUME_INFO_PROMPT.replace("{text}", chunk)
            try:
                results.append(
                    await llm_service.generate_structured(
                        prompt, ResumeStructuredData, max_retries=2
                    )
                )
            except Exception as exc:
                failed += 1
                logger.warning(
                    "Resume extraction chunk failed (%s: %s)",
                    type(exc).__name__,
                    str(exc)[:200],
                )
        if not results:
            raise ResumeProcessingError(
                "llm_failed",
                "AI analysis is unavailable right now. You can retry it later.",
            )
        return _merge_structured(results, contact), failed

    async def load_full_text(
        self, db: AsyncIOMotorDatabase, doc: dict
    ) -> str:
        content = await self._storage.get_content(
            db, str(doc.get("content_file_id") or "")
        )
        if content and isinstance(content.get("raw_text"), str):
            return content["raw_text"]
        return str(doc.get("raw_text") or "")


resume_processing_service = ResumeProcessingService(
    resume_repository, resume_storage
)
