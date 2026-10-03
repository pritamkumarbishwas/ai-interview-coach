from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    email: EmailStr
    created_at: datetime


class _NameValidationMixin(BaseModel):
    """`min_length=1` alone accepts "   " — require a real name."""

    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Name must not be blank")
        return stripped


class UserCreate(_NameValidationMixin):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserUpdate(_NameValidationMixin):
    """Profile fields a user may edit after registration."""
