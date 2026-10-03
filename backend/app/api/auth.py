from fastapi import APIRouter, Depends, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import get_auth_service, get_current_user
from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.user import UserOut, UserUpdate
from app.services.auth_service import AuthService

router = APIRouter()


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register(
    payload: RegisterRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
    _: None = Depends(rate_limit("register")),
) -> User:
    return await service.register(db, payload)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and receive a JWT",
)
async def login(
    payload: LoginRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
    _: None = Depends(rate_limit("login")),
) -> TokenResponse:
    return await service.login(db, payload)


@router.get(
    "/me",
    response_model=UserOut,
    summary="Get the currently authenticated user",
)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.patch(
    "/me",
    response_model=UserOut,
    summary="Update the currently authenticated user's profile",
)
async def update_me(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
) -> User:
    return await service.update_profile(db, current_user, payload)
