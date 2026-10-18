from pydantic import BaseModel, Field

from app.core.timeutil import ISTDateTime


class Experience(BaseModel):
    company: str
    role: str
    duration: str
    description: str


class Project(BaseModel):
    name: str
    description: str
    technologies: list[str] = Field(default_factory=list)


class Education(BaseModel):
    institution: str
    degree: str
    year: str


class ResumeStructuredData(BaseModel):
    """Extraction result.

    Every section defaults to an empty list: a resume legitimately may not have
    a given section (or the model may omit one), and a missing section must not
    fail the whole upload. This mirrors the prompt's "return an empty list for
    that section" instruction with a schema-level safety net.
    """

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


class ResumeUploadResponse(BaseModel):
    id: str
    filename: str
    structured_data: ResumeStructuredData


class ResumeSummary(BaseModel):
    """List projection — deliberately excludes the (large) raw_text field."""

    id: str
    filename: str
    file_size: int = 0
    skills: list[str] = Field(default_factory=list)
    created_at: ISTDateTime
