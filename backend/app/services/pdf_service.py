"""One-page PDF screening summary for a job requisition (Phase 8 export).

Renderer only: it receives already-computed analytics and shortlist rows and
lays them onto a single page. Identity-free by design — it shows names and
advisory scores, never a decision the model made (the model never decides).
"""

from datetime import UTC, datetime

import fitz

from app.models.analytics import JobAnalytics
from app.schemas.invitation import ShortlistEntry

PAGE_MARGIN = 40
LINE_HEIGHT = 13
FONT_SIZE = 9
MAX_ROWS = 20
NAME_WIDTH = 34


class PdfService:
    def render_job_summary(
        self,
        job_title: str,
        company: str,
        analytics: JobAnalytics,
        entries: list[ShortlistEntry],
    ) -> bytes:
        doc = fitz.open()
        try:
            page = doc.new_page()
            for index, line in enumerate(self._lines(job_title, company, analytics, entries)):
                page.insert_text(
                    (PAGE_MARGIN, PAGE_MARGIN + index * LINE_HEIGHT),
                    line,
                    fontsize=FONT_SIZE,
                )
            return doc.tobytes()
        finally:
            doc.close()

    def _lines(
        self,
        job_title: str,
        company: str,
        analytics: JobAnalytics,
        entries: list[ShortlistEntry],
    ) -> list[str]:
        generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        lines = [
            f"Screening summary — {job_title or 'Untitled role'}",
            f"{company}".strip() or "—",
            f"Generated {generated} · advisory only (no automated decisions)",
            "",
            "Funnel",
            f"  Invited {analytics.total_invited}   Completed {analytics.completed}"
            f"   In progress {analytics.in_progress}   Pending {analytics.pending}",
            f"  Expired {analytics.expired}   Revoked {analytics.revoked}",
            f"  Completion rate {analytics.completion_rate}%   Pass rate {analytics.pass_rate}%",
            "",
            "Scores (completed candidates)",
            f"  Average {analytics.average_score}   Median {analytics.median_score}",
            "  Distribution: "
            + "   ".join(f"{b.label}:{b.count}" for b in analytics.score_distribution),
            "",
            "Decisions",
            "  "
            + "   ".join(f"{key}:{value}" for key, value in analytics.decisions.items()),
            "Integrity (advisory)",
            "  "
            + "   ".join(
                f"{key}:{value}" for key, value in analytics.integrity_distribution.items()
            ),
            "",
            f"Top candidates (by advisory score, max {MAX_ROWS})",
            "  #  Candidate                            Score  Pct  Integrity   Decision",
        ]
        ranked = [entry for entry in entries if entry.status == "completed"][:MAX_ROWS]
        if not ranked:
            lines.append("  (no completed candidates yet)")
            return lines
        for rank, entry in enumerate(ranked, start=1):
            percentile = f"{entry.percentile:.0f}" if entry.percentile is not None else "-"
            integrity = entry.integrity_level or "-"
            lines.append(
                f"  {rank:<2} {_clip(entry.candidate_name, NAME_WIDTH):<{NAME_WIDTH}} "
                f"{entry.overall_score:>6.1f} {percentile:>4}  {integrity:<10}  "
                f"{entry.decision}"
            )
        return lines


def _clip(value: str, width: int) -> str:
    value = " ".join(value.split())
    return value if len(value) <= width else value[: width - 1] + "…"


pdf_service = PdfService()
