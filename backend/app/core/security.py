from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import (
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)
from pydantic import BaseModel

from app.core.config import settings
from app.core.exceptions import AuthenticationError

_password_hasher = PasswordHasher()

ALGORITHM = settings.jwt_algorithm
TOKEN_TYPE = "access"


class TokenPayload(BaseModel):
    sub: str
    exp: int
    type: str = TOKEN_TYPE


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _password_hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def create_access_token(
    subject: str,
    expires_delta: timedelta | None = None,
) -> str:
    now = datetime.now(UTC)
    expires_at = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.jwt_expires_minutes)
    )
    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": now,
        "exp": expires_at,
        "type": TOKEN_TYPE,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> TokenPayload:
    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Token has expired") from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid or expired token") from exc

    if data.get("type") != TOKEN_TYPE:
        raise AuthenticationError("Invalid token type")

    try:
        payload = TokenPayload(sub=str(data["sub"]), exp=int(data["exp"]), type=data["type"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AuthenticationError("Invalid token payload") from exc

    return payload
