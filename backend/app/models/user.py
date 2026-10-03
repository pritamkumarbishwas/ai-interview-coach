from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class User(BaseModel):
    id: str | None = Field(default=None, alias="_id")
    name: str
    email: str
    password_hash: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(populate_by_name=True)

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email}>"
