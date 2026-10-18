"""Phase 10 (Advanced AI): shadow-mode agreement between AI and human decisions.

Pure, deterministic aggregation over a job's shortlist entries (which already
carry the advisory score, threshold and the recorded human decision). No LLM and
no database access happen here, so the numbers are reproducible and auditable.

The AI recommendation is the scorecard's `meets_threshold` flag; the human
signal is the recorded decision. A row is only comparable when *both* exist:
a configured threshold produces the AI signal, and a non-``pending`` decision
produces the human one. Everything else is reported as an exclusion.
"""

from app.models.invitation import Decision
from app.models.shadow import (
    ALIGNMENT_TOLERANCE,
    MIN_COMPARED,
    ShadowDisagreement,
    ShadowReport,
)
from app.schemas.invitation import ShortlistEntry

# Only a recorded "advance" is a positive human signal; hold and decline are not.
POSITIVE_DECISION: Decision = "advance"
# Bounded so a huge pipeline cannot turn the report into a full row dump.
MAX_DISAGREEMENTS = 25


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(100.0 * numerator / denominator, 1)


class ShadowService:
    def build(self, job_id: str, entries: list[ShortlistEntry]) -> ShadowReport:
        """Compare the advisory AI signal with the human decision per candidate."""
        excluded_not_completed = excluded_no_threshold = excluded_awaiting_decision = 0
        agreed_advance = agreed_review = ai_lenient = ai_strict = 0
        disagreements: list[ShadowDisagreement] = []

        for entry in entries:
            if entry.status != "completed":
                excluded_not_completed += 1
                continue
            if entry.threshold <= 0:
                # No threshold means the scorecard makes no advance/review call.
                excluded_no_threshold += 1
                continue
            if entry.decision == "pending":
                excluded_awaiting_decision += 1
                continue

            ai_advances = entry.meets_threshold
            human_advances = entry.decision == POSITIVE_DECISION

            if ai_advances and human_advances:
                agreed_advance += 1
            elif not ai_advances and not human_advances:
                agreed_review += 1
            elif ai_advances:
                ai_lenient += 1
            else:
                ai_strict += 1

            if ai_advances != human_advances:
                disagreements.append(
                    ShadowDisagreement(
                        invitation_id=entry.invitation_id,
                        candidate_name=entry.candidate_name,
                        ai_recommendation="advance" if ai_advances else "review",
                        human_decision=entry.decision,
                        overall_score=entry.overall_score,
                        threshold=entry.threshold,
                        direction="ai_lenient" if ai_advances else "ai_strict",
                        integrity_level=entry.integrity_level,
                    )
                )

        compared = agreed_advance + agreed_review + ai_lenient + ai_strict
        agreed = agreed_advance + agreed_review
        advanced_rate_ai = _rate(agreed_advance + ai_lenient, compared)
        advanced_rate_human = _rate(agreed_advance + ai_strict, compared)
        leniency_gap = round(advanced_rate_ai - advanced_rate_human, 1)

        # Biggest disagreements first: how far the score sat from the threshold.
        disagreements.sort(
            key=lambda item: (abs(item.overall_score - item.threshold), item.candidate_name),
            reverse=True,
        )

        return ShadowReport(
            job_id=job_id,
            advisory=True,
            compared=compared,
            agreed=agreed,
            agreement_rate=_rate(agreed, compared),
            agreed_advance=agreed_advance,
            agreed_review=agreed_review,
            ai_lenient=ai_lenient,
            ai_strict=ai_strict,
            advanced_rate_ai=advanced_rate_ai,
            advanced_rate_human=advanced_rate_human,
            leniency_gap=leniency_gap,
            bias=self._bias(leniency_gap),
            sufficient_sample=compared >= MIN_COMPARED,
            excluded_no_threshold=excluded_no_threshold,
            excluded_awaiting_decision=excluded_awaiting_decision,
            excluded_not_completed=excluded_not_completed,
            disagreements=disagreements[:MAX_DISAGREEMENTS],
        )

    @staticmethod
    def _bias(leniency_gap: float) -> str:
        if leniency_gap >= ALIGNMENT_TOLERANCE:
            return "lenient"
        if leniency_gap <= -ALIGNMENT_TOLERANCE:
            return "strict"
        return "aligned"


shadow_service = ShadowService()
