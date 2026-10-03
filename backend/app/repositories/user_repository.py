from datetime import UTC, datetime

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import ConflictError
from app.models.user import User


def _to_user(doc: dict) -> User:
    doc["_id"] = str(doc["_id"])
    return User(**doc)


class UserRepository:
    async def get_by_id(self, db: AsyncIOMotorDatabase, user_id: str) -> User | None:
        try:
            object_id = ObjectId(user_id)
        except (InvalidId, TypeError):
            return None
        doc = await db.users.find_one({"_id": object_id})
        return _to_user(doc) if doc else None

    async def get_by_email(self, db: AsyncIOMotorDatabase, email: str) -> User | None:
        doc = await db.users.find_one({"email": email.strip().lower()})
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
            result = await db.users.insert_one(doc)
        except DuplicateKeyError as exc:
            # Two concurrent registrations raced past the pre-insert lookup.
            raise ConflictError("An account with this email already exists") from exc
        user.id = str(result.inserted_id)
        return user

    async def update_password(self, db: AsyncIOMotorDatabase, user_id: str, new_hash: str) -> None:
        try:
            object_id = ObjectId(user_id)
        except (InvalidId, TypeError):
            return
        await db.users.update_one({"_id": object_id}, {"$set": {"password_hash": new_hash}})

    async def update_profile(self, db: AsyncIOMotorDatabase, user_id: str, *, name: str) -> None:
        try:
            object_id = ObjectId(user_id)
        except (InvalidId, TypeError):
            return
        await db.users.update_one(
            {"_id": object_id},
            {"$set": {"name": name.strip(), "updated_at": datetime.now(UTC)}},
        )


user_repository = UserRepository()
