from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.models.answer import Answer
from app.models.interview import Interview, Question
from app.models.report import Report
from app.repositories.base import find_owned_document, stringify_id, to_object_id

# Only the fields the list endpoint returns; the per-question texts stay in
# the database and are loaded on demand by the detail endpoint.
LIST_PROJECTION = {
    "role": 1,
    "type": 1,
    "difficulty": 1,
    "status": 1,
    "target_questions": 1,
    "created_at": 1,
    "questions.id": 1,
    "answers.id": 1,
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

    async def find_by_question(
        self, db: AsyncIOMotorDatabase, question_id: str, user_id: str
    ) -> dict | None:
        """Locate the interview that owns an embedded question."""
        doc = await db[self.collection_name].find_one(
            {"user_id": user_id, "questions.id": question_id}
        )
        return stringify_id(doc) if doc else None

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

    async def record_answer(
        self,
        db: AsyncIOMotorDatabase,
        interview_id: str,
        user_id: str,
        answer: Answer,
        next_question: Question | None,
        completing: bool,
    ) -> dict | None:
        """Persist the scored answer, the next question, and/or completion.

        The filter pins `current_question_id` to the answered question, so a
        duplicate submission (or a concurrent answer) loses the race and
        receives `None` instead of recording the answer twice.
        """
        object_id = to_object_id(interview_id)
        if object_id is None:
            return None

        push: dict[str, object] = {"answers": answer.model_dump()}
        set_ops: dict[str, object] = {}
        if next_question is not None:
            push["questions"] = next_question.model_dump()
            set_ops["current_question_id"] = next_question.id
        if completing:
            set_ops["status"] = "completed"
            set_ops["completed_at"] = datetime.now(UTC)

        update: dict[str, object] = {"$push": push}
        if set_ops:
            update["$set"] = set_ops

        doc = await db[self.collection_name].find_one_and_update(
            {
                "_id": object_id,
                "user_id": user_id,
                "status": "in_progress",
                "current_question_id": answer.question_id,
            },
            update,
            return_document=ReturnDocument.AFTER,
        )
        return self._shape(doc) if doc else None

    async def set_report(
        self, db: AsyncIOMotorDatabase, interview_id: str, user_id: str, report: Report
    ) -> dict | None:
        """Cache the final report exactly once, on a completed interview.

        `report: None` matches both a missing field and an explicit null, so
        documents written before reports existed qualify too. A caller that
        gets `None` back should re-read: another request stored its report
        first (or the interview is gone / not completed).
        """
        object_id = to_object_id(interview_id)
        if object_id is None:
            return None
        doc = await db[self.collection_name].find_one_and_update(
            {
                "_id": object_id,
                "user_id": user_id,
                "status": "completed",
                "report": None,
            },
            {"$set": {"report": report.model_dump()}},
            return_document=ReturnDocument.AFTER,
        )
        return self._shape(doc) if doc else None

    @staticmethod
    def _shape(doc: dict[str, Any]) -> dict:
        """Expose `_id` as a string for the Pydantic model."""
        return stringify_id(doc)


interview_repository = InterviewRepository()
