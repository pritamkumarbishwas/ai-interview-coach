"""Staff provisioning: invitations, role changes, and the bootstrap admin."""

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.core.exceptions import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
    QuotaExceededError,
)
from app.core.mailer import EmailMessage, get_mailer
from app.core.security import create_access_token, hash_password
from app.emails.templates import staff_invitation_email
from app.models.staff_invitation import StaffInvitation
from app.models.user import STAFF_ROLES, User
from app.repositories.staff_invitation_repository import StaffInvitationRepository
from app.repositories.user_repository import UserRepository, user_repository
from app.schemas.auth import TokenResponse
from app.schemas.staff import (
    InvitationAccept,
    InvitationCreate,
    InvitationOut,
    RoleUpdateRequest,
)
from app.schemas.user import UserOut
from app.services.audit_service import audit_service

logger = logging.getLogger(__name__)

INVITATION_TTL = timedelta(days=7)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _accept_url(token: str) -> str:
    base = settings.frontend_url.rstrip("/")
    return f"{base}/staff/accept?token={token}"


def _now() -> datetime:
    return datetime.now(UTC)


class StaffService:
    def __init__(self, users: UserRepository, invitations: StaffInvitationRepository) -> None:
        self._users = users
        self._invitations = invitations

    async def invite(
        self, db: AsyncIOMotorDatabase, admin: User, payload: InvitationCreate
    ) -> InvitationOut:
        if payload.role not in STAFF_ROLES:
            raise InvalidInputError("Role must be one of: admin, recruiter, reviewer")
        email = payload.email.strip().lower()
        if await self._users.get_by_email(db, email) is not None:
            raise ConflictError("A user with this email already exists")

        # Seat cap: refuse to provision beyond the configured number of accounts.
        if settings.max_staff_seats:
            seats_used = await self._users.count_staff(db)
            pending = await self._invitations.count_pending(db)
            if seats_used + pending >= settings.max_staff_seats:
                raise QuotaExceededError(
                    f"All {settings.max_staff_seats} staff seats are in use"
                )

        # A fresh invite supersedes any earlier pending one for the same email.
        await self._invitations.revoke_pending_for_email(db, email)
        token = secrets.token_urlsafe(32)
        invitation = StaffInvitation(
            email=email,
            role=payload.role,
            token_hash=_hash_token(token),
            invited_by=admin.id or "",
            expires_at=_now() + INVITATION_TTL,
        )
        invitation.id = await self._invitations.insert(db, invitation)

        accept_url = _accept_url(token)
        await self._send_invitation_email(payload.name, invitation, accept_url)
        await audit_service.record(
            db,
            action="staff.invite",
            actor_id=admin.id,
            target_type="staff_invitation",
            target_id=invitation.id,
            metadata={"email": email, "role": payload.role},
        )
        return self._to_out(invitation, accept_url=accept_url)

    async def list_invitations(
        self, db: AsyncIOMotorDatabase, limit: int
    ) -> list[InvitationOut]:
        docs = await self._invitations.list_recent(db, limit)
        return [
            InvitationOut(
                id=doc["_id"],
                email=doc["email"],
                role=doc["role"],
                status=doc["status"],
                expires_at=doc["expires_at"],
                created_at=doc["created_at"],
            )
            for doc in docs
        ]

    async def revoke(self, db: AsyncIOMotorDatabase, admin: User, invitation_id: str) -> None:
        doc = await self._invitations.revoke(db, invitation_id)
        if doc is None:
            raise NotFoundError("Pending invitation not found")
        await audit_service.record(
            db,
            action="staff.invitation_revoked",
            actor_id=admin.id,
            target_type="staff_invitation",
            target_id=invitation_id,
        )

    async def accept(self, db: AsyncIOMotorDatabase, payload: InvitationAccept) -> TokenResponse:
        doc = await self._invitations.find_by_token_hash(db, _hash_token(payload.token))
        if doc is None:
            raise NotFoundError("Invitation not found")

        invitation = StaffInvitation(**doc)
        if invitation.status != "pending":
            raise ConflictError("This invitation is no longer valid")
        if invitation.expires_at.replace(tzinfo=UTC) < _now():
            raise ConflictError("This invitation has expired")
        if await self._users.get_by_email(db, invitation.email) is not None:
            raise ConflictError("A user with this email already exists")

        user = await self._users.create(
            db,
            name=payload.name,
            email=invitation.email,
            password_hash=hash_password(payload.password),
            role=invitation.role,
        )
        await self._invitations.mark_accepted(db, invitation.id or "")
        await audit_service.record(
            db,
            action="staff.invitation_accepted",
            actor_id=user.id,
            target_type="user",
            target_id=user.id,
            metadata={"role": user.role},
        )
        return self._build_token_response(user)

    async def list_staff(self, db: AsyncIOMotorDatabase, limit: int) -> list[UserOut]:
        users = await self._users.list_staff(db, limit)
        return [UserOut.model_validate(user) for user in users]

    async def update_role(
        self, db: AsyncIOMotorDatabase, admin: User, user_id: str, payload: RoleUpdateRequest
    ) -> UserOut:
        if payload.role not in STAFF_ROLES:
            raise InvalidInputError("Role must be one of: admin, recruiter, reviewer")
        updated = await self._users.update_role(db, user_id, payload.role)
        if updated is None:
            raise NotFoundError("User not found")
        await audit_service.record(
            db,
            action="staff.role_changed",
            actor_id=admin.id,
            target_type="user",
            target_id=user_id,
            metadata={"role": payload.role},
        )
        return UserOut.model_validate(updated)

    async def _send_invitation_email(
        self, name: str, invitation: StaffInvitation, accept_url: str
    ) -> None:
        content = staff_invitation_email(
            invitee_name=name,
            role=invitation.role,
            company=settings.app_name,
            accept_url=accept_url,
            expires_at=invitation.expires_at,
        )
        try:
            await get_mailer().send(
                EmailMessage(
                    to=invitation.email,
                    subject=content.subject,
                    text=content.text,
                    html=content.html,
                )
            )
        except Exception as exc:
            # Email is a side channel; the inviting admin still gets the URL.
            logger.warning("Could not send staff invitation email: %s", exc)

    def _build_token_response(self, user: User) -> TokenResponse:
        token = create_access_token(subject=user.id)
        return TokenResponse(
            access_token=token,
            token_type="bearer",
            expires_in=settings.jwt_expires_minutes * 60,
            user=UserOut.model_validate(user),
        )

    @staticmethod
    def _to_out(invitation: StaffInvitation, accept_url: str | None = None) -> InvitationOut:
        return InvitationOut(
            id=invitation.id or "",
            email=invitation.email,
            role=invitation.role,
            status=invitation.status,
            expires_at=invitation.expires_at,
            created_at=invitation.created_at,
            accept_url=accept_url,
        )


async def ensure_bootstrap_admin(db: AsyncIOMotorDatabase) -> None:
    """Create (or promote) the seed admin from settings, if configured."""
    email = (settings.bootstrap_admin_email or "").strip().lower()
    password = settings.bootstrap_admin_password or ""
    if not email or not password:
        return

    existing = await user_repository.get_by_email(db, email)
    if existing is not None:
        if existing.role != "admin":
            await user_repository.update_role(db, existing.id or "", "admin")
            logger.info("Promoted existing user %s to admin", email)
        return

    await user_repository.create(
        db,
        name=settings.bootstrap_admin_name,
        email=email,
        password_hash=hash_password(password),
        role="admin",
    )
    logger.info("Created bootstrap admin %s", email)
