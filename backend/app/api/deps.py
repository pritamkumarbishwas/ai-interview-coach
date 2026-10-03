from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import get_db
from app.core.exceptions import AuthenticationError
from app.core.security import decode_access_token
from app.models.user import User
from app.repositories.user_repository import UserRepository, user_repository
from app.services.auth_service import AuthService

bearer_scheme = HTTPBearer(auto_error=False)


def get_user_repository() -> UserRepository:
    return user_repository


def get_auth_service(
    users: UserRepository = Depends(get_user_repository),
) -> AuthService:
    return AuthService(users)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncIOMotorDatabase = Depends(get_db),
    users: UserRepository = Depends(get_user_repository),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError("Not authenticated")

    payload = decode_access_token(credentials.credentials)
    user = await users.get_by_id(db, payload.sub)
    if user is None:
        raise AuthenticationError("User no longer exists")
    return user
