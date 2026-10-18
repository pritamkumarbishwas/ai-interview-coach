from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import get_audit_service, require_admin
from app.core.database import get_db
from app.models.user import User
from app.schemas.audit import AuditLogOut
from app.services.audit_service import AuditService

router = APIRouter()


@router.get("", response_model=list[AuditLogOut])
async def list_audit_logs(
    admin: User = Depends(require_admin),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: AuditService = Depends(get_audit_service),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AuditLogOut]:
    docs = await service.list_recent(db, limit)
    return [
        AuditLogOut(
            id=doc["_id"],
            actor_id=doc.get("actor_id"),
            action=doc["action"],
            target_type=doc.get("target_type", ""),
            target_id=doc.get("target_id", ""),
            metadata=doc.get("metadata", {}),
            created_at=doc["created_at"],
        )
        for doc in docs
    ]
