from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.models.interview import Interview, Question
from app.repositories.base import find_owned_document, stringify_id, to_object_id

# Only the fields the list endpoint returns; the per-question texts stay in
# the database and are loaded on demand by the detail endpoint.
LIST_PROJECTION = {
    "role": 1,
    "type": 1,
    "difficulty": 1,
    "status": 1,
    "created_at": 1,
    "questions.id": 1,
}


class InterviewRepository:
    collection_name = "interviews"

    async def insert(self, db: AsyncIOMotorDatabase, interview: Interview) -> str:
        doc = interview.model_dump(by_alias=True, exclude={"id"})
        result = await db[self.collection_name].insert_one(doc)
        return str(result.inserted_id)

    async def list_for_user(self, db: AsyncIOMotorDatabase, user_id: str, limit: int) -> list[dict]:
        cursor = (
            db[self.collection_name]
            .find({"user_id": user_id}, LIST_PROJECTION)
            .sort("created_at", -1)
            .limit(limit)
        )
        return [self._shape(doc) async for doc in cursor]

    async def find_owned(
        self, db: AsyncIOMotorDatabase, interview_id: str, user_id: str
    ) -> dict | None:
        return await find_owned_document(db, self.collection_name, interview_id, user_id)

    async def start(
        self,
        db: AsyncIOMotorDatabase,
        interview_id: str,
        user_id: str,
        question: Question,
    ) -> dict | None:
        """Transition `created -> in_progress` and record the first question.

        The status filter makes the transition atomic: a concurrent start
        loses the race and receives `None` (the caller turns that into a 409).
        """
        object_id = to_object_id(interview_id)
        if object_id is None:
            return None
        doc = await db[self.collection_name].find_one_and_update(
            {"_id": object_id, "user_id": user_id, "status": "created"},
            {
                "$set": {
                    "status": "in_progress",
                    "started_at": datetime.now(UTC),
                    "current_question_id": question.id,
                },
                "$push": {"questions": question.model_dump()},
            },
            return_document=ReturnDocument.AFTER,
        )
        return self._shape(doc) if doc else None

    async def append_question(
        self,
        db: AsyncIOMotorDatabase,
        interview_id: str,
        user_id: str,
        question: Question,
    ) -> dict | None:
        """Attach the next question to an `in_progress` interview."""
        object_id = to_object_id(interview_id)
        if object_id is None:
            return None
        doc = await db[self.collection_name].find_one_and_update(
            {"_id": object_id, "user_id": user_id, "status": "in_progress"},
            {
                "$push": {"questions": question.model_dump()},
                "$set": {"current_question_id": question.id},
            },
            return_document=ReturnDocument.AFTER,
        )
        return self._shape(doc) if doc else None

    async def delete(self, db: AsyncIOMotorDatabase, interview_id: str, user_id: str) -> None:
        object_id = to_object_id(interview_id)
        if object_id is None:
            return
        await db[self.collection_name].delete_one({"_id": object_id, "user_id": user_id})

    @staticmethod
    def _shape(doc: dict[str, Any]) -> dict:
        """Expose `_id` as a string for the Pydantic model."""
        return stringify_id(doc)


interview_repository = InterviewRepository()
