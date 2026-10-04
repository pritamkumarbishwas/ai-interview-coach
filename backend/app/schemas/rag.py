from pydantic import BaseModel, Field


class KnowledgeChunk(BaseModel):
    """One embeddable unit loaded from the knowledge base."""

    # Stable UUID derived from source path + position, so re-ingestion
    # upserts (overwrites) instead of duplicating points.
    id: str
    text: str = Field(min_length=1)
    # Broad topic used by the metadata filter; "*" matches every topic.
    topic: str = "*"
    # Roles this chunk is relevant for; ["*"] means role-agnostic.
    roles: list[str] = Field(default_factory=lambda: ["*"])
    # Where the chunk came from, relative to the knowledge base directory.
    source: str = ""


class RetrievedChunk(BaseModel):
    """A chunk returned from Qdrant, with its retrieval score."""

    id: str
    text: str
    collection: str
    topic: str = "*"
    roles: list[str] = Field(default_factory=list)
    source: str = ""
    score: float = 0.0
