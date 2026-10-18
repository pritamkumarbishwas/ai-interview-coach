from fastapi import APIRouter, Depends, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import get_staff_service, require_admin
from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.models.user import User
from app.schemas.auth import TokenResponse
from app.schemas.staff import (
    InvitationAccept,
    InvitationCreate,
    InvitationOut,
    RoleUpdateRequest,
)
from app.schemas.user import UserOut
from app.services.staff_service import StaffService

router = APIRouter()


@router.post("/invitations", response_model=InvitationOut, status_code=status.HTTP_201_CREATED)
async def create_invitation(
    payload: InvitationCreate,
    admin: User = Depends(require_admin),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: StaffService = Depends(get_staff_service),
    _: None = Depends(rate_limit("staff_invite")),
) -> InvitationOut:
    return await service.invite(db, admin, payload)


@router.get("/invitations", response_model=list[InvitationOut])
async def list_invitations(
    admin: User = Depends(require_admin),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: StaffService = Depends(get_staff_service),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[InvitationOut]:
    return await service.list_invitations(db, limit)


@router.delete("/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invitation(
    invitation_id: str,
    admin: User = Depends(require_admin),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: StaffService = Depends(get_staff_service),
) -> None:
    await service.revoke(db, admin, invitation_id)


@router.post("/invitations/accept", response_model=TokenResponse)
async def accept_invitation(
    payload: InvitationAccept,
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: StaffService = Depends(get_staff_service),
    _: None = Depends(rate_limit("staff_accept")),
) -> TokenResponse:
    """Public: an invited staff member sets their name/password and logs in."""
    return await service.accept(db, payload)


@router.get("/users", response_model=list[UserOut])
async def list_staff(
    admin: User = Depends(require_admin),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: StaffService = Depends(get_staff_service),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[UserOut]:
    return await service.list_staff(db, limit)


@router.patch("/users/{user_id}/role", response_model=UserOut)
async def update_staff_role(
    user_id: str,
    payload: RoleUpdateRequest,
    admin: User = Depends(require_admin),
    db: AsyncIOMotorDatabase = Depends(get_db),
    service: StaffService = Depends(get_staff_service),
) -> UserOut:
    return await service.update_role(db, admin, user_id, payload)
