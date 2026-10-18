"""Scaffolding for per-template interview configuration.

Later phases (the template builder, invitations, rounds) all need to agree on
one shape for how an interview is configured. Defining it now — with sensible
defaults and strict validation — lets those phases share a contract instead of
drifting. Nothing persists this model yet.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.interview import Difficulty, InterviewType, ProctoringMode

ResponseMode = Literal["voice", "typed", "code", "whiteboard"]
IntegrityPolicy = Literal["advisory", "strict"]


class RoundConfig(BaseModel):
    """One stage of a standardized interview."""

    key: str
    label: str = ""
    interview_type: InterviewType = "technical"
    difficulty: Difficulty = "intermediate"
    duration_minutes: int = Field(default=30, ge=1, le=180)
    target_questions: int = Field(default=5, ge=1, le=20)
    response_modes: list[ResponseMode] = Field(default_factory=lambda: ["voice", "typed"])

    model_config = ConfigDict(extra="forbid")


class InterviewTemplateConfig(BaseModel):
    """A reusable, standardized interview definition.

    The template's display name lives on the owning ``InterviewTemplate``; this
    object captures only the interview shape so it can travel independently.
    """

    proctoring_mode: ProctoringMode = "strict"
    # "advisory": integrity signals inform a human reviewer. "strict": policy can
    # block/flag harder. Never auto-rejects — a human always decides.
    integrity_policy: IntegrityPolicy = "advisory"
    allow_pauses: bool = False
    rounds: list[RoundConfig] = Field(
        default_factory=lambda: [RoundConfig(key="screen", label="Screening")]
    )

    model_config = ConfigDict(extra="forbid")
