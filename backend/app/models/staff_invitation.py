"""A pending invitation for an internal staff member to join with a role.

Invitations are company-wide (single-company deployment), so they are managed
by admins and not scoped to a user. Only the SHA-256 hash of the token is
stored; the raw token is a secret that travels in the invitation email.
"""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.user import Role

StaffInvitationStatus = Literal["pending", "accepted", "revoked"]


class StaffInvitation(BaseModel):
    id: str | None = Field(default=None, alias="_id")
    email: str
    role: Role
    token_hash: str
    invited_by: str
    status: StaffInvitationStatus = "pending"
    expires_at: datetime
    accepted_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(populate_by_name=True)
