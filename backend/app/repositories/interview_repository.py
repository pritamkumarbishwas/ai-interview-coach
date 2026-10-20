from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.models.answer import Answer, Evaluation
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
    "proctoring_mode": 1,
    "target_questions": 1,
    "created_at": 1,
    "questions.id": 1,
    "answers.id": 1,
}

# Dashboard stats need counts plus the cached report's scores/topics — never
# the question or answer bodies themselves.
DASHBOARD_PROJECTION = {
    "role": 1,
    "type": 1,
    "difficulty": 1,
    "status": 1,
    "proctoring_mode": 1,
    "target_questions": 1,
    "created_at": 1,
    "answers.id": 1,
    "report.overall_score": 1,
    "report.strong_topics": 1,
    "report.weak_topics": 1,
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

    async def all_for_user(self, db: AsyncIOMotorDatabase, user_id: str) -> list[dict]:
        """Every interview for the dashboard, newest first, without bodies."""
        cursor = (
            db[self.collection_name]
            .find({"user_id": user_id}, DASHBOARD_PROJECTION)
            .sort("created_at", -1)
        )
        return [self._shape(doc) async for doc in cursor]

    async def find_owned(
        self, db: AsyncIOMotorDatabase, interview_id: str, user_id: str
    ) -> dict | None:
        return await find_owned_document(db, self.collection_name, interview_id, user_id)

    async def get_by_id(
        self, db: AsyncIOMotorDatabase, interview_id: str
    ) -> dict | None:
        """Fetch by id regardless of owner (admin/cleanup paths only)."""
        object_id = to_object_id(interview_id)
        if object_id is None:
            return None
        doc = await db[self.collection_name].find_one({"_id": object_id})
        return stringify_id(doc) if doc else None

    async def active_ids_for_resume(
        self, db: AsyncIOMotorDatabase, user_id: str, resume_id: str
    ) -> list[str]:
        """Ids of interviews that still reference a resume and are unfinished."""
        cursor = db[self.collection_name].find(
            {
                "user_id": user_id,
                "resume_id": resume_id,
                "status": {"$in": ["created", "in_progress"]},
            },
            {"_id": 1},
        )
        return [str(doc["_id"]) async for doc in cursor]

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

    async def set_answer_evaluation(
        self,
        db: AsyncIOMotorDatabase,
        interview_id: str,
        user_id: str,
        answer_id: str,
        evaluation: Evaluation,
    ) -> bool:
        """Persist one answer's evaluation (incremental, deferred pipeline).

        Uses `$set` with `arrayFilters` to target only the matching answer
        element, so concurrent per-answer writes never clobber each other.
        Returns True if an answer was updated.
        """
        object_id = to_object_id(interview_id)
        if object_id is None:
            return False
        result = await db[self.collection_name].update_one(
            {
                "_id": object_id,
                "user_id": user_id,
                "answers": {"$elemMatch": {"id": answer_id, "evaluation": None}},
            },
            {
                "$set": {
                    "answers.$[el].evaluation": evaluation.model_dump(),
                }
            },
            array_filters=[{"el.id": answer_id}],
        )
        return result.modified_count == 1

    async def set_recording_meta(
        self,
        db: AsyncIOMotorDatabase,
        interview_id: str,
        user_id: str,
        kind: str,
        meta: dict,
    ) -> dict | None:
        """Upsert one recording's metadata onto the interview document."""
        object_id = to_object_id(interview_id)
        if object_id is None:
            return None
        doc = await db[self.collection_name].find_one_and_update(
            {"_id": object_id, "user_id": user_id},
            {"$set": {f"recordings.{kind}": meta}},
            return_document=ReturnDocument.AFTER,
        )
        return self._shape(doc) if doc else None
    async def update_proctoring_session(
        self, db: AsyncIOMotorDatabase, interview_id: str, user_id: str, session: dict
    ) -> dict | None:
        object_id = to_object_id(interview_id)
        if object_id is None:
            return None
        doc = await db[self.collection_name].find_one_and_update(
            {"_id": object_id, "user_id": user_id},
            {"$set": {"proctoring_session": session}},
            return_document=ReturnDocument.AFTER,
        )
        return self._shape(doc) if doc else None

    async def push_proctoring_event(
        self, db: AsyncIOMotorDatabase, interview_id: str, user_id: str, event: dict
    ) -> bool:
        """Append one proctoring event to the session (race-safe `$push`)."""
        object_id = to_object_id(interview_id)
        if object_id is None:
            return False
        result = await db[self.collection_name].update_one(
            {"_id": object_id, "user_id": user_id},
            {"$push": {"proctoring_session.events": event}},
        )
        return result.matched_count > 0

    async def delete_by_id(self, db: AsyncIOMotorDatabase, interview_id: str) -> bool:
        """Hard-delete an interview (used by candidate erasure/retention)."""
        object_id = to_object_id(interview_id)
        if object_id is None:
            return False
        result = await db[self.collection_name].delete_one({"_id": object_id})
        return result.deleted_count > 0

    @staticmethod
    def _shape(doc: dict[str, Any]) -> dict:
        """Expose `_id` as a string for the Pydantic model."""
        return stringify_id(doc)


interview_repository = InterviewRepository()
