"""Helpers shared by the repository modules.

Repositories own every MongoDB query in the application; routers and services
never talk to the database directly.
"""

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase


def to_object_id(value: str | None) -> ObjectId | None:
    """Parse a string id, or return `None` when it is not a valid ObjectId."""
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None


def stringify_id(doc: dict) -> dict:
    """Expose `_id` as a string (the alias the models use) and return `doc`."""
    doc["_id"] = str(doc["_id"])
    return doc


async def find_owned_document(
    db: AsyncIOMotorDatabase,
    collection: str,
    document_id: str,
    user_id: str,
    owner_field: str = "user_id",
) -> dict | None:
    """Fetch one document owned by `user_id`, or `None` if missing.

    Returns `None` for invalid ids too, so callers only handle one failure
    case and cannot read another user's data. ``owner_field`` names the column
    that records the owner (most collections use ``user_id``; candidate
    invitations track the recruiter in ``created_by``).
    """
    object_id = to_object_id(document_id)
    if object_id is None:
        return None
    doc = await db[collection].find_one({"_id": object_id, owner_field: user_id})
    return stringify_id(doc) if doc else None
