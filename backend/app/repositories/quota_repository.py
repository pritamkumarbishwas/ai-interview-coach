from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError


class QuotaRepository:
    """Daily per-actor counters backing the per-role quotas."""

    collection_name = "quota_usage"

    async def increment(
        self,
        db: AsyncIOMotorDatabase,
        *,
        actor_id: str,
        action: str,
        window_start: datetime,
    ) -> int:
        query = {"actor_id": actor_id, "action": action, "window_start": window_start}
        update = {
            "$inc": {"count": 1},
            "$setOnInsert": {"created_at": datetime.now(UTC).replace(tzinfo=None)},
        }
        try:
            doc = await db[self.collection_name].find_one_and_update(
                query, update, upsert=True, return_document=ReturnDocument.AFTER
            )
        except DuplicateKeyError:
            # Two requests created the counter at once; the loser just increments.
            doc = await db[self.collection_name].find_one_and_update(
                query,
                {"$inc": {"count": 1}},
                return_document=ReturnDocument.AFTER,
            )
        return int(doc.get("count", 0)) if doc else 0

    async def decrement(
        self,
        db: AsyncIOMotorDatabase,
        *,
        actor_id: str,
        action: str,
        window_start: datetime,
    ) -> None:
        await db[self.collection_name].update_one(
            {"actor_id": actor_id, "action": action, "window_start": window_start},
            {"$inc": {"count": -1}},
        )

    async def counts(
        self,
        db: AsyncIOMotorDatabase,
        *,
        actor_id: str,
        window_start: datetime,
    ) -> dict[str, int]:
        cursor = db[self.collection_name].find(
            {"actor_id": actor_id, "window_start": window_start}
        )
        return {doc["action"]: int(doc.get("count", 0)) async for doc in cursor}


quota_repository = QuotaRepository()
