"""Programmatic API keys for read-only ATS integrations (Phase 8).

A key is only ever stored as a SHA-256 hash; the raw value is shown exactly once,
at creation. The plaintext prefix is kept so keys can be listed and looked up
without revealing the secret. Keys are read-only and delegated to the staff user
that created them, so they can never exceed that user's own access.
"""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Only staff roles make sense: a key acts on behalf of its creator.
ApiKeyRole = Literal["admin", "recruiter", "reviewer"]

KEY_PREFIX = "aic_"
# `KEY_PREFIX` + 40 url-safe characters of entropy (~240 bits).
KEY_SECRET_BYTES = 30


class ApiKey(BaseModel):
    id: str | None = Field(default=None, alias="_id")
    name: str
    prefix: str
    key_hash: str
    role: ApiKeyRole = "reviewer"
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None
    expires_at: datetime | None = None

    model_config = ConfigDict(populate_by_name=True)

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None
