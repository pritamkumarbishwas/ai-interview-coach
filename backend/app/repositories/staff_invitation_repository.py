from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.collection import ReturnDocument

from app.models.staff_invitation import StaffInvitation
from app.repositories.base import stringify_id, to_object_id

LIST_PROJECTION = {
    "email": 1,
    "role": 1,
    "status": 1,
    "expires_at": 1,
    "created_at": 1,
}


class StaffInvitationRepository:
    collection_name = "staff_invitations"

    async def insert(self, db: AsyncIOMotorDatabase, invitation: StaffInvitation) -> str:
        doc = invitation.model_dump(by_alias=True, exclude={"id"})
        result = await db[self.collection_name].insert_one(doc)
        return str(result.inserted_id)

    async def list_recent(self, db: AsyncIOMotorDatabase, limit: int) -> list[dict]:
        cursor = (
            db[self.collection_name]
            .find({}, LIST_PROJECTION)
            .sort("created_at", -1)
            .limit(limit)
        )
        return [stringify_id(doc) async for doc in cursor]

    async def find_by_token_hash(
        self, db: AsyncIOMotorDatabase, token_hash: str
    ) -> dict | None:
        doc = await db[self.collection_name].find_one({"token_hash": token_hash})
        return stringify_id(doc) if doc else None

    async def find_owned(
        self, db: AsyncIOMotorDatabase, invitation_id: str
    ) -> dict | None:
        object_id = to_object_id(invitation_id)
        if object_id is None:
            return None
        doc = await db[self.collection_name].find_one({"_id": object_id})
        return stringify_id(doc) if doc else None

    async def revoke_pending_for_email(self, db: AsyncIOMotorDatabase, email: str) -> None:
        await db[self.collection_name].update_many(
            {"email": email, "status": "pending"},
            {"$set": {"status": "revoked"}},
        )

    async def mark_accepted(self, db: AsyncIOMotorDatabase, invitation_id: str) -> None:
        object_id = to_object_id(invitation_id)
        if object_id is None:
            return
        await db[self.collection_name].update_one(
            {"_id": object_id},
            {"$set": {"status": "accepted", "accepted_at": datetime.now(UTC)}},
        )

    async def revoke(self, db: AsyncIOMotorDatabase, invitation_id: str) -> dict | None:
        object_id = to_object_id(invitation_id)
        if object_id is None:
            return None
        doc = await db[self.collection_name].find_one_and_update(
            {"_id": object_id, "status": "pending"},
            {"$set": {"status": "revoked"}},
            return_document=ReturnDocument.AFTER,
        )
        return stringify_id(doc) if doc else None


staff_invitation_repository = StaffInvitationRepository()
