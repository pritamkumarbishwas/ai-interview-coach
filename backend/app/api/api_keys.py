"""API-key management (staff-facing).

A staff user manages only their own keys; a key inherits that user's access and
can never do more than the user could. The raw secret is returned once, on
creation, and never again.
"""

from fastapi import APIRouter, Depends, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import get_api_key_service, require_recruiter
from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.models.user import User
from app.schemas.api_key import ApiKeyCreate, ApiKeyCreated, ApiKeyOut
from app.services.api_key_service import ApiKeyService

router = APIRouter()


@router.post("", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: ApiKeyCreate,
    current_user: User = Depends(require_recruiter),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ApiKeyService = Depends(get_api_key_service),
    _: None = Depends(rate_limit("api_key_create")),
) -> ApiKeyCreated:
    """Mint a new key. The `key` field is shown exactly once."""
    return await service.create(db, current_user, payload)


@router.get("", response_model=list[ApiKeyOut])
async def list_api_keys(
    current_user: User = Depends(require_recruiter),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ApiKeyService = Depends(get_api_key_service),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ApiKeyOut]:
    return await service.list(db, current_user, limit)


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: str,
    current_user: User = Depends(require_recruiter),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: ApiKeyService = Depends(get_api_key_service),
) -> None:
    await service.revoke(db, current_user, key_id)
