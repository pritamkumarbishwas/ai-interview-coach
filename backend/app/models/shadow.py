"""Phase 10 (Advanced AI): shadow mode — does the advisory AI agree with humans?

Shadow mode answers a **trust** question, not a hiring question: across one
job's candidates, how often would the advisory AI recommendation have matched
the decision a human actually recorded? The AI is not in the decision path, so
this never changes an outcome — it only measures calibration in production.

The report is deliberately honest about its own coverage: candidates with no
configured threshold or no recorded decision are counted as *exclusions*, so a
tiny compared sample is never mistaken for agreement.
"""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.timeutil import ISTDateTime
from app.models.invitation import Decision

# The side the advisory AI lands on, in terms a reviewer recognises.
ShadowSide = Literal["advance", "review"]
# Which way a disagreement leans. "ai_lenient" = AI advanced, the panel did not.
DisagreementDirection = Literal["ai_lenient", "ai_strict"]
# How the AI's advance rate compares with the panel's, within tolerance.
BiasVerdict = Literal["aligned", "lenient", "strict"]

# A compared advance-rate gap this small is noise, not a systematic lean.
ALIGNMENT_TOLERANCE = 10.0
# Below this many compared candidates, an agreement rate is not meaningful.
MIN_COMPARED = 10


class ShadowDisagreement(BaseModel):
    """One candidate the advisory AI and the human panel judged differently."""

    invitation_id: str
    candidate_name: str = ""
    ai_recommendation: ShadowSide
    human_decision: Decision
    overall_score: float = 0.0
    threshold: float = 0.0
    # "ai_lenient": AI wanted to advance but the panel held/declined.
    # "ai_strict": the panel advanced but the AI's advisory score fell short.
    direction: DisagreementDirection
    integrity_level: str | None = None


class ShadowReport(BaseModel):
    """AI-vs-human agreement for one job's decided candidates (advisory only)."""

    job_id: str
    # Always true: shadow mode observes decisions, it never makes one.
    advisory: bool = True
    # Candidates with both an AI recommendation and a recorded human decision.
    compared: int = 0
    agreed: int = 0
    agreement_rate: float = 0.0
    # Confusion-matrix quadrants (agreed two + disagreement two == compared).
    agreed_advance: int = 0
    agreed_review: int = 0
    ai_lenient: int = 0
    ai_strict: int = 0
    # Share of compared candidates each side would have advanced.
    advanced_rate_ai: float = 0.0
    advanced_rate_human: float = 0.0
    # AI minus human advance rate (positive => the AI is the more permissive side).
    leniency_gap: float = 0.0
    bias: BiasVerdict = "aligned"
    # True once enough candidates have been decided for the rate to mean anything.
    sufficient_sample: bool = False
    # Coverage: why candidates were left out, so the sample size is never a mystery.
    excluded_no_threshold: int = 0
    excluded_awaiting_decision: int = 0
    excluded_not_completed: int = 0
    # Bounded, most-notable-first, so the reviewer can inspect the disagreements.
    disagreements: list[ShadowDisagreement] = Field(default_factory=list)
    generated_at: ISTDateTime = Field(default_factory=lambda: datetime.now(UTC))
