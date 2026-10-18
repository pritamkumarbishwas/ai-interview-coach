from datetime import datetime

from pydantic import BaseModel


class ErasureResult(BaseModel):
    """Outcome of destroying one candidate's session data."""

    invitation_id: str
    interview_deleted: bool
    recording_chunks_deleted: int
    erased_at: datetime


class PurgeResult(BaseModel):
    """Outcome of a retention purge run."""

    erased: int
