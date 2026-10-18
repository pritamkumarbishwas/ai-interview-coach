"""Phase 8: aggregate recruiting analytics + CSV export.

Pure, deterministic aggregation over a job's shortlist entries (which already
carry the advisory score, threshold, integrity level and human decision). No
scoring or LLM calls happen here, and no candidate identity is used in the
aggregates — a row-level export is the only place identity appears, and it is
recruiter-gated at the route.

CSV cells are defanged against spreadsheet formula injection because candidate
name/email are attacker-influenced free text.
"""

import csv
import io
from statistics import median

from app.models.analytics import JobAnalytics, ScoreBucket
from app.schemas.invitation import ShortlistEntry

# Fixed 0-100 bands for the advisory score distribution.
SCORE_BANDS: tuple[tuple[str, float, float], ...] = (
    ("0-59", 0.0, 59.999),
    ("60-69", 60.0, 69.999),
    ("70-79", 70.0, 79.999),
    ("80-89", 80.0, 89.999),
    ("90-100", 90.0, 100.0),
)

DECISIONS: tuple[str, ...] = ("pending", "advance", "hold", "decline")
INTEGRITY_LEVELS: tuple[str, ...] = ("low", "moderate", "elevated", "high", "unknown")

# Leading characters that spreadsheets interpret as a formula.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

CSV_COLUMNS: tuple[str, ...] = (
    "candidate_name",
    "candidate_email",
    "status",
    "decision",
    "overall_score",
    "threshold",
    "meets_threshold",
    "percentile",
    "integrity_level",
    "integrity_score",
)


def _band_for(score: float) -> str:
    for label, low, high in SCORE_BANDS:
        if low <= score <= high:
            return label
    return SCORE_BANDS[-1][0]


def _defang(value: str) -> str:
    """Neutralize a cell a spreadsheet would evaluate as a formula."""
    return f"'{value}" if value.startswith(_FORMULA_PREFIXES) else value


class AnalyticsService:
    def build(self, job_id: str, entries: list[ShortlistEntry]) -> JobAnalytics:
        """Aggregate a job's shortlist entries into a funnel + distributions."""
        status_counts = {"pending": 0, "started": 0, "completed": 0, "expired": 0, "revoked": 0}
        for entry in entries:
            if entry.status in status_counts:
                status_counts[entry.status] += 1

        completed = [entry for entry in entries if entry.status == "completed"]
        scores = [entry.overall_score for entry in completed]
        passed = sum(1 for entry in completed if entry.meets_threshold)

        decisions = dict.fromkeys(DECISIONS, 0)
        for entry in entries:
            decisions[entry.decision] = decisions.get(entry.decision, 0) + 1

        integrity = dict.fromkeys(INTEGRITY_LEVELS, 0)
        for entry in completed:
            level = entry.integrity_level or "unknown"
            integrity[level] = integrity.get(level, 0) + 1

        total = len(entries)
        return JobAnalytics(
            job_id=job_id,
            total_invited=total,
            pending=status_counts["pending"],
            in_progress=status_counts["started"],
            completed=len(completed),
            expired=status_counts["expired"],
            revoked=status_counts["revoked"],
            completion_rate=self._rate(len(completed), total),
            passed=passed,
            pass_rate=self._rate(passed, len(completed)),
            average_score=round(sum(scores) / len(scores), 1) if scores else 0.0,
            median_score=round(median(scores), 1) if scores else 0.0,
            score_distribution=self._distribution(scores),
            decisions=decisions,
            integrity_distribution=integrity,
        )

    def to_csv(self, entries: list[ShortlistEntry]) -> str:
        """Serialize shortlist rows to CSV (formula-injection defanged)."""
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\r\n")
        writer.writerow(CSV_COLUMNS)
        for entry in entries:
            writer.writerow(
                [
                    _defang(entry.candidate_name),
                    _defang(str(entry.candidate_email)),
                    entry.status,
                    entry.decision,
                    f"{entry.overall_score:.1f}",
                    f"{entry.threshold:.1f}",
                    "yes" if entry.meets_threshold else "no",
                    "" if entry.percentile is None else f"{entry.percentile:.1f}",
                    entry.integrity_level or "",
                    "" if entry.integrity_score is None else str(entry.integrity_score),
                ]
            )
        return buffer.getvalue()

    @staticmethod
    def _rate(numerator: int, denominator: int) -> float:
        if denominator <= 0:
            return 0.0
        return round(100.0 * numerator / denominator, 1)

    @staticmethod
    def _distribution(scores: list[float]) -> list[ScoreBucket]:
        counts = dict.fromkeys((label for label, _, _ in SCORE_BANDS), 0)
        for score in scores:
            counts[_band_for(score)] += 1
        return [ScoreBucket(label=label, count=counts[label]) for label, _, _ in SCORE_BANDS]


analytics_service = AnalyticsService()
