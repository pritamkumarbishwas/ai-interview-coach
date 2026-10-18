"""Compliance record: the controls and processing this deployment applies.

Surfaced to admins (and usable as the technical annex of a data-processing
agreement) so operators can answer customer/auditor questions without reading
the source.
"""

from pydantic import BaseModel, Field


class Subprocessor(BaseModel):
    name: str
    purpose: str
    region: str = ""


class ComplianceRecord(BaseModel):
    deployment_region: str
    data_retention_days: int
    retention_purge_enabled: bool
    # App-managed secrets are encrypted at rest (field-level), on top of any
    # disk/storage-engine encryption the deployment provides.
    encryption_at_rest: bool
    llm_provider: str
    transcription_provider: str
    mail_provider: str
    dpa_contact_email: str
    # Data-subject rights the platform implements today.
    data_subject_endpoints: list[str] = Field(default_factory=list)
    subprocessors: list[Subprocessor] = Field(default_factory=list)
