"""ATS provider adapters for outbound webhook payloads (Phase 8).

We always send the same normalized envelope; ``provider`` selects an extra
``data`` block shaped for the partner's own ingestion model (Greenhouse, Lever).
Those provider blocks mirror the field names each integration consumes, but
they must be validated against the partner's live API before go-live — the
envelope is the stable contract, the provider block is the adapter.
"""

from datetime import UTC, datetime

from app.models.invitation import ScreeningInvitation
from app.models.job import Job, WebhookProvider

# The single event we emit today; kept explicit so more can be added.
CANDIDATE_DECIDED = "candidate.decided"


def build_payload(
    provider: WebhookProvider,
    job: Job,
    invitation: ScreeningInvitation,
    *,
    overall_score: float | None,
    meets_threshold: bool | None,
) -> dict:
    """Assemble the JSON body for a ``candidate.decided`` event."""
    name = invitation.candidate_name or ""
    first, _, last = name.partition(" ")
    assessment = {
        "overall_score": overall_score,
        "meets_threshold": meets_threshold,
        # Advisory by design: the model never decides, a human does.
        "advisory": True,
    }
    payload: dict = {
        "event": CANDIDATE_DECIDED,
        "sent_at": datetime.now(UTC).isoformat(),
        "job": {"id": job.id, "title": job.title, "company": job.company},
        "candidate": {
            "name": name,
            "email": invitation.candidate_email,
            "role": invitation.role,
        },
        "decision": {
            "value": invitation.decision,
            "note": invitation.decision_note,
            "decided_at": _iso(invitation.decided_at),
        },
        "assessment": assessment,
    }
    payload["provider"] = provider
    if provider == "greenhouse":
        payload["data"] = _greenhouse(invitation, assessment, first, last)
    elif provider == "lever":
        payload["data"] = _lever(job, invitation, assessment, name)
    return payload


def _greenhouse(
    invitation: ScreeningInvitation, assessment: dict, first: str, last: str
) -> dict:
    actions = {
        "advance": "advance",
        "hold": "hold",
        "decline": "decline",
        "pending": "revert",
    }
    return {
        "type": "candidate_stage_change",
        "action": actions.get(invitation.decision, "revert"),
        "stage": {"name": "Screening"},
        "candidate": {
            "first_name": first,
            "last_name": last,
            "email": invitation.candidate_email,
        },
        "scorecard": {"overall": assessment["overall_score"]},
    }


def _lever(job: Job, invitation: ScreeningInvitation, assessment: dict, name: str) -> dict:
    advance = {"advance": True, "decline": False}.get(invitation.decision)
    return {
        "event": "candidate.decision",
        "posting": {"title": job.title, "company": job.company},
        "candidate": {"name": name, "email": invitation.candidate_email},
        "advance": advance,
        "note": invitation.decision_note,
        "assessment": assessment,
    }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
