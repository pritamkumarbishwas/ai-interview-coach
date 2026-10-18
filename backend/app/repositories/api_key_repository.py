from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.api_key import ApiKey
from app.repositories.base import stringify_id, to_object_id

LIST_PROJECTION = {
    "name": 1,
    "prefix": 1,
    "role": 1,
    "created_by": 1,
    "created_at": 1,
    "last_used_at": 1,
    "revoked_at": 1,
    "expires_at": 1,
}


class ApiKeyRepository:
    collection_name = "api_keys"

    async def insert(self, db: AsyncIOMotorDatabase, api_key: ApiKey) -> str:
        doc = api_key.model_dump(by_alias=True, exclude={"id"})
        result = await db[self.collection_name].insert_one(doc)
        return str(result.inserted_id)

    async def find_by_prefix(self, db: AsyncIOMotorDatabase, prefix: str) -> dict | None:
        """Look up a key by its non-secret prefix (verification follows)."""
        doc = await db[self.collection_name].find_one(
            {"prefix": prefix},
            {
                "prefix": 1,
                "name": 1,
                "key_hash": 1,
                "role": 1,
                "created_by": 1,
                "last_used_at": 1,
                "revoked_at": 1,
                "expires_at": 1,
            },
        )
        return stringify_id(doc) if doc else None

    async def list_for_user(
        self, db: AsyncIOMotorDatabase, user_id: str, limit: int
    ) -> list[dict]:
        cursor = (
            db[self.collection_name]
            .find({"created_by": user_id}, LIST_PROJECTION)
            .sort("created_at", -1)
            .limit(limit)
        )
        return [stringify_id(doc) async for doc in cursor]

    async def find_owned(
        self, db: AsyncIOMotorDatabase, key_id: str, user_id: str
    ) -> dict | None:
        object_id = to_object_id(key_id)
        if object_id is None:
            return None
        doc = await db[self.collection_name].find_one(
            {"_id": object_id, "created_by": user_id}
        )
        return stringify_id(doc) if doc else None

    async def revoke(self, db: AsyncIOMotorDatabase, key_id: str, user_id: str) -> bool:
        object_id = to_object_id(key_id)
        if object_id is None:
            return False
        result = await db[self.collection_name].update_one(
            {"_id": object_id, "created_by": user_id, "revoked_at": None},
            {"$set": {"revoked_at": datetime.now(UTC)}},
        )
        return result.modified_count > 0

    async def touch(self, db: AsyncIOMotorDatabase, key_id: str) -> None:
        """Record last use (best-effort; never fails the caller's request)."""
        object_id = to_object_id(key_id)
        if object_id is None:
            return
        await db[self.collection_name].update_one(
            {"_id": object_id}, {"$set": {"last_used_at": datetime.now(UTC)}}
        )


api_key_repository = ApiKeyRepository()
