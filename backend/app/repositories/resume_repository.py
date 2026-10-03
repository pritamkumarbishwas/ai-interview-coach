from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.resume import Resume
from app.repositories.base import find_owned_document, stringify_id, to_object_id

# Only the fields the list endpoint returns; `raw_text` and the stored file
# key stay in the database.
LIST_PROJECTION = {
    "filename": 1,
    "file_size": 1,
    "created_at": 1,
    "structured_data.skills": 1,
}


class ResumeRepository:
    collection_name = "resumes"

    async def insert(self, db: AsyncIOMotorDatabase, resume: Resume) -> str:
        doc = resume.model_dump(by_alias=True, exclude={"id"})
        result = await db[self.collection_name].insert_one(doc)
        return str(result.inserted_id)

    async def list_for_user(
        self, db: AsyncIOMotorDatabase, user_id: str, limit: int
    ) -> list[dict]:
        cursor = (
            db[self.collection_name]
            .find({"user_id": user_id}, LIST_PROJECTION)
            .sort("created_at", -1)
            .limit(limit)
        )
        return [stringify_id(doc) async for doc in cursor]

    async def find_owned(
        self, db: AsyncIOMotorDatabase, resume_id: str, user_id: str
    ) -> dict | None:
        return await find_owned_document(db, self.collection_name, resume_id, user_id)

    async def delete(self, db: AsyncIOMotorDatabase, resume_id: str, user_id: str) -> None:
        object_id = to_object_id(resume_id)
        if object_id is None:
            return
        await db[self.collection_name].delete_one({"_id": object_id, "user_id": user_id})


resume_repository = ResumeRepository()
