"""API-key lifecycle and authentication (Phase 8).

Keys are hashed at rest and verified with a constant-time comparison. The
auth path is deliberately cheap: one indexed lookup by prefix plus one hash
comparison. ``last_used_at`` is refreshed at most once a minute per key so a
high-traffic integration does not turn every read into a write.
"""

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.exceptions import AuthenticationError, NotFoundError
from app.models.api_key import KEY_PREFIX, KEY_SECRET_BYTES, ApiKey
from app.models.user import User
from app.repositories.api_key_repository import ApiKeyRepository
from app.schemas.api_key import ApiKeyCreate, ApiKeyCreated, ApiKeyOut

logger = logging.getLogger(__name__)

# Refresh `last_used_at` no more often than this.
TOUCH_INTERVAL_SECONDS = 60
# How much of the raw key is stored in plaintext for display/lookup.
PREFIX_LENGTH = len(KEY_PREFIX) + 8


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _naive_utc(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value


class ApiKeyService:
    def __init__(self, keys: ApiKeyRepository) -> None:
        self._keys = keys

    async def create(
        self, db: AsyncIOMotorDatabase, user: User, payload: ApiKeyCreate
    ) -> ApiKeyCreated:
        secret = secrets.token_urlsafe(KEY_SECRET_BYTES)
        raw = f"{KEY_PREFIX}{secret}"
        expires_at = (
            datetime.now(UTC) + timedelta(days=payload.expires_in_days)
            if payload.expires_in_days
            else None
        )
        api_key = ApiKey(
            name=payload.name.strip(),
            prefix=raw[:PREFIX_LENGTH],
            key_hash=_hash(raw),
            role=payload.role,
            created_by=user.id or "",
            expires_at=expires_at,
        )
        api_key.id = await self._keys.insert(db, api_key)
        logger.info("API key created id=%s name=%s", api_key.id, api_key.name)
        return ApiKeyCreated(key=raw, **self._to_out(api_key).model_dump())

    async def list(
        self, db: AsyncIOMotorDatabase, user: User, limit: int
    ) -> list[ApiKeyOut]:
        docs = await self._keys.list_for_user(db, user.id or "", limit)
        return [
            ApiKeyOut(
                id=doc["_id"],
                name=doc.get("name", ""),
                prefix=doc.get("prefix", ""),
                role=doc.get("role", "reviewer"),
                created_at=doc["created_at"],
                last_used_at=doc.get("last_used_at"),
                revoked_at=doc.get("revoked_at"),
                expires_at=doc.get("expires_at"),
            )
            for doc in docs
        ]

    async def revoke(
        self, db: AsyncIOMotorDatabase, user: User, key_id: str
    ) -> None:
        revoked = await self._keys.revoke(db, key_id, user.id or "")
        if not revoked:
            raise NotFoundError("API key not found")

    async def authenticate(
        self, db: AsyncIOMotorDatabase, raw: str | None
    ) -> ApiKey:
        """Resolve a raw key to its record, or raise a 401.

        Every failure returns the same message so a caller cannot tell an
        unknown prefix from a wrong secret.
        """
        invalid = AuthenticationError("Invalid or missing API key")
        if not raw or not raw.startswith(KEY_PREFIX):
            raise invalid
        doc = await self._keys.find_by_prefix(db, raw[:PREFIX_LENGTH])
        if doc is None:
            raise invalid
        # Constant-time compare so a timing side channel cannot recover the hash.
        if not secrets.compare_digest(doc.get("key_hash", ""), _hash(raw)):
            raise invalid

        api_key = ApiKey(**doc)
        if api_key.is_revoked:
            raise AuthenticationError("This API key has been revoked")
        if api_key.expires_at is not None and _naive_utc(api_key.expires_at) < datetime.now(
            UTC
        ).replace(tzinfo=None):
            raise AuthenticationError("This API key has expired")

        await self._maybe_touch(db, api_key)
        return api_key

    async def _maybe_touch(self, db: AsyncIOMotorDatabase, api_key: ApiKey) -> None:
        now = datetime.now(UTC)
        last = api_key.last_used_at
        if last is not None and (_naive_utc(now) - _naive_utc(last)).total_seconds() < (
            TOUCH_INTERVAL_SECONDS
        ):
            return
        try:
            await self._keys.touch(db, api_key.id or "")
        except Exception as exc:  # usage tracking must never block a request
            logger.warning("Could not update API key last_used_at: %s", exc)

    @staticmethod
    def _to_out(api_key: ApiKey) -> ApiKeyOut:
        return ApiKeyOut(
            id=api_key.id or "",
            name=api_key.name,
            prefix=api_key.prefix,
            role=api_key.role,
            created_at=api_key.created_at,
            last_used_at=api_key.last_used_at,
            revoked_at=api_key.revoked_at,
            expires_at=api_key.expires_at,
        )
