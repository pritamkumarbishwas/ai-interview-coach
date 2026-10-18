from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.audit_log import AuditLog
from app.repositories.base import stringify_id


class AuditLogRepository:
    collection_name = "audit_logs"

    async def insert(self, db: AsyncIOMotorDatabase, entry: AuditLog) -> str:
        doc = entry.model_dump(by_alias=True, exclude={"id"})
        result = await db[self.collection_name].insert_one(doc)
        return str(result.inserted_id)

    async def list_recent(self, db: AsyncIOMotorDatabase, limit: int) -> list[dict]:
        cursor = db[self.collection_name].find({}).sort("created_at", -1).limit(limit)
        return [stringify_id(doc) async for doc in cursor]


audit_log_repository = AuditLogRepository()
