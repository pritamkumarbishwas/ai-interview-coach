from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.resume import Resume
from app.repositories.base import find_owned_document, stringify_id, to_object_id

# Only the fields the list endpoint returns; `raw_text`, extracted content and
# storage identifiers stay in the database.
LIST_PROJECTION = {
    "filename": 1,
    "file_size": 1,
    "mime_type": 1,
    "created_at": 1,
    "page_count": 1,
    "ocr_pages": 1,
    "analysis.status": 1,
    "previews.page": 1,
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
            .find(
                {"user_id": user_id, "analysis.status": {"$ne": "deleting"}},
                LIST_PROJECTION,
            )
            .sort("created_at", -1)
            .limit(limit)
        )
        return [stringify_id(doc) async for doc in cursor]

    async def find_owned(
        self, db: AsyncIOMotorDatabase, resume_id: str, user_id: str
    ) -> dict | None:
        return await find_owned_document(db, self.collection_name, resume_id, user_id)

    async def find_by_sha(
        self, db: AsyncIOMotorDatabase, user_id: str, sha256: str
    ) -> dict | None:
        if not sha256:
            return None
        doc = await db[self.collection_name].find_one(
            {
                "user_id": user_id,
                "sha256": sha256,
                "analysis.status": {"$ne": "deleting"},
            }
        )
        return stringify_id(doc) if doc else None

    async def update_fields(
        self,
        db: AsyncIOMotorDatabase,
        resume_id: str,
        user_id: str,
        fields: dict[str, Any],
    ) -> bool:
        object_id = to_object_id(resume_id)
        if object_id is None:
            return False
        result = await db[self.collection_name].update_one(
            {"_id": object_id, "user_id": user_id},
            {"$set": fields},
        )
        return bool(result.matched_count)

    async def delete(
        self, db: AsyncIOMotorDatabase, resume_id: str, user_id: str
    ) -> None:
        object_id = to_object_id(resume_id)
        if object_id is None:
            return
        await db[self.collection_name].delete_one(
            {"_id": object_id, "user_id": user_id}
        )


resume_repository = ResumeRepository()
