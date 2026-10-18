from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.collection import ReturnDocument

from app.models.job import Job
from app.repositories.base import find_owned_document, stringify_id, to_object_id

# Only the fields the list endpoint returns; the description stays in the db.
# ``user_id`` travels too so an admin's cross-owner list can show the owner.
LIST_PROJECTION = {
    "title": 1,
    "company": 1,
    "status": 1,
    "template_id": 1,
    "user_id": 1,
    "reviewer_ids": 1,
    "created_at": 1,
}


class JobRepository:
    collection_name = "jobs"

    async def insert(self, db: AsyncIOMotorDatabase, job: Job) -> str:
        doc = job.model_dump(by_alias=True, exclude={"id"})
        result = await db[self.collection_name].insert_one(doc)
        return str(result.inserted_id)

    async def list_for_user(self, db: AsyncIOMotorDatabase, user_id: str, limit: int) -> list[dict]:
        cursor = (
            db[self.collection_name]
            .find({"user_id": user_id}, LIST_PROJECTION)
            .sort("created_at", -1)
            .limit(limit)
        )
        return [stringify_id(doc) async for doc in cursor]

    async def list_all(self, db: AsyncIOMotorDatabase, limit: int) -> list[dict]:
        """Every requisition, newest first (admin cross-owner view)."""
        cursor = (
            db[self.collection_name]
            .find({}, LIST_PROJECTION)
            .sort("created_at", -1)
            .limit(limit)
        )
        return [stringify_id(doc) async for doc in cursor]

    async def list_for_reviewer(
        self, db: AsyncIOMotorDatabase, user_id: str, limit: int
    ) -> list[dict]:
        """Requisitions a reviewer was assigned to (cross-owner, read-only)."""
        cursor = (
            db[self.collection_name]
            .find({"reviewer_ids": user_id}, LIST_PROJECTION)
            .sort("created_at", -1)
            .limit(limit)
        )
        return [stringify_id(doc) async for doc in cursor]

    async def find_owned(self, db: AsyncIOMotorDatabase, job_id: str, user_id: str) -> dict | None:
        return await find_owned_document(db, self.collection_name, job_id, user_id)

    async def get_by_id(self, db: AsyncIOMotorDatabase, job_id: str) -> dict | None:
        """Fetch a job regardless of owner (used by background handlers)."""
        object_id = to_object_id(job_id)
        if object_id is None:
            return None
        doc = await db[self.collection_name].find_one({"_id": object_id})
        return stringify_id(doc) if doc else None

    async def update(
        self, db: AsyncIOMotorDatabase, job_id: str, user_id: str, fields: dict
    ) -> dict | None:
        object_id = to_object_id(job_id)
        if object_id is None:
            return None
        fields["updated_at"] = datetime.now(UTC)
        doc = await db[self.collection_name].find_one_and_update(
            {"_id": object_id, "user_id": user_id},
            {"$set": fields},
            return_document=ReturnDocument.AFTER,
        )
        return stringify_id(doc) if doc else None

    async def count_for_template(
        self, db: AsyncIOMotorDatabase, user_id: str, template_id: str
    ) -> int:
        return await db[self.collection_name].count_documents(
            {"user_id": user_id, "template_id": template_id}
        )

    async def count_for_template_any(
        self, db: AsyncIOMotorDatabase, template_id: str
    ) -> int:
        """Whether any requisition (any owner) still references the template."""
        return await db[self.collection_name].count_documents(
            {"template_id": template_id}
        )

    async def delete(self, db: AsyncIOMotorDatabase, job_id: str, user_id: str) -> None:
        object_id = to_object_id(job_id)
        if object_id is None:
            return
        await db[self.collection_name].delete_one({"_id": object_id, "user_id": user_id})

    async def update_any(
        self, db: AsyncIOMotorDatabase, job_id: str, fields: dict
    ) -> dict | None:
        """Update a requisition regardless of owner (admin override)."""
        object_id = to_object_id(job_id)
        if object_id is None:
            return None
        fields["updated_at"] = datetime.now(UTC)
        doc = await db[self.collection_name].find_one_and_update(
            {"_id": object_id},
            {"$set": fields},
            return_document=ReturnDocument.AFTER,
        )
        return stringify_id(doc) if doc else None

    async def delete_any(self, db: AsyncIOMotorDatabase, job_id: str) -> bool:
        """Delete a requisition regardless of owner (admin override)."""
        object_id = to_object_id(job_id)
        if object_id is None:
            return False
        result = await db[self.collection_name].delete_one({"_id": object_id})
        return result.deleted_count > 0

    async def set_reviewers(
        self, db: AsyncIOMotorDatabase, job_id: str, reviewer_ids: list[str]
    ) -> dict | None:
        """Replace the reviewer assignment list on a requisition."""
        object_id = to_object_id(job_id)
        if object_id is None:
            return None
        doc = await db[self.collection_name].find_one_and_update(
            {"_id": object_id},
            {
                "$set": {
                    "reviewer_ids": reviewer_ids,
                    "updated_at": datetime.now(UTC),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return stringify_id(doc) if doc else None


job_repository = JobRepository()
