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
        # Content-addressed deduplication is per user. Legacy documents have no
        # sha256 and are deliberately excluded from the unique index.
        await db.resumes.create_index(
            [("user_id", 1), ("sha256", 1)],
            unique=True,
            name="ux_resumes_user_sha256",
            partialFilterExpression={"sha256": {"$type": "string"}},
        )
        await db.resumes.create_index(
            [("analysis.status", 1), ("created_at", 1)],
            name="ix_resumes_analysis_status",
        )
        # GridFS assets carry the owning resume id in metadata for cleanup and
        # orphan reconciliation.
        for bucket in (
            settings.resume_bucket_name,
            settings.resume_preview_bucket_name,
        ):
            await db[f"{bucket}.files"].create_index(
                "metadata.resume_id", name="ix_resume_assets_resume_id"
            )
        await db.job_descriptions.create_index("user_id", name="ix_job_descriptions_user_id")
        await db.job_descriptions.create_index(
            [("user_id", 1), ("created_at", -1)], name="ix_jd_user_created"
        )
        await db.interviews.create_index("user_id", name="ix_interviews_user_id")
        await db.interviews.create_index(
            [("user_id", 1), ("created_at", -1)], name="ix_interviews_user_created"
        )
        await db.interviews.create_index(
            [("user_id", 1), ("status", 1), ("completed_at", -1)],
            name="ix_interviews_user_status_completed",
        )
        await db.templates.create_index("user_id", name="ix_templates_user_id")
        await db.templates.create_index(
            [("user_id", 1), ("created_at", -1)], name="ix_templates_user_created"
        )
        await db.jobs.create_index("user_id", name="ix_jobs_user_id")
        await db.jobs.create_index(
            [("user_id", 1), ("created_at", -1)], name="ix_jobs_user_created"
        )
        await db.screening_invitations.create_index(
            "token_hash", unique=True, name="ux_screening_invitations_token"
        )
        await db.screening_invitations.create_index(
            [("job_id", 1), ("created_at", -1)],
            name="ix_screening_invitations_job_created",
        )
        await db.staff_invitations.create_index(
            "token_hash", unique=True, name="ux_staff_invitations_token"
        )
        await db.staff_invitations.create_index(
            [("email", 1), ("status", 1)], name="ix_staff_invitations_email_status"
        )
        await db.audit_logs.create_index([("created_at", -1)], name="ix_audit_logs_created")
        # API keys are looked up by their non-secret prefix; the prefix is
        # unique because it embeds random bytes.
        await db.api_keys.create_index(
            "prefix", unique=True, name="ux_api_keys_prefix"
        )
        await db.api_keys.create_index(
            [("created_by", 1), ("created_at", -1)], name="ix_api_keys_owner_created"
        )
        # Background job queue: the claim query filters by status and due time.
        await db[settings.jobs_collection_name].create_index(
            [("status", 1), ("run_at", 1)], name="ix_jobs_status_run_at"
        )
        # LLM usage/cost records are queried by time window.
        await db.llm_usage.create_index(
            [("created_at", -1)], name="ix_llm_usage_created"
        )
        # Per-role quota counters: one document per actor/action/day. The unique
        # index makes the increment upsert safe; the TTL index retires old days.
        await db.quota_usage.create_index(
            [("actor_id", 1), ("action", 1), ("window_start", 1)],
            unique=True,
            name="ux_quota_actor_action_window",
        )
        await db.quota_usage.create_index(
            "window_start", expireAfterSeconds=90 * 24 * 3600, name="ttl_quota_window"
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
