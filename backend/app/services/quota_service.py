"""Per-role limits (Phase 9).

Daily quotas that cap how much of a given action a role may perform. Limits are
configured as ``ROLE_LIMITS="role:action=max"`` pairs; ``*`` matches any role or
action and the most specific match wins. A missing or 0 limit is unlimited, so
an unconfigured deployment behaves exactly as before.

Counting is per actor, not per role: the *limit* is a property of the role, the
*usage* is the individual's. Enforcement consumes the counter atomically and
rolls the increment back when the cap is hit, so an over-quota attempt does not
displace a legitimate one.
"""

from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.core.exceptions import QuotaExceededError
from app.models.user import User
from app.repositories.quota_repository import QuotaRepository, quota_repository
from app.schemas.quota import QuotaStatus, QuotaSummary

# Actions that carry a quota; also the ones surfaced in the self-view.
QUOTA_ACTIONS = ("invitations", "exports", "api_keys")


def _window_start() -> datetime:
    """Start of the current UTC day (naive, matching stored datetimes)."""
    now = datetime.now(UTC)
    return now.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)


class QuotaService:
    def __init__(self, repository: QuotaRepository) -> None:
        self._repo = repository

    @staticmethod
    def limit_for(role: str, action: str) -> int | None:
        """Resolve the daily limit for a role+action (most specific wins)."""
        limits = settings.role_limits
        for key in (f"{role}:{action}", f"*:{action}", f"{role}:*", "*:*"):
            if key in limits:
                value = limits[key]
                return value if value > 0 else None
        return None

    async def enforce(
        self, db: AsyncIOMotorDatabase, user: User, action: str
    ) -> None:
        """Consume one unit of `action` for `user`, or raise 429 if over quota."""
        limit = self.limit_for(user.role, action)
        if limit is None:
            return
        window = _window_start()
        actor_id = user.id or ""
        count = await self._repo.increment(
            db, actor_id=actor_id, action=action, window_start=window
        )
        if count > limit:
            await self._repo.decrement(
                db, actor_id=actor_id, action=action, window_start=window
            )
            raise QuotaExceededError(
                f"Daily limit of {limit} {action.replace('_', ' ')} reached "
                f"for the {user.role} role"
            )

    async def usage(self, db: AsyncIOMotorDatabase, user: User) -> QuotaSummary:
        """Current usage against each quota for the calling user."""
        window = _window_start()
        counts = await self._repo.counts(
            db, actor_id=user.id or "", window_start=window
        )
        quotas = []
        for action in QUOTA_ACTIONS:
            limit = self.limit_for(user.role, action)
            used = counts.get(action, 0)
            quotas.append(
                QuotaStatus(
                    action=action,
                    limit=limit,
                    used=used,
                    remaining=None if limit is None else max(limit - used, 0),
                )
            )
        return QuotaSummary(role=user.role, window_start=window, quotas=quotas)


quota_service = QuotaService(quota_repository)
