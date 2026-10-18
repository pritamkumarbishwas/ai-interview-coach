from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.collection import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import ConflictError
from app.models.user import STAFF_ROLES, Role, User
from app.repositories.base import stringify_id, to_object_id


def _to_user(doc: dict) -> User:
    return User(**stringify_id(doc))


class UserRepository:
    collection_name = "users"

    async def get_by_id(self, db: AsyncIOMotorDatabase, user_id: str) -> User | None:
        object_id = to_object_id(user_id)
        if object_id is None:
            return None
        doc = await db[self.collection_name].find_one({"_id": object_id})
        return _to_user(doc) if doc else None

    async def get_by_email(self, db: AsyncIOMotorDatabase, email: str) -> User | None:
        doc = await db[self.collection_name].find_one({"email": email.strip().lower()})
        return _to_user(doc) if doc else None

    async def create(
        self,
        db: AsyncIOMotorDatabase,
        *,
        name: str,
        email: str,
        password_hash: str,
        role: Role = "candidate",
    ) -> User:
        user = User(
            name=name.strip(),
            email=email.strip().lower(),
            password_hash=password_hash,
            role=role,
        )
        doc = user.model_dump(by_alias=True, exclude={"id"})
        try:
            result = await db[self.collection_name].insert_one(doc)
        except DuplicateKeyError as exc:
            # Two concurrent registrations raced past the pre-insert lookup.
            raise ConflictError("An account with this email already exists") from exc
        user.id = str(result.inserted_id)
        return user

    async def update_password(self, db: AsyncIOMotorDatabase, user_id: str, new_hash: str) -> None:
        object_id = to_object_id(user_id)
        if object_id is None:
            return
        await db[self.collection_name].update_one(
            {"_id": object_id}, {"$set": {"password_hash": new_hash}}
        )

    async def list_staff(self, db: AsyncIOMotorDatabase, limit: int) -> list[User]:
        """Internal users only (admin/recruiter/reviewer), newest first."""
        cursor = (
            db[self.collection_name]
            .find({"role": {"$in": list(STAFF_ROLES)}})
            .sort("created_at", -1)
            .limit(limit)
        )
        return [_to_user(doc) async for doc in cursor]

    async def count_staff(self, db: AsyncIOMotorDatabase) -> int:
        """Number of provisioned staff accounts (admin/recruiter/reviewer)."""
        return await db[self.collection_name].count_documents(
            {"role": {"$in": list(STAFF_ROLES)}}
        )

    async def update_role(
        self, db: AsyncIOMotorDatabase, user_id: str, role: Role
    ) -> User | None:
        object_id = to_object_id(user_id)
        if object_id is None:
            return None
        doc = await db[self.collection_name].find_one_and_update(
            {"_id": object_id},
            {"$set": {"role": role, "updated_at": datetime.now(UTC)}},
            return_document=ReturnDocument.AFTER,
        )
        return _to_user(doc) if doc else None

    async def update_profile(
        self, db: AsyncIOMotorDatabase, user_id: str, *, name: str
    ) -> User | None:
        """Apply the profile change and return the updated document."""
        object_id = to_object_id(user_id)
        if object_id is None:
            return None
        doc = await db[self.collection_name].find_one_and_update(
            {"_id": object_id},
            {"$set": {"name": name.strip(), "updated_at": datetime.now(UTC)}},
            return_document=ReturnDocument.AFTER,
        )
        return _to_user(doc) if doc else None


user_repository = UserRepository()
