"""Cross-candidate normalization for advisory ranking.

Raw per-answer scores drift with rubric/question difficulty, so comparing a
candidate against a threshold (or against each other) is only meaningful with
context. This module adds *relative* context for a single job's round — a mean-rank
percentile and a z-score — computed purely in code.

Normalization is advisory: it never changes whether a candidate meets the round
threshold (that stays on the raw score) and never makes a decision.
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizedScore:
    value: float
    percentile: float
    z_score: float


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _stdev(values: list[float], mean: float) -> float:
    """Population standard deviation (0.0 when every value is identical)."""
    if len(values) < 2:
        return 0.0
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return math.sqrt(variance)


def normalize(scores: list[float]) -> list[NormalizedScore]:
    """Normalize `scores` against each other, preserving input order.

    - percentile: mean-rank percentile (ties share the average rank), 50 when
      only one candidate has a score, so a single candidate is never presented
      as "top 100%".
    - z_score: standard deviations from the cohort mean, 0.0 when the cohort
      has no spread.
    """
    if not scores:
        return []

    mean = _mean(scores)
    stdev = _stdev(scores, mean)
    total = len(scores)
    results: list[NormalizedScore] = []
    for value in scores:
        below = sum(1 for other in scores if other < value)
        equal = sum(1 for other in scores if other == value)
        percentile = 100.0 * (below + 0.5 * equal) / total
        z_score = (value - mean) / stdev if stdev > 0 else 0.0
        results.append(
            NormalizedScore(
                value=value,
                percentile=round(percentile, 1),
                z_score=round(z_score, 2),
            )
        )
    return results
