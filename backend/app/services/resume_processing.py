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
from app.prompts.templates import (
    EXTRACT_RESUME_INFO_PROMPT,
    EXTRACT_RESUME_SYSTEM_PROMPT,
)
from app.repositories.resume_repository import ResumeRepository, resume_repository
from app.schemas.resume import ContactInfo, ContactLink, ResumeStructuredData
from app.services.llm_service import is_incomplete_output, llm_service
from app.services.parsers import (
    clean_text,
    parse_docx_blocks,
    parse_docx_links,
    parse_pdf_pages,
    validate_docx,
    validate_pdf,
)
from app.services.resume_storage import ResumeStorage, resume_storage

logger = logging.getLogger(__name__)

ANALYSIS_VERSION = "resume-v4"
RESUME_PROCESS_JOB = "resume.process"
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<![\w])\+?\(?\d(?:[ \t().-]*\d){7,14}(?![\w])")
URL_RE = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
CHUNK_OVERLAP_CHARS = 400
MIN_SPLIT_RETRY_CHARS = 1_600
MAX_COMPLETION_TOKENS = 4_096
EXTRACTION_REASONING_EFFORT = "low"

_SECTION_ALIASES = {
    "professional summary": "Summary",
    "summary": "Summary",
    "profile": "Summary",
    "professional profile": "Summary",
    "objective": "Summary",
    "career objective": "Summary",
    "about me": "Summary",
    "technical skills": "Skills",
    "skills": "Skills",
    "core skills": "Skills",
    "core competencies": "Skills",
    "technical expertise": "Skills",
    "technologies": "Skills",
    "experience": "Experience",
    "work experience": "Experience",
    "professional experience": "Experience",
    "employment history": "Experience",
    "work history": "Experience",
    "career history": "Experience",
    "projects": "Projects",
    "personal projects": "Projects",
    "academic projects": "Projects",
    "key projects": "Projects",
    "selected projects": "Projects",
    "project experience": "Projects",
    "education": "Education",
    "academic background": "Education",
    "academics": "Education",
    "education & training": "Education",
    "education and training": "Education",
    "certifications": "Certifications",
    "certificates": "Certifications",
    "professional certifications": "Certifications",
    "licenses & certifications": "Certifications",
    "licenses and certifications": "Certifications",
    "certifications & licenses": "Certifications",
    "awards": "Awards",
    "honors": "Awards",
    "honours": "Awards",
    "honors & awards": "Awards",
    "awards & honors": "Awards",
    "achievements": "Achievements",
    "accomplishments": "Achievements",
    "key achievements": "Achievements",
    "coding profiles": "Achievements",
    "publications": "Publications",
    "papers": "Publications",
    "languages": "Languages",
    "volunteer": "Volunteer",
    "volunteering": "Volunteer",
    "volunteer experience": "Volunteer",
    "community involvement": "Volunteer",
    "interests": "Interests",
    "hobbies": "Interests",
}

_ADDITIONAL_SECTION_FIELDS = {
    "header": "contact",
    "contact": "contact",
    "contact information": "contact",
    "personal information": "contact",
    "summary": "summary",
    "professional summary": "summary",
    "technical skills": "skills",
    "skills": "skills",
    "core competencies": "skills",
    "experience": "experience",
    "work experience": "experience",
    "professional experience": "experience",
    "projects": "projects",
    "personal projects": "projects",
    "education": "education",
    "certifications": "certifications",
    "certificates": "certifications",
    "awards": "awards",
    "achievements": "achievements",
    "publications": "publications",
    "languages": "languages",
    "volunteer": "volunteer",
    "interests": "interests",
}


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


def _valid_phone(value: str) -> bool:
    digits = re.sub(r"\D", "", value)
    return 10 <= len(digits) <= 15


def _extract_contact(
    text: str, document_links: list[dict[str, Any]] | None = None
) -> ContactInfo:
    emails = [match.group(0) for match in EMAIL_RE.finditer(text)]
    phones = [
        match.group(0).strip(" .-")
        for match in PHONE_RE.finditer(text)
        if _valid_phone(match.group(0))
    ]
    links: list[ContactLink] = []
    seen: set[str] = set()

    def add_link(label: object, url: object) -> None:
        link = ContactLink(label=str(label or ""), url=str(url or ""))
        key = link.url.rstrip("/").casefold()
        if link.url and key not in seen:
            seen.add(key)
            links.append(link)

    # Contact links usually sit in the first page header. Project links are
    # preserved separately for the extraction prompt instead of polluting the
    # candidate's contact block.
    for item in document_links or []:
        if item.get("page") == 1 and float(item.get("top") or 0) <= 260:
            add_link(item.get("label"), item.get("url"))
    for match in URL_RE.finditer(text[:2_000]):
        add_link("", match.group(0).rstrip(".,;:)]}"))
    return ContactInfo(
        email=emails[0] if emails else "",
        phone=phones[0] if phones else "",
        links=links[:12],
    )


def _document_links(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    seen: set[str] = set()
    for page in pages:
        for item in page.get("links", []):
            link = ContactLink(
                label=str(item.get("label") or ""), url=str(item.get("url") or "")
            )
            key = link.url.rstrip("/").casefold()
            if not link.url or key in seen:
                continue
            seen.add(key)
            links.append(
                {
                    "label": link.label,
                    "url": link.url,
                    "page": item.get("page"),
                    "top": item.get("top"),
                }
            )
    return links


def _attach_native_links(
    pages: list[dict[str, Any]], links: list[dict[str, str]]
) -> None:
    """Attach DOCX hyperlinks to the first page for prompt/LLM mapping."""
    if not pages or not links:
        return
    existing = {
        str(item.get("url") or "").rstrip("/").casefold()
        for item in pages[0].get("links", [])
    }
    page_links = pages[0].setdefault("links", [])
    for item in links:
        link = ContactLink(
            label=str(item.get("label") or ""), url=str(item.get("url") or "")
        )
        key = link.url.rstrip("/").casefold()
        if not link.url or key in existing:
            continue
        existing.add(key)
        page_links.append(
            {"label": link.label, "url": link.url, "page": 1, "top": 999}
        )


def _link_context(links: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for item in links[:40]:
        label = str(item.get("label") or "link").replace("\n", " ")[:120]
        page = item.get("page")
        suffix = f" (page {page})" if page else ""
        lines.append(f"- {label}: {item.get('url')}{suffix}")
    return "\n".join(lines) or "(no embedded document links)"


def _redact_contact_pii(text: str) -> str:
    text = EMAIL_RE.sub("[email redacted]", text)
    text = PHONE_RE.sub(
        lambda match: (
            "[phone redacted]" if _valid_phone(match.group(0)) else match.group(0)
        ),
        text,
    )
    return text


def _find_split(text: str, start: int, end: int) -> int:
    """Find a natural boundary near the end of a chunk."""
    # Prefer a boundary close to the limit; taking the first paragraph break
    # after the midpoint can produce tiny chunks and orphaned entry bodies.
    minimum = start + int((end - start) * 0.7)
    for separator in ("\n\n", "\n", ". ", " "):
        index = text.rfind(separator, minimum, end)
        if index > start:
            return index + len(separator)
    return end


def _chunk_text(text: str) -> list[str]:
    if len(text) <= settings.resume_extraction_chunk_chars:
        return [text] if text.strip() else []
    chunks: list[str] = []
    start = 0
    limit = settings.resume_extraction_chunk_chars
    while start < len(text) and len(chunks) < settings.resume_max_extraction_chunks:
        end = min(len(text), start + limit)
        if end < len(text):
            end = _find_split(text, start, end)
        chunks.append(text[start:end])
        if end >= len(text):
            break
        # Overlap keeps a heading and its body in the same later chunk when a
        # natural paragraph boundary still falls inside an entry.
        start = max(end - CHUNK_OVERLAP_CHARS, start + 1)
    return chunks


def _normalize_heading(line: str) -> str:
    cleaned = re.sub(
        r"^[\s\u2022\u00b7\u25aa\u25e6*\-\u2013\u2014]+", "", line.strip()
    )
    return re.sub(r"\s+", " ", cleaned).strip(" :.-").casefold()


def _section_segments(text: str) -> list[tuple[str, str]]:
    """Split text at recognized section headings without losing the preamble."""
    lines = text.splitlines(keepends=True)
    headings: list[tuple[int, str]] = []
    offset = 0
    for line in lines:
        label = _SECTION_ALIASES.get(_normalize_heading(line.rstrip("\r\n")))
        if label is not None:
            headings.append((offset, label))
        offset += len(line)
    if not headings:
        return [(text.strip(), "Resume")] if text.strip() else []

    segments: list[tuple[str, str]] = []
    if headings[0][0] > 0:
        preamble = text[: headings[0][0]].strip()
        if preamble:
            segments.append((preamble, "Header"))
    for index, (start, label) in enumerate(headings):
        end = headings[index + 1][0] if index + 1 < len(headings) else len(text)
        content = text[start:end].strip()
        if content:
            segments.append((content, label))
    return segments


def _chunk_resume(text: str) -> list[tuple[str, str]]:
    """Build chunks that preserve section headings and carry section context."""
    segments = _section_segments(text)
    limit = settings.resume_extraction_chunk_chars
    max_chunks = settings.resume_max_extraction_chunks
    chunks: list[tuple[str, str]] = []
    parts: list[str] = []
    labels: list[str] = []
    size = 0

    def flush() -> None:
        nonlocal parts, labels, size
        if parts:
            chunks.append(("\n\n".join(parts).strip(), ", ".join(dict.fromkeys(labels))))
            parts = []
            labels = []
            size = 0

    for segment, label in segments:
        if len(chunks) >= max_chunks:
            break
        if len(segment) > limit:
            flush()
            for part in _chunk_text(segment):
                if len(chunks) >= max_chunks:
                    break
                chunks.append((part, label))
            continue
        addition = len(segment) + (2 if parts else 0)
        if parts and size + addition > limit:
            flush()
        parts.append(segment)
        labels.append(label)
        size += addition
    flush()
    return chunks[:max_chunks]


def _split_chunk_for_retry(text: str) -> tuple[str, str] | None:
    """Split an oversized chunk after the provider truncates its JSON."""
    if len(text) < MIN_SPLIT_RETRY_CHARS:
        return None
    split = _find_split(text, int(len(text) * 0.3), int(len(text) * 0.7))
    if split <= 0 or split >= len(text):
        split = len(text) // 2
    left = text[:split].strip()
    # A little overlap keeps a project/experience heading with its bullets.
    right = text[max(0, split - CHUNK_OVERLAP_CHARS) :].strip()
    if not left or not right:
        return None
    return left, right


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


def _drop_project_like_experience(
    experience: list[dict[str, Any]], projects: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Remove project entries that a chunk without a Projects heading mislabelled."""
    project_names = {
        str(item.get("name") or "").strip().casefold()
        for item in projects
        if str(item.get("name") or "").strip()
    }
    if not project_names:
        return experience
    kept: list[dict[str, Any]] = []
    for item in experience:
        company = str(item.get("company") or "").strip().casefold()
        role = str(item.get("role") or "").strip().casefold()
        has_employment_meta = any(
            str(item.get(field) or "").strip()
            for field in ("duration", "start_date", "end_date", "location")
        )
        if not has_employment_meta and (company in project_names or role in project_names):
            logger.info(
                "Dropping project-like experience entry: company=%r role=%r",
                item.get("company"),
                item.get("role"),
            )
            continue
        kept.append(item)
    return kept


def _drop_redundant_additional_sections(
    sections: list[dict[str, Any]], merged: dict[str, Any]
) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for section in sections:
        heading = _normalize_heading(str(section.get("heading") or ""))
        field = _ADDITIONAL_SECTION_FIELDS.get(heading)
        if field and merged.get(field):
            if field == "certifications":
                certifications = merged.get("certifications") or []
                # Keep the fallback section when certificate descriptions were
                # not mapped into the first-class field.
                if any(
                    not str(item.get("description") or "").strip()
                    for item in certifications
                ):
                    kept.append(section)
                    continue
            continue
        kept.append(section)
    return kept


def _merge_structured(
    results: list[ResumeStructuredData], contact: ContactInfo
) -> ResumeStructuredData:
    merged: dict[str, Any] = {
        "version": 4,
        "contact": {"name": "", "email": "", "phone": "", "location": "", "links": []},
        "summary": "",
        "skills": [],
        "experience": [],
        "projects": [],
        "education": [],
        "certifications": [],
        "awards": [],
        "achievements": [],
        "publications": [],
        "languages": [],
        "volunteer": [],
        "interests": [],
        "additional_sections": [],
    }
    for result in results:
        data = result.model_dump()
        extracted_contact = data.get("contact") or {}
        for field in ("name", "email", "phone", "location"):
            value = str(extracted_contact.get(field) or "").strip()
            if value and not merged["contact"][field]:
                merged["contact"][field] = value
        merged["contact"]["links"].extend(extracted_contact.get("links") or [])
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
            "achievements",
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
        ("achievements", ("title",)),
        ("publications", ("title",)),
        ("languages", ("language",)),
        ("volunteer", ("company", "role", "duration")),
    ):
        merged[field] = _merge_objects(merged[field], key_fields)
    merged["additional_sections"] = _merge_objects(
        merged["additional_sections"], ("heading",)
    )
    merged["experience"] = _drop_project_like_experience(
        merged["experience"], merged["projects"]
    )
    merged["additional_sections"] = _drop_redundant_additional_sections(
        merged["additional_sections"], merged
    )
    # Keep deterministic contact details even when the LLM was given redacted
    # text and could not see them. The LLM still supplies the name, location
    # and profile links that local regexes cannot reliably identify.
    deterministic = contact.model_dump()
    deterministic_links = deterministic.pop("links", [])
    merged["contact"] = {
        **merged["contact"],
        **{k: v for k, v in deterministic.items() if v},
    }
    seen_links: set[str] = set()
    links: list[dict[str, str]] = []
    for link in [*merged["contact"].get("links", []), *deterministic_links]:
        normalized = ContactLink(
            label=str(link.get("label") or ""), url=str(link.get("url") or "")
        )
        key = normalized.url.rstrip("/").lower()
        if not key or key in seen_links:
            continue
        seen_links.add(key)
        links.append(normalized.model_dump())
    merged["contact"]["links"] = links[:20]
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
            document_links = _document_links(pages)
            structured, failed_chunks = await self._extract_structured(
                raw_text, document_links
            )
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
        native_links = await run_in_threadpool(parse_docx_links, original)
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
            _attach_native_links(pages, native_links)
            full_text = native_text
            return pages, full_text, [], bool(native_text)

        pages = await run_in_threadpool(parse_pdf_pages, pdf_bytes)
        if len(pages) > settings.resume_max_pages:
            pages = pages[: settings.resume_max_pages]
            warnings.append(
                f"Content extraction is limited to {settings.resume_max_pages} pages."
            )
        _attach_native_links(pages, native_links)
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
        self,
        raw_text: str,
        document_links: list[dict[str, Any]] | None = None,
    ) -> tuple[ResumeStructuredData, int]:
        contact = _extract_contact(raw_text, document_links)
        chunks = _chunk_resume(_redact_contact_pii(raw_text))
        if not chunks:
            return ResumeStructuredData(contact=contact), 0
        links_context = _link_context(document_links or [])
        results: list[ResumeStructuredData] = []
        failed = 0
        for chunk, section_context in chunks:
            chunk_results, chunk_failed = await self._extract_chunk(
                chunk, links_context, section_context
            )
            results.extend(chunk_results)
            failed += chunk_failed
        if not results:
            raise ResumeProcessingError(
                "llm_failed",
                "AI analysis is unavailable right now. You can retry it later.",
            )
        return _merge_structured(results, contact), failed

    async def _extract_chunk(
        self,
        chunk: str,
        links_context: str,
        section_context: str = "Resume",
        depth: int = 0,
    ) -> tuple[list[ResumeStructuredData], int]:
        prompt = (
            EXTRACT_RESUME_INFO_PROMPT.replace("{links}", links_context)
            .replace("{section_context}", section_context)
            .replace("{text}", chunk)
        )
        try:
            request: dict[str, Any] = {
                # Free Groq tiers can reject back-to-back chunks with 429;
                # the provider supplies a retry hint, so allow a few more tries.
                "max_retries": 5,
                "system_prompt": EXTRACT_RESUME_SYSTEM_PROMPT,
                "max_completion_tokens": MAX_COMPLETION_TOKENS,
            }
            if llm_service.supports_reasoning_effort:
                request["reasoning_effort"] = EXTRACTION_REASONING_EFFORT
            result = await llm_service.generate_structured(
                prompt,
                ResumeStructuredData,
                **request,
            )
            return [result], 0
        except Exception as exc:
            split = (
                _split_chunk_for_retry(chunk)
                if depth < 2 and is_incomplete_output(exc)
                else None
            )
            if split is not None:
                logger.warning(
                    "Resume extraction output was truncated; retrying as %d smaller chunks",
                    2,
                )
                results: list[ResumeStructuredData] = []
                failed = 0
                for part in split:
                    part_results, part_failed = await self._extract_chunk(
                        part, links_context, section_context, depth + 1
                    )
                    results.extend(part_results)
                    failed += part_failed
                return results, failed
            logger.warning(
                "Resume extraction chunk failed (%s: %s)",
                type(exc).__name__,
                str(exc)[:200],
            )
            return [], 1

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
