"""Audit-trail writer: best-effort, append-only, never breaks the action."""

import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.audit_log import AuditLog
from app.repositories.audit_log_repository import AuditLogRepository, audit_log_repository

logger = logging.getLogger(__name__)


class AuditService:
    def __init__(self, logs: AuditLogRepository) -> None:
        self._logs = logs

    async def record(
        self,
        db: AsyncIOMotorDatabase,
        *,
        action: str,
        actor_id: str | None = None,
        target_type: str = "",
        target_id: str = "",
        metadata: dict | None = None,
    ) -> None:
        """Write one audit entry; a failure here must never fail the request."""
        try:
            await self._logs.insert(
                db,
                AuditLog(
                    actor_id=actor_id,
                    action=action,
                    target_type=target_type,
                    target_id=target_id,
                    metadata=metadata or {},
                ),
            )
        except Exception as exc:
            logger.warning("Audit write failed for action=%s: %s", action, exc)

    async def list_recent(self, db: AsyncIOMotorDatabase, limit: int) -> list[dict]:
        return await self._logs.list_recent(db, limit)


audit_service = AuditService(audit_log_repository)
