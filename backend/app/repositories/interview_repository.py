import re
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
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
    "kind": 1,
    "type": 1,
    "difficulty": 1,
    "status": 1,
    "proctoring_mode": 1,
    "target_questions": 1,
    "created_at": 1,
    "completed_at": 1,
    "questions.id": 1,
    "answers.id": 1,
    "report.overall_score": 1,
}

# Dashboard stats need counts plus the cached report's scores/topics — never
# the question or answer bodies themselves.
RECENT_PROJECTION = {
    "role": 1,
    "kind": 1,
    "type": 1,
    "difficulty": 1,
    "status": 1,
    "target_questions": 1,
    "created_at": 1,
    "answered_count": {"$size": {"$ifNull": ["$answers", []]}},
    "score": {
        "$cond": [
            {"$isNumber": "$report.overall_score"},
            "$report.overall_score",
            None,
        ]
    },
}

TOPIC_GROUP = [
    {"$group": {"_id": "$topic", "count": {"$sum": 1}}},
    {"$sort": {"count": -1, "_id": 1}},
]


class InterviewRepository:
    collection_name = "interviews"

    async def insert(self, db: AsyncIOMotorDatabase, interview: Interview) -> str:
        doc = interview.model_dump(by_alias=True, exclude={"id"})
        result = await db[self.collection_name].insert_one(doc)
        return str(result.inserted_id)

    async def list_for_user(
        self,
        db: AsyncIOMotorDatabase,
        user_id: str,
        limit: int,
        *,
        offset: int = 0,
        status: str | None = None,
        interview_type: str | None = None,
        query: str | None = None,
    ) -> tuple[list[dict], int]:
        """One page of the user's interviews plus the unpaginated total.

        Filters live in the query so pagination stays correct: filtering in the
        client would only see the current page.
        """
        match: dict[str, Any] = {"user_id": user_id}
        if status:
            match["status"] = status
        if interview_type:
            match["type"] = interview_type
        needle = (query or "").strip()
        if needle:
            match["role"] = {"$regex": re.escape(needle), "$options": "i"}

        collection = db[self.collection_name]
        total = await collection.count_documents(match)
        cursor = (
            collection.find(match, LIST_PROJECTION)
            .sort([("created_at", -1), ("_id", -1)])
            .skip(offset)
            .limit(limit)
        )
        return [self._shape(doc) async for doc in cursor], total

    async def stats_for_user(
        self,
        db: AsyncIOMotorDatabase,
        user_id: str,
        *,
        recent_limit: int,
        topic_limit: int,
    ) -> dict:
        """Aggregate the dashboard in one round trip, without loading bodies."""
        pipeline = [
            {"$match": {"user_id": user_id}},
            {
                "$facet": {
                    "summary": [
                        {
                            "$group": {
                                "_id": None,
                                "total": {"$sum": 1},
                                "completed": {
                                    "$sum": {
                                        "$cond": [
                                            {"$eq": ["$status", "completed"]},
                                            1,
                                            0,
                                        ]
                                    }
                                },
                                "in_progress": {
                                    "$sum": {
                                        "$cond": [
                                            {"$eq": ["$status", "in_progress"]},
                                            1,
                                            0,
                                        ]
                                    }
                                },
                                "not_started": {
                                    "$sum": {
                                        "$cond": [
                                            {"$eq": ["$status", "created"]},
                                            1,
                                            0,
                                        ]
                                    }
                                },
                                "questions_answered": {
                                    "$sum": {"$size": {"$ifNull": ["$answers", []]}}
                                },
                            }
                        }
                    ],
                    "scores": [
                        {
                            "$match": {
                                "status": "completed",
                                "report.overall_score": {"$type": "number"},
                            }
                        },
                        {
                            "$group": {
                                "_id": None,
                                "scored_count": {"$sum": 1},
                                "average_score": {"$avg": "$report.overall_score"},
                            }
                        },
                    ],
                    "strong_topics": [
                        {"$match": {"status": "completed"}},
                        {
                            "$project": {
                                "_id": 0,
                                "topic": {"$ifNull": ["$report.strong_topics", []]},
                            }
                        },
                        {"$unwind": "$topic"},
                        *TOPIC_GROUP,
                        {"$limit": topic_limit},
                    ],
                    "weak_topics": [
                        {"$match": {"status": "completed"}},
                        {
                            "$project": {
                                "_id": 0,
                                "topic": {"$ifNull": ["$report.weak_topics", []]},
                            }
                        },
                        {"$unwind": "$topic"},
                        *TOPIC_GROUP,
                        {"$limit": topic_limit},
                    ],
                    "recent": [
                        {"$sort": {"created_at": -1, "_id": -1}},
                        {"$limit": recent_limit},
                        {"$project": RECENT_PROJECTION},
                    ],
                    "active": [
                        {
                            "$match": {
                                "status": {"$in": ["created", "in_progress"]}
                            }
                        },
                        {"$sort": {"created_at": -1, "_id": -1}},
                        {"$limit": 1},
                        {
                            "$project": {
                                "role": 1,
                                "status": 1,
                                "created_at": 1,
                            }
                        },
                    ],
                }
            },
        ]
        rows = [row async for row in db[self.collection_name].aggregate(pipeline)]
        if not rows:
            return {}
        facets = rows[0]
        for key in ("recent", "active"):
            facets[key] = [self._shape(doc) for doc in facets.get(key) or []]
        return facets

    async def results_for_user(
        self,
        db: AsyncIOMotorDatabase,
        user_id: str,
        sort: str,
        limit: int,
    ) -> tuple[list[dict], dict]:
        """Completed interviews plus aggregate score stats, in one query.

        Aggregation happens server-side across every completed interview, so
        the stats stay correct even though the response only returns `limit`
        rows. Unscored reports are ordered after scored ones and excluded from
        the average/best by MongoDB's numeric aggregators.
        """
        sort_specs = {
            "recent": {"completed_at": -1, "created_at": -1},
            "score_desc": {
                "_has_score": -1,
                "report.overall_score": -1,
                "completed_at": -1,
            },
            "score_asc": {
                "_has_score": -1,
                "report.overall_score": 1,
                "completed_at": -1,
            },
        }
        pipeline = [
            {"$match": {"user_id": user_id, "status": "completed"}},
            {
                "$facet": {
                    "items": [
                        {
                            "$addFields": {
                                "_has_score": {"$isNumber": "$report.overall_score"}
                            }
                        },
                        {"$sort": sort_specs.get(sort, sort_specs["recent"])},
                        {"$limit": limit},
                        {"$project": LIST_PROJECTION},
                    ],
                    "stats": [
                        {
                            "$group": {
                                "_id": None,
                                "total": {"$sum": 1},
                                "scored_count": {
                                    "$sum": {
                                        "$cond": [
                                            {"$isNumber": "$report.overall_score"},
                                            1,
                                            0,
                                        ]
                                    }
                                },
                                "average_score": {
                                    "$avg": "$report.overall_score"
                                },
                                "best_score": {
                                    "$max": "$report.overall_score"
                                },
                            }
                        }
                    ],
                }
            },
        ]
        cursor = db[self.collection_name].aggregate(pipeline)
        rows = [row async for row in cursor]
        if not rows:
            return [], {}
        facets = rows[0]
        stats_list = facets.get("stats") or []
        stats = stats_list[0] if stats_list else {}
        items = [self._shape(doc) for doc in facets.get("items") or []]
        return items, stats

    async def find_owned(
        self, db: AsyncIOMotorDatabase, interview_id: str, user_id: str
    ) -> dict | None:
        return await find_owned_document(db, self.collection_name, interview_id, user_id)

    async def count_active_for_jd(self, db: AsyncIOMotorDatabase, jd_id: str) -> int:
        """Interviews still using a job description (created or in progress)."""
        return await db[self.collection_name].count_documents(
            {"jd_id": jd_id, "status": {"$in": ["created", "in_progress"]}}
        )

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
        """Persist the answer, the next question, and/or completion.

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

    async def complete_early(
        self, db: AsyncIOMotorDatabase, interview_id: str, user_id: str
    ) -> dict | None:
        """Atomically finish an in-progress interview before the target count.

        The status filter makes completion and the final answer mutually
        exclusive: whichever loses the race gets `None` and can re-read the
        interview to return the idempotent completed state.
        """
        object_id = to_object_id(interview_id)
        if object_id is None:
            return None
        doc = await db[self.collection_name].find_one_and_update(
            {
                "_id": object_id,
                "user_id": user_id,
                "status": "in_progress",
            },
            {
                "$set": {
                    "status": "completed",
                    "completed_at": datetime.now(UTC),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return self._shape(doc) if doc else None

    async def set_report(
        self,
        db: AsyncIOMotorDatabase,
        interview_id: str,
        user_id: str,
        report: Report,
        *,
        replace: bool = False,
    ) -> dict | None:
        """Cache the final report on a completed interview.

        By default the write is insert-only (`report: None`), so concurrent
        callers generate at most one stored report. ``replace=True`` is used
        only to repair a legacy partial report after its missing evaluations
        have been backfilled successfully.
        """
        object_id = to_object_id(interview_id)
        if object_id is None:
            return None
        query: dict[str, object] = {
            "_id": object_id,
            "user_id": user_id,
            "status": "completed",
        }
        if not replace:
            query["report"] = None
        doc = await db[self.collection_name].find_one_and_update(
            query,
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

    async def clear_recording_meta(
        self, db: AsyncIOMotorDatabase, interview_id: str, user_id: str, kind: str
    ) -> bool:
        """Remove a recording's sealed metadata when a fresh upload starts."""
        object_id = to_object_id(interview_id)
        if object_id is None:
            return False
        result = await db[self.collection_name].update_one(
            {"_id": object_id, "user_id": user_id},
            {"$unset": {f"recordings.{kind}": ""}},
        )
        return result.matched_count > 0

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
        """Expose `_id` as a string for the Pydantic model.

        Legacy documents can predate `created_at`; the ObjectId embeds the
        insert time, so use it instead of failing response validation.
        """
        if doc.get("created_at") is None and isinstance(doc.get("_id"), ObjectId):
            doc["created_at"] = doc["_id"].generation_time
        return stringify_id(doc)


interview_repository = InterviewRepository()
