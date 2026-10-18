"""Deterministic calibration metrics for the advisory scoring engine.

Scoring quality is judged by comparing AI scores against human reviewer scores
on a golden set (a handful of interviews with agreed human scores). Everything
here is a pure function of its inputs — no LLM and no database — so the numbers
are reproducible and can gate a rubric/threshold change before it ships.

Calibration never changes a candidate's outcome; it only tells us how closely
the advisory scores track human judgement.
"""

from dataclasses import dataclass

DEFAULT_TOLERANCE = 10.0


@dataclass(frozen=True)
class CalibrationRow:
    """One interview scored by both the AI and a human reviewer (0-100)."""

    label: str
    ai_score: float
    human_score: float


@dataclass(frozen=True)
class CalibrationReport:
    samples: int
    tolerance: float
    mean_absolute_error: float
    # Positive => the AI scores higher than humans (lenient); negative => harsh.
    mean_signed_bias: float
    max_absolute_error: float
    # Share of samples whose |ai - human| is within `tolerance`.
    agreement_rate: float
    worst_case: str


def evaluate(
    rows: list[CalibrationRow], tolerance: float = DEFAULT_TOLERANCE
) -> CalibrationReport:
    if not rows:
        return CalibrationReport(0, tolerance, 0.0, 0.0, 0.0, 0.0, "")

    diffs = [row.ai_score - row.human_score for row in rows]
    absolute = [abs(diff) for diff in diffs]
    within = [diff for diff in absolute if diff <= tolerance]
    worst_index = max(range(len(rows)), key=lambda index: absolute[index])

    return CalibrationReport(
        samples=len(rows),
        tolerance=tolerance,
        mean_absolute_error=round(sum(absolute) / len(rows), 2),
        mean_signed_bias=round(sum(diffs) / len(rows), 2),
        max_absolute_error=round(max(absolute), 2),
        agreement_rate=round(len(within) / len(rows), 2),
        worst_case=rows[worst_index].label,
    )
