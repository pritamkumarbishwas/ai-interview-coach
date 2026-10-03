import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.core.exceptions import AuthenticationError, ConflictError
from app.core.security import (
    create_access_token,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.user import UserOut, UserUpdate

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def register(self, db: AsyncIOMotorDatabase, payload: RegisterRequest) -> User:
        existing = await self._users.get_by_email(db, payload.email)
        if existing is not None:
            raise ConflictError("An account with this email already exists")

        user = await self._users.create(
            db,
            name=payload.name,
            email=payload.email,
            password_hash=hash_password(payload.password),
        )
        logger.info("Registered user id=%s email=%s", user.id, user.email)
        return user

    async def login(self, db: AsyncIOMotorDatabase, payload: LoginRequest) -> TokenResponse:
        user = await self._users.get_by_email(db, payload.email)
        if user is None or not verify_password(payload.password, user.password_hash):
            logger.warning("Failed login attempt for email=%s", payload.email)
            raise AuthenticationError("Invalid email or password")

        if needs_rehash(user.password_hash):
            new_hash = hash_password(payload.password)
            user.password_hash = new_hash
            await self._users.update_password(db, user.id, new_hash)

        logger.info("User logged in id=%s", user.id)
        return self._build_token_response(user)

    async def update_profile(
        self, db: AsyncIOMotorDatabase, user: User, payload: UserUpdate
    ) -> User:
        updated = await self._users.update_profile(db, user.id or "", name=payload.name)
        if updated is None:  # user was removed between authentication and this update
            raise AuthenticationError("User no longer exists")
        logger.info("Updated profile id=%s", updated.id)
        return updated

    def _build_token_response(self, user: User) -> TokenResponse:
        token = create_access_token(subject=user.id)
        return TokenResponse(
            access_token=token,
            token_type="bearer",
            expires_in=settings.jwt_expires_minutes * 60,
            user=UserOut.model_validate(user),
        )
