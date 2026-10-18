from pydantic import BaseModel

from app.core.timeutil import ISTDateTime


class AuditLogOut(BaseModel):
    id: str
    actor_id: str | None = None
    action: str
    target_type: str = ""
    target_id: str = ""
    metadata: dict = {}
    created_at: ISTDateTime
