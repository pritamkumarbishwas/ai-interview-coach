"""Builds a competency scorecard from a completed interview's evaluations.

No LLM is involved: every number is aggregated in code from the stored,
already-evaluated answers, so the scorecard is stable and auditable.
"""

import logging

from app.models.interview import Interview, Question
from app.models.scorecard import (
    CONCERN_COMPETENCY_MAX,
    STRONG_COMPETENCY_MIN,
    CompetencyEvidence,
    CompetencyScore,
    Scorecard,
    recommendation_for,
)

logger = logging.getLogger(__name__)

GENERAL_COMPETENCY = "General"
MAX_QUOTES_PER_ANSWER = 3


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 1)


class ScorecardService:
    def build(self, interview: Interview) -> Scorecard:
        """Aggregate per-competency scores with cited evidence.

        Competency for each answer comes from the evaluator; when it is empty
        (older documents, or a model that declined to label) the question's
        topic is used, falling back to "General".
        """
        questions: dict[str, Question] = {q.id: q for q in interview.questions}
        buckets: dict[str, list[tuple[int, str, str, list[str]]]] = {}

        for answer in interview.answers:
            evaluation = answer.evaluation
            if evaluation is None:
                continue
            question = questions.get(answer.question_id)
            competency = (
                evaluation.competency
                or (question.topic if question else "")
                or GENERAL_COMPETENCY
            )
            topic = question.topic if question else ""
            quotes = [quote for quote in evaluation.evidence if quote][:MAX_QUOTES_PER_ANSWER]
            buckets.setdefault(competency, []).append(
                (evaluation.overall, answer.question_id, topic, quotes)
            )

        competencies: list[CompetencyScore] = []
        for competency, items in buckets.items():
            competencies.append(
                CompetencyScore(
                    competency=competency,
                    score=_mean([item[0] for item in items]),
                    answered=len(items),
                    evidence=[
                        CompetencyEvidence(
                            question_id=question_id,
                            topic=topic,
                            score=score,
                            quotes=quotes,
                        )
                        for score, question_id, topic, quotes in items
                    ],
                )
            )

        # Keep rubric dimensions visible even when they were never answered.
        for name in interview.rubric:
            if not any(item.competency == name for item in competencies):
                competencies.append(
                    CompetencyScore(competency=name, score=0.0, answered=0)
                )

        competencies.sort(key=lambda item: item.competency)
        scored = [item.score for item in competencies if item.answered]

        strengths = [
            item.competency
            for item in competencies
            if item.answered and item.score >= STRONG_COMPETENCY_MIN
        ]
        concerns = [
            item.competency
            for item in competencies
            if item.answered and item.score <= CONCERN_COMPETENCY_MAX
        ]
        recommendation, meets_threshold = recommendation_for(
            _mean(scored), interview.pass_threshold
        )

        return Scorecard(
            interview_id=interview.id or "",
            role=interview.role,
            advisory=True,
            overall_score=_mean(scored),
            competencies=competencies,
            strengths=strengths,
            concerns=concerns,
            recommendation=recommendation,
            threshold=interview.pass_threshold,
            meets_threshold=meets_threshold,
            identity_hidden=True,
        )


scorecard_service = ScorecardService()
