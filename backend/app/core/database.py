import logging
from collections.abc import AsyncGenerator

from fastapi import Request
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings

logger = logging.getLogger(__name__)

_indexes_ready = False


async def connect_to_mongo() -> AsyncIOMotorClient:
    """Create the application-wide client.

    The client is created inside the lifespan coroutine so it is bound to the
    running event loop and shared by every request instead of opening a fresh
    connection pool per request.
    """
    return AsyncIOMotorClient(settings.mongo_uri)


async def close_mongo(client: AsyncIOMotorClient | None) -> None:
    if client is not None:
        client.close()


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create the indexes the queries rely on (idempotent)."""
    global _indexes_ready
    if _indexes_ready:
        return
    try:
        await db.users.create_index("email", unique=True, name="ux_users_email")
        await db.resumes.create_index("user_id", name="ix_resumes_user_id")
        await db.resumes.create_index(
            [("user_id", 1), ("created_at", -1)], name="ix_resumes_user_created"
        )
        await db.job_descriptions.create_index("user_id", name="ix_job_descriptions_user_id")
        await db.job_descriptions.create_index(
            [("user_id", 1), ("created_at", -1)], name="ix_jd_user_created"
        )
    except Exception as exc:
        # If this fails, the application cannot safely enforce uniqueness constraints.
        logger.critical("Could not create MongoDB indexes: %s", exc)
        raise RuntimeError("Database index creation failed") from exc
    _indexes_ready = True


async def get_db(request: Request) -> AsyncGenerator[AsyncIOMotorDatabase, None]:
    """FastAPI dependency yielding the database of the shared client."""
    client: AsyncIOMotorClient | None = getattr(request.app.state, "mongo", None)
    if client is None:  # pragma: no cover - lifespan always runs first
        raise RuntimeError("MongoDB client is not initialised")
    yield client[settings.mongo_db_name]
