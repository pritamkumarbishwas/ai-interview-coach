from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.models.invitation import ScreeningInvitation
from app.repositories.base import find_owned_document, stringify_id, to_object_id

LIST_PROJECTION = {
    "job_id": 1,
    "candidate_name": 1,
    "candidate_email": 1,
    "role": 1,
    "status": 1,
    "expires_at": 1,
    "interview_id": 1,
    "created_at": 1,
    "round_minutes": 1,
    "round_deadline": 1,
    "pass_threshold": 1,
    "decision": 1,
    "decision_note": 1,
    "decided_at": 1,
}


class InvitationRepository:
    collection_name = "screening_invitations"

    async def insert(self, db: AsyncIOMotorDatabase, invitation: ScreeningInvitation) -> str:
        doc = invitation.model_dump(by_alias=True, exclude={"id"})
        result = await db[self.collection_name].insert_one(doc)
        return str(result.inserted_id)

    async def find_by_token_hash(
        self, db: AsyncIOMotorDatabase, token_hash: str
    ) -> dict | None:
        doc = await db[self.collection_name].find_one({"token_hash": token_hash})
        return stringify_id(doc) if doc else None

    async def find_owned(
        self, db: AsyncIOMotorDatabase, invitation_id: str, user_id: str
    ) -> dict | None:
        return await find_owned_document(
            db, self.collection_name, invitation_id, user_id, owner_field="created_by"
        )

    async def get_by_id(
        self, db: AsyncIOMotorDatabase, invitation_id: str
    ) -> dict | None:
        """Fetch an invitation regardless of owner (background handlers)."""
        object_id = to_object_id(invitation_id)
        if object_id is None:
            return None
        doc = await db[self.collection_name].find_one({"_id": object_id})
        return stringify_id(doc) if doc else None

    async def list_for_job(
        self, db: AsyncIOMotorDatabase, job_id: str, limit: int
    ) -> list[dict]:
        cursor = (
            db[self.collection_name]
            .find({"job_id": job_id}, LIST_PROJECTION)
            .sort("created_at", -1)
            .limit(limit)
        )
        return [stringify_id(doc) async for doc in cursor]

    async def mark_started(
        self,
        db: AsyncIOMotorDatabase,
        invitation_id: str,
        interview_id: str,
        round_deadline: datetime,
    ) -> None:
        object_id = to_object_id(invitation_id)
        if object_id is None:
            return
        await db[self.collection_name].update_one(
            {"_id": object_id},
            {
                "$set": {
                    "status": "started",
                    "interview_id": interview_id,
                    "round_deadline": round_deadline,
                    "started_at": datetime.now(UTC),
                }
            },
        )

    async def rotate_token(
        self, db: AsyncIOMotorDatabase, invitation_id: str, token_hash: str
    ) -> None:
        """Replace the stored token hash (used when re-sending an invite)."""
        object_id = to_object_id(invitation_id)
        if object_id is None:
            return
        await db[self.collection_name].update_one(
            {"_id": object_id}, {"$set": {"token_hash": token_hash}}
        )

    async def set_status(
        self, db: AsyncIOMotorDatabase, invitation_id: str, status: str
    ) -> None:
        object_id = to_object_id(invitation_id)
        if object_id is None:
            return
        fields: dict = {"status": status}
        if status == "completed":
            fields["completed_at"] = datetime.now(UTC)
        await db[self.collection_name].update_one({"_id": object_id}, {"$set": fields})

    async def set_deadline(
        self,
        db: AsyncIOMotorDatabase,
        invitation_id: str,
        round_deadline: datetime,
    ) -> None:
        """Move the server-authoritative round deadline (time accommodation)."""
        object_id = to_object_id(invitation_id)
        if object_id is None:
            return
        await db[self.collection_name].update_one(
            {"_id": object_id}, {"$set": {"round_deadline": round_deadline}}
        )

    async def add_round_minutes(
        self, db: AsyncIOMotorDatabase, invitation_id: str, minutes: int
    ) -> dict | None:
        """Increase the per-round budget before the round has started.

        A pending invitation has no deadline yet — the budget is applied when
        the candidate starts, so extending it must change `round_minutes`
        rather than a deadline that `start` would overwrite.
        """
        object_id = to_object_id(invitation_id)
        if object_id is None:
            return None
        doc = await db[self.collection_name].find_one_and_update(
            {"_id": object_id},
            {"$inc": {"round_minutes": minutes}},
            return_document=ReturnDocument.AFTER,
        )
        return stringify_id(doc) if doc else None

    async def set_decision(
        self,
        db: AsyncIOMotorDatabase,
        invitation_id: str,
        decision: str,
        note: str,
        decided_by: str,
    ) -> None:
        """Record a human decision (never a candidate-visible field)."""
        object_id = to_object_id(invitation_id)
        if object_id is None:
            return
        await db[self.collection_name].update_one(
            {"_id": object_id},
            {
                "$set": {
                    "decision": decision,
                    "decision_note": note,
                    "decided_by": decided_by,
                    "decided_at": datetime.now(UTC),
                }
            },
        )

    async def delete(self, db: AsyncIOMotorDatabase, invitation_id: str, user_id: str) -> None:
        object_id = to_object_id(invitation_id)
        if object_id is None:
            return
        await db[self.collection_name].delete_one(
            {"_id": object_id, "created_by": user_id}
        )

    async def mark_erased(
        self, db: AsyncIOMotorDatabase, invitation_id: str, fields: dict
    ) -> None:
        """Anonymize an invitation and stamp `erased_at` (idempotent)."""
        object_id = to_object_id(invitation_id)
        if object_id is None:
            return
        await db[self.collection_name].update_one({"_id": object_id}, {"$set": fields})

    async def list_erasable(
        self, db: AsyncIOMotorDatabase, cutoff: datetime, limit: int
    ) -> list[dict]:
        """Invitations whose session data is past the retention window.

        Completed/expired/revoked rows with no `erased_at` whose completion (or,
        for rows with no completion timestamp, creation) predates `cutoff`.
        """
        query = {
            "erased_at": None,
            "status": {"$in": ["completed", "expired", "revoked"]},
            "$or": [
                {"completed_at": {"$lt": cutoff}},
                {"completed_at": None, "created_at": {"$lt": cutoff}},
            ],
        }
        cursor = (
            db[self.collection_name].find(query).sort("completed_at", 1).limit(limit)
        )
        return [stringify_id(doc) async for doc in cursor]


invitation_repository = InvitationRepository()
