"""Qdrant-backed retrieval over the ingested knowledge base (RAG).

Five fixed collections partition the knowledge base; the interview type picks
which ones are searched, and chunks carry `topic`/`roles` payload fields so
`retrieve_context()` can filter by role and topic. Everything degrades to an
empty result when `RAG_ENABLED=false` or the store is unreachable — question
generation must never fail because of RAG.
"""

import asyncio
import logging
from pathlib import Path

from qdrant_client import QdrantClient, models

from app.core.config import BACKEND_ROOT, settings
from app.schemas.rag import KnowledgeChunk, RetrievedChunk
from app.services.embedding_service import embedding_service

logger = logging.getLogger(__name__)

COLLECTIONS = (
    "technical_concepts",
    "interview_questions",
    "behavioral_questions",
    "system_design",
    "role_knowledge",
)

# Which collections are worth searching for each interview type.
TYPE_COLLECTIONS: dict[str, tuple[str, ...]] = {
    "technical": ("technical_concepts", "interview_questions", "role_knowledge"),
    "behavioral": ("behavioral_questions", "role_knowledge"),
    "hr": ("behavioral_questions", "role_knowledge"),
    "system_design": ("system_design", "technical_concepts", "role_knowledge"),
    "mixed": COLLECTIONS,
}
DEFAULT_TYPE_COLLECTIONS = COLLECTIONS

# Below this many topic-filtered hits, retry without the topic filter:
# question-gen topic labels ("RLS Implementation Details") rarely match the
# knowledge base's broader topics ("row-level security", "*").
MIN_CONTEXT_CHUNKS = 3


class RagService:
    """Qdrant access for ingestion and retrieval (lazy client, cached setup)."""

    def __init__(self) -> None:
        self._client: QdrantClient | None = None
        self._ensured = False

    @property
    def enabled(self) -> bool:
        # Read per call so tests can flip RAG_ENABLED at runtime.
        return settings.rag_enabled

    @property
    def client(self) -> QdrantClient:
        if self._client is None:
            url = settings.qdrant_url.strip()
            if url.startswith(("http://", "https://")):
                self._client = QdrantClient(url=url, api_key=settings.qdrant_api_key or None)
            elif url == ":memory:":
                self._client = QdrantClient(location=":memory:")
            else:
                # Embedded persistent store (no Docker): a directory, resolved
                # against the backend package root when relative. qdrant-client
                # only accepts directories via `path` (its `location` parameter
                # is treated as a URL otherwise).
                path = Path(url).expanduser()
                if not path.is_absolute():
                    path = BACKEND_ROOT / path
                path.mkdir(parents=True, exist_ok=True)
                self._client = QdrantClient(path=str(path))
        return self._client

    async def ensure_collections(self) -> None:
        """Create any missing collections (idempotent, cached per process)."""
        if self._ensured:
            return
        size = await embedding_service.dimension()

        def create_missing() -> None:
            existing = {c.name for c in self.client.get_collections().collections}
            for name in COLLECTIONS:
                if name in existing:
                    continue
                try:
                    self.client.create_collection(
                        collection_name=name,
                        vectors_config=models.VectorParams(
                            size=size, distance=models.Distance.COSINE
                        ),
                    )
                except Exception:  # lost a create race — it exists now
                    logger.debug("collection %s already created", name)

        await asyncio.to_thread(create_missing)
        self._ensured = True

    def delete_collections(self) -> None:
        """Drop all collections (used by `ingest --reset` and tests)."""
        for name in COLLECTIONS:
            try:
                self.client.delete_collection(name)
            except Exception:  # missing collection is fine
                logger.debug("collection %s not present", name)
        self._ensured = False

    async def upsert(self, collection: str, chunks: list[KnowledgeChunk]) -> int:
        """Embed and store chunks in one collection; returns the count."""
        if collection not in COLLECTIONS:
            raise ValueError(f"Unknown collection {collection!r}; valid: {', '.join(COLLECTIONS)}")
        if not chunks:
            return 0
        await self.ensure_collections()
        vectors = await embedding_service.embed([chunk.text for chunk in chunks])
        points = [
            models.PointStruct(
                id=chunk.id,
                vector=vector,
                payload={
                    "text": chunk.text,
                    "topic": chunk.topic,
                    "roles": chunk.roles,
                    "source": chunk.source,
                },
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        await asyncio.to_thread(self.client.upsert, collection, points, wait=True)
        return len(points)

    async def retrieve_context(
        self,
        role: str,
        topic: str,
        interview_type: str,
        k: int | None = None,
    ) -> list[RetrievedChunk]:
        """Top 3-5 chunks for a question, filtered by role and topic.

        Returns an empty list when RAG is disabled; Qdrant/embedding errors
        propagate so callers can log and continue without context.
        """
        if not self.enabled:
            return []
        limit = k if k is not None else settings.rag_top_k
        await self.ensure_collections()

        type_words = interview_type.replace("_", " ")
        query_text = f"{topic} {type_words}".strip() if topic else type_words
        query_vector = (await embedding_service.embed([query_text]))[0]
        collections = TYPE_COLLECTIONS.get(interview_type, DEFAULT_TYPE_COLLECTIONS)

        topic_hits = await asyncio.to_thread(self._search, collections, query_vector, topic, limit)
        if topic and len(topic_hits) < MIN_CONTEXT_CHUNKS:
            # Retry without the topic filter, keeping any topic matches first.
            general_hits = await asyncio.to_thread(
                self._search, collections, query_vector, "", limit
            )
            topic_hits = _dedupe(topic_hits + general_hits)

        role_hits = [hit for hit in topic_hits if _role_matches(hit, role)]
        # A role filter that starves the result is worse than no filter:
        # the knowledge base may simply not tag this role.
        return (role_hits or topic_hits)[:limit]

    def _search(
        self,
        collections: tuple[str, ...],
        query_vector: list[float],
        topic: str,
        limit: int,
    ) -> list[RetrievedChunk]:
        query_filter = None
        if topic:
            query_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="topic",
                        match=models.MatchAny(any=[topic, "*"]),
                    )
                ]
            )
        hits: list[RetrievedChunk] = []
        for name in collections:
            result = self.client.query_points(
                collection_name=name,
                query=query_vector,
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
            )
            for point in result.points:
                payload = point.payload or {}
                hits.append(
                    RetrievedChunk(
                        id=str(point.id),
                        text=payload.get("text", ""),
                        collection=name,
                        topic=payload.get("topic", "*"),
                        roles=payload.get("roles") or ["*"],
                        source=payload.get("source", ""),
                        score=float(point.score),
                    )
                )
        hits.sort(key=lambda hit: -hit.score)
        return hits[: max(limit * 2, limit)]


def _role_matches(chunk: RetrievedChunk, role: str) -> bool:
    """True when the chunk is role-agnostic or fits the interview's role."""
    if not role:
        return True
    role_lower = role.lower()
    for chunk_role in chunk.roles or ["*"]:
        key = chunk_role.strip().lower()
        if key in ("", "*") or key in role_lower:
            return True
    return False


def _dedupe(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    seen: set[str] = set()
    unique: list[RetrievedChunk] = []
    for chunk in chunks:
        if chunk.id not in seen:
            seen.add(chunk.id)
            unique.append(chunk)
    return unique


rag_service = RagService()
