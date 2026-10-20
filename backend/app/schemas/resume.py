import re
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator

from app.core.timeutil import ISTDateTime

_SAFE_SCHEMES = {"http", "https", "mailto"}
_BARE_DOMAIN_RE = re.compile(r"^[a-z0-9.-]+\.[a-z]{2,}(?:[/:?#].*)?$", re.IGNORECASE)


def normalize_link_url(value: object) -> str:
    """Normalize user/LLM supplied URLs and drop unsafe schemes."""
    url = str(value or "").strip()
    if not url:
        return ""
    if url.startswith("//"):
        url = f"https:{url}"
    scheme = url.split(":", 1)[0].lower() if ":" in url else ""
    if scheme in _SAFE_SCHEMES:
        parsed = urlsplit(url)
        if scheme == "mailto":
            return url if parsed.path else ""
        if not parsed.netloc:
            return ""
        return url
    if scheme or url.startswith("/"):
        return ""
    if not _BARE_DOMAIN_RE.match(url):
        return ""
    return f"https://{url}"


class ContactLink(BaseModel):
    label: str = ""
    url: str = ""

    @field_validator("url", mode="before")
    @classmethod
    def _normalize_url(cls, value: object) -> str:
        return normalize_link_url(value)


class ContactInfo(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    links: list[ContactLink] = Field(default_factory=list)


class Experience(BaseModel):
    company: str = ""
    role: str = ""
    location: str = ""
    duration: str = ""
    start_date: str = ""
    end_date: str = ""
    description: str = ""
    achievements: list[str] = Field(default_factory=list)


class Project(BaseModel):
    name: str = ""
    description: str = ""
    technologies: list[str] = Field(default_factory=list)
    links: list[ContactLink] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)


class Education(BaseModel):
    institution: str = ""
    degree: str = ""
    field_of_study: str = ""
    year: str = ""
    start_date: str = ""
    end_date: str = ""
    grade: str = ""
    details: list[str] = Field(default_factory=list)


class Certification(BaseModel):
    name: str = ""
    issuer: str = ""
    issue_date: str = ""
    credential_id: str = ""
    url: str = ""

    @field_validator("url", mode="before")
    @classmethod
    def _normalize_url(cls, value: object) -> str:
        return normalize_link_url(value)


class Award(BaseModel):
    title: str = ""
    issuer: str = ""
    date: str = ""
    description: str = ""


class Achievement(BaseModel):
    title: str = ""
    description: str = ""


class Publication(BaseModel):
    title: str = ""
    publisher: str = ""
    date: str = ""
    url: str = ""
    description: str = ""

    @field_validator("url", mode="before")
    @classmethod
    def _normalize_url(cls, value: object) -> str:
        return normalize_link_url(value)


class Language(BaseModel):
    language: str = ""
    proficiency: str = ""


class AdditionalSection(BaseModel):
    """A section the extractor could not map to a first-class field."""

    heading: str = ""
    content: str = ""


class ResumeStructuredData(BaseModel):
    """Complete, versioned extraction result.

    Every section defaults to an empty value: a resume legitimately may not have
    a given section (or the model may omit one), and a missing section must not
    fail the whole upload. Unknown headings are preserved in
    ``additional_sections`` instead of being silently discarded.
    """

    version: int = 3
    contact: ContactInfo = Field(default_factory=ContactInfo)
    summary: str = ""
    skills: list[str] = Field(
        default_factory=list, description="A list of technical and soft skills"
    )
    experience: list[Experience] = Field(
        default_factory=list, description="Work experience entries"
    )
    projects: list[Project] = Field(
        default_factory=list, description="Notable projects"
    )
    education: list[Education] = Field(
        default_factory=list, description="Educational background"
    )
    certifications: list[Certification] = Field(default_factory=list)
    awards: list[Award] = Field(default_factory=list)
    achievements: list[Achievement] = Field(default_factory=list)
    publications: list[Publication] = Field(default_factory=list)
    languages: list[Language] = Field(default_factory=list)
    volunteer: list[Experience] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    additional_sections: list[AdditionalSection] = Field(default_factory=list)


class ResumeUploadResponse(BaseModel):
    id: str
    filename: str
    structured_data: ResumeStructuredData = Field(default_factory=ResumeStructuredData)
    analysis_status: str = "pending"
    page_count: int = 0
    ocr_used: bool = False
    deduplicated: bool = False


class ResumeSummary(BaseModel):
    """List projection — deliberately excludes the (large) raw_text field."""

    id: str
    filename: str
    file_size: int = 0
    mime_type: str = ""
    skills: list[str] = Field(default_factory=list)
    analysis_status: str = "ready"
    page_count: int = 0
    has_preview: bool = False
    ocr_used: bool = False
    created_at: ISTDateTime


class ResumeTextResponse(BaseModel):
    id: str
    text: str
    page_count: int = 0
    ocr_pages: list[int] = Field(default_factory=list)


class ResumeActionResponse(BaseModel):
    id: str
    analysis_status: str
