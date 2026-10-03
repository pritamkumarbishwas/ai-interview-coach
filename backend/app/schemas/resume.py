from datetime import datetime

from pydantic import BaseModel, Field


class Experience(BaseModel):
    company: str
    role: str
    duration: str
    description: str


class Project(BaseModel):
    name: str
    description: str
    technologies: list[str]


class Education(BaseModel):
    institution: str
    degree: str
    year: str


class ResumeStructuredData(BaseModel):
    skills: list[str] = Field(description="A list of technical and soft skills")
    experience: list[Experience] = Field(description="Work experience entries")
    projects: list[Project] = Field(description="Notable projects")
    education: list[Education] = Field(description="Educational background")


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
    created_at: datetime
