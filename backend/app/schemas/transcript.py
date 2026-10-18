from pydantic import BaseModel


class TranscriptionOut(BaseModel):
    """Server-side speech-to-text result for one recorded answer."""

    text: str = ""
