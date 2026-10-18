from datetime import datetime

from pydantic import BaseModel


class AuditLogOut(BaseModel):
    id: str
    actor_id: str | None = None
    action: str
    target_type: str = ""
    target_id: str = ""
    metadata: dict = {}
    created_at: datetime
