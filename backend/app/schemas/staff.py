from pydantic import BaseModel, EmailStr, Field

from app.core.timeutil import ISTDateTime
from app.models.staff_invitation import StaffInvitationStatus
from app.models.user import Role


class InvitationCreate(BaseModel):
    email: EmailStr
    role: Role
    # Optional display name, used to personalise the invitation email.
    name: str = Field(default="", max_length=120)


class InvitationAccept(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)


class InvitationOut(BaseModel):
    id: str
    email: EmailStr
    role: Role
    status: StaffInvitationStatus
    expires_at: ISTDateTime
    created_at: ISTDateTime
    # Returned to the inviting admin so the link can be copied if email is not
    # configured; never derivable from the stored record.
    accept_url: str | None = None


class RoleUpdateRequest(BaseModel):
    role: Role
