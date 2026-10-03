from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError
from pymongo.collection import ReturnDocument

from app.core.exceptions import ConflictError
from app.models.user import User
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
    ) -> User:
        user = User(
            name=name.strip(),
            email=email.strip().lower(),
            password_hash=password_hash,
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
