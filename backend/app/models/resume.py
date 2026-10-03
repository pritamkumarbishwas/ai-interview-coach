from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Resume(BaseModel):
    id: str | None = Field(default=None, alias="_id")
    user_id: str
    filename: str
    file_size: int = 0
    storage_key: str = ""
    raw_text: str
    structured_data: dict[str, Any]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(populate_by_name=True)
