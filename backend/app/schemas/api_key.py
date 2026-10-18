from pydantic import BaseModel, Field

from app.core.timeutil import ISTDateTime
from app.models.api_key import ApiKeyRole


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    role: ApiKeyRole = "reviewer"
    # Optional lifetime; `None` means the key never expires on its own.
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)


class ApiKeyOut(BaseModel):
    id: str
    name: str
    prefix: str
    role: ApiKeyRole
    created_at: ISTDateTime
    last_used_at: ISTDateTime | None = None
    revoked_at: ISTDateTime | None = None
    expires_at: ISTDateTime | None = None


class ApiKeyCreated(ApiKeyOut):
    """The one and only time the raw key is returned."""

    key: str
