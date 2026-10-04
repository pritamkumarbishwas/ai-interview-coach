"""Local embedding model (fastembed / ONNX) — no API key required.

The same model must embed both ingested chunks and retrieval queries, so a
single lazy instance is shared by `rag_service` and the ingestion script.
The first use downloads the model into `EMBEDDING_CACHE_DIR`.
"""

import asyncio
import logging

from app.core.config import resolve_embedding_cache_dir, settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Lazy-loaded text embedder; `embed_texts` is the sync patch point for tests."""

    def __init__(self) -> None:
        self._model = None
        self._dim: int | None = None

    @property
    def model(self):
        if self._model is None:
            from fastembed import TextEmbedding  # heavy import — keep it lazy

            cache_dir = resolve_embedding_cache_dir()
            cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info("Loading embedding model %s", settings.embedding_model)
            self._model = TextEmbedding(
                model_name=settings.embedding_model,
                cache_dir=str(cache_dir),
            )
        return self._model

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Synchronous embedding (the patch point tests replace)."""
        if not texts:
            return []
        return [list(map(float, vector)) for vector in self.model.embed(texts)]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Async wrapper so ONNX inference never blocks the event loop."""
        return await asyncio.to_thread(self.embed_texts, texts)

    async def embed_one(self, text: str) -> list[float]:
        vectors = await self.embed([text])
        return vectors[0]

    async def dimension(self) -> int:
        """Vector size — probed from a real embedding (works with patched models)."""
        if self._dim is None:
            vectors = await self.embed(["dimension probe"])
            self._dim = len(vectors[0])
        return self._dim


embedding_service = EmbeddingService()
