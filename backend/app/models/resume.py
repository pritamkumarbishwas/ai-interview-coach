from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.timeutil import ISTDateTime

ResumeAnalysisStatus = Literal[
    "pending", "processing", "ready", "partial", "failed", "deleting"
]


class ResumeAnalysis(BaseModel):
    """State of the derived OCR/LLM analysis for one stored resume.

    The original file and full extracted content are independent of this state;
    a failed analysis never discards the resume.
    """

    status: ResumeAnalysisStatus = "pending"
    version: str = "resume-v3"
    model: str = ""
    started_at: ISTDateTime | None = None
    completed_at: ISTDateTime | None = None
    error_code: str = ""
    error_message: str = ""
    failed_chunks: int = 0
    warnings: list[str] = Field(default_factory=list)


class ResumePreview(BaseModel):
    """One rendered page image stored in GridFS."""

    page: int
    file_id: str
    width: int = 0
    height: int = 0
    dpi: int = 0
    content_type: str = "image/png"


class Resume(BaseModel):
    id: str | None = Field(default=None, alias="_id")
    user_id: str
    filename: str
    mime_type: str = ""
    file_size: int = 0
    sha256: str = ""
    # Legacy local-storage key. New uploads use `original_file_id`.
    storage_key: str = ""
    storage_backend: str = "gridfs"
    original_file_id: str = ""
    content_file_id: str = ""
    raw_text: str = ""
    text_sha256: str = ""
    page_count: int = 0
    ocr_pages: list[int] = Field(default_factory=list)
    has_text_layer: bool = True
    structured_data: dict[str, Any] = Field(default_factory=dict)
    analysis: ResumeAnalysis = Field(default_factory=ResumeAnalysis)
    previews: list[ResumePreview] = Field(default_factory=list)
    created_at: ISTDateTime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: ISTDateTime = Field(default_factory=lambda: datetime.now(UTC))
    deleted_at: ISTDateTime | None = None

    model_config = ConfigDict(populate_by_name=True)
