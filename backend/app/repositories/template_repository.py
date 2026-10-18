from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.collection import ReturnDocument

from app.models.template import InterviewTemplate
from app.repositories.base import find_owned_document, stringify_id, to_object_id


class TemplateRepository:
    collection_name = "templates"

    async def insert(self, db: AsyncIOMotorDatabase, template: InterviewTemplate) -> str:
        doc = template.model_dump(by_alias=True, exclude={"id"})
        result = await db[self.collection_name].insert_one(doc)
        return str(result.inserted_id)

    async def list_for_user(
        self, db: AsyncIOMotorDatabase, user_id: str, limit: int
    ) -> list[dict]:
        """Summaries only: counts, not the full rounds and question bank.

        The sizes are computed in the database so a large question bank never
        travels to the API just to be counted.
        """
        cursor = db[self.collection_name].aggregate(
            [
                {"$match": {"user_id": user_id}},
                {"$sort": {"created_at": -1}},
                {"$limit": limit},
                {
                    "$project": {
                        "name": 1,
                        "description": 1,
                        "created_at": 1,
                        "proctoring_mode": "$config.proctoring_mode",
                        "round_count": {"$size": {"$ifNull": ["$config.rounds", []]}},
                        "question_count": {"$size": {"$ifNull": ["$question_bank", []]}},
                    }
                },
            ]
        )
        return [stringify_id(doc) async for doc in cursor]

    async def find_owned(
        self, db: AsyncIOMotorDatabase, template_id: str, user_id: str
    ) -> dict | None:
        return await find_owned_document(db, self.collection_name, template_id, user_id)

    async def update(
        self, db: AsyncIOMotorDatabase, template_id: str, user_id: str, fields: dict
    ) -> dict | None:
        object_id = to_object_id(template_id)
        if object_id is None:
            return None
        fields["updated_at"] = datetime.now(UTC)
        doc = await db[self.collection_name].find_one_and_update(
            {"_id": object_id, "user_id": user_id},
            {"$set": fields},
            return_document=ReturnDocument.AFTER,
        )
        return stringify_id(doc) if doc else None

    async def delete(self, db: AsyncIOMotorDatabase, template_id: str, user_id: str) -> None:
        object_id = to_object_id(template_id)
        if object_id is None:
            return
        await db[self.collection_name].delete_one({"_id": object_id, "user_id": user_id})


template_repository = TemplateRepository()
