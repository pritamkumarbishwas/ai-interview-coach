"""Competency scorecard: rubric-based, evidence-cited, advisory scoring.

Where the practice `Report` is candidate-facing feedback, the scorecard is the
recruiter-facing decision aid for a screening round. Every competency score is
aggregated in code from the stored per-answer evaluations and cites the verbatim
quotes that justify it. Scores are **advisory** — a human makes the decision —
and the candidate's identity is deliberately absent (`identity_hidden`).
"""

from datetime import UTC, datetime

from pydantic import BaseModel, Field

STRONG_COMPETENCY_MIN = 70.0
CONCERN_COMPETENCY_MAX = 50.0


class CompetencyEvidence(BaseModel):
    """The quotes from one answer that support a competency score."""

    question_id: str = ""
    topic: str = ""
    score: int = 0
    quotes: list[str] = Field(default_factory=list)


class CompetencyScore(BaseModel):
    competency: str
    score: float
    answered: int = 0
    evidence: list[CompetencyEvidence] = Field(default_factory=list)


class Scorecard(BaseModel):
    interview_id: str
    role: str = ""
    # Always true: this never decides anything on its own.
    advisory: bool = True
    overall_score: float = 0.0
    competencies: list[CompetencyScore] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    # Human-readable advisory summary (never an automatic decision).
    recommendation: str = ""
    threshold: float = 0.0
    meets_threshold: bool = False
    # Scores are rubric-only; the candidate's identity is never an input.
    identity_hidden: bool = True
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def recommendation_for(overall: float, threshold: float) -> tuple[str, bool]:
    """Advisory recommendation text + whether the threshold is met.

    Deliberately hedged: this is guidance for a reviewer, not a decision.
    """
    if threshold <= 0:
        return ("Advisory score only — no pass threshold is configured for this round.", False)
    meets = overall >= threshold
    if meets:
        return (
            f"Meets the round threshold ({threshold:.0f}) — worth advancing, pending human review.",
            True,
        )
    return (
        f"Below the round threshold ({threshold:.0f}) — review the evidence before deciding.",
        False,
    )
