"""Append-only audit trail for privileged and state-changing actions.

The scaffold is deliberately small: a typed entry, a best-effort writer that
never breaks the action it records, and a list endpoint for admins. Later
phases add more call sites, not a new mechanism.
"""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class AuditLog(BaseModel):
    id: str | None = Field(default=None, alias="_id")
    actor_id: str | None = None
    action: str
    target_type: str = ""
    target_id: str = ""
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(populate_by_name=True)
