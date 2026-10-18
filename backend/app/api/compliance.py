"""Compliance record (Phase 9).

A single admin-readable endpoint describing the data-protection posture of this
deployment: where data lives, how long it is kept, which third parties process
it, and which data-subject rights the platform implements.
"""

from fastapi import APIRouter, Depends

from app.api.deps import require_admin
from app.core.config import settings
from app.core.crypto import field_cipher
from app.models.user import User
from app.schemas.compliance import ComplianceRecord, Subprocessor

router = APIRouter()

# Data-subject rights implemented today.
DATA_SUBJECT_ENDPOINTS = [
    "GET /api/invitations/{id}/data (right of access)",
    "POST /api/invitations/{id}/erase (right to erasure)",
    "POST /api/invitations/retention/purge (retention enforcement)",
]


def _subprocessors() -> list[Subprocessor]:
    rows = [
        Subprocessor(
            name=f"LLM provider ({settings.llm_provider})",
            purpose="Interview question generation and answer scoring",
            region=settings.deployment_region,
        )
    ]
    if settings.transcription_provider != "none":
        rows.append(
            Subprocessor(
                name=f"Transcription provider ({settings.transcription_provider})",
                purpose="Speech-to-text for candidate answers",
                region=settings.deployment_region,
            )
        )
    return rows


@router.get("", response_model=ComplianceRecord)
async def get_compliance_record(_: User = Depends(require_admin)) -> ComplianceRecord:
    """The deployment's data-processing record (admin-only)."""
    return ComplianceRecord(
        deployment_region=settings.deployment_region,
        data_retention_days=settings.data_retention_days,
        retention_purge_enabled=settings.retention_purge_enabled,
        encryption_at_rest=field_cipher.enabled,
        llm_provider=settings.llm_provider,
        transcription_provider=settings.transcription_provider,
        mail_provider=settings.mail_provider,
        dpa_contact_email=settings.dpa_contact_email,
        data_subject_endpoints=DATA_SUBJECT_ENDPOINTS,
        subprocessors=_subprocessors(),
    )
