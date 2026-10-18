from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# `candidate` is the role of a practice-module user (self-registered). Staff
# roles are provisioned by an admin via invitations. Screening candidates are
# guests (magic links) and never get a `User` record.
Role = Literal["candidate", "admin", "recruiter", "reviewer"]
STAFF_ROLES: frozenset[str] = frozenset({"admin", "recruiter", "reviewer"})


class User(BaseModel):
    id: str | None = Field(default=None, alias="_id")
    name: str
    email: str
    password_hash: str
    role: Role = "candidate"
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(populate_by_name=True)

    @property
    def is_staff(self) -> bool:
        return self.role in STAFF_ROLES

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} role={self.role}>"
