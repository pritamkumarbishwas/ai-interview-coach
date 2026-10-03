from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.job_description import JobDescription
from app.repositories.base import find_owned_document, stringify_id, to_object_id

# Only the fields the list endpoint returns; `raw_text` stays in the database.
# `structured_data.responsibilities` feeds the snippet fallback for documents
# saved before the `snippet` field existed.
LIST_PROJECTION = {
    "title": 1,
    "company": 1,
    "snippet": 1,
    "created_at": 1,
    "structured_data.responsibilities": 1,
}


class JobDescriptionRepository:
    collection_name = "job_descriptions"

    async def insert(self, db: AsyncIOMotorDatabase, jd: JobDescription) -> str:
        doc = jd.model_dump(by_alias=True, exclude={"id"})
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

    async def find_owned(self, db: AsyncIOMotorDatabase, jd_id: str, user_id: str) -> dict | None:
        return await find_owned_document(db, self.collection_name, jd_id, user_id)

    async def delete(self, db: AsyncIOMotorDatabase, jd_id: str, user_id: str) -> None:
        object_id = to_object_id(jd_id)
        if object_id is None:
            return
        await db[self.collection_name].delete_one({"_id": object_id, "user_id": user_id})


job_description_repository = JobDescriptionRepository()
