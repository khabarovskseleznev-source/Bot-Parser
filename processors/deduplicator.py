"""
Дедупликация новостей.

Двухуровневый подход:
1. Hash-check — быстрая проверка SHA-256 через SQL (точное совпадение).
2. Semantic similarity — косинусное сходство через ChromaDB (порог настраивается).

Порядок: hash → semantic. В ChromaDB записывается только после прохождения обоих.
"""

from dataclasses import dataclass, field
from typing import Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from database.crud import compute_hash, get_news_by_hash
from processors.embeddings import get_embedding
from processors.vector_store import VectorStore

# Порог косинусного сходства (0–1). Выше — дубликат.
DEFAULT_SIMILARITY_THRESHOLD = 0.92


@dataclass
class DeduplicationResult:
    """Результат проверки на дубликат."""

    is_duplicate: bool
    reason: str  # 'hash', 'semantic', 'unique'
    similarity: float = 0.0  # для semantic
    embedding: Optional[list[float]] = field(default=None, repr=False)  # переиспользуется в pipeline


class Deduplicator:
    """Двухуровневый дедупликатор новостей.

    Args:
        vector_store: Экземпляр VectorStore для конкретного клиента.
        similarity_threshold: Порог косинусного сходства (0.0–1.0).
    """

    def __init__(
        self,
        vector_store: VectorStore,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    ) -> None:
        self._vector_store = vector_store
        self._threshold = similarity_threshold

    async def check(
        self,
        session: AsyncSession,
        client_id: int,
        title: str,
        content: str,
    ) -> DeduplicationResult:
        """Проверить, является ли текст дубликатом.

        Args:
            session: Сессия SQLAlchemy.
            client_id: ID клиента.
            title: Заголовок новости.
            content: Текст новости.

        Returns:
            DeduplicationResult с флагом и причиной.
        """
        text = title + " " + content
        content_hash = compute_hash(title + content)

        # Уровень 1: hash-check
        existing = await get_news_by_hash(session, client_id, content_hash)
        if existing is not None:
            logger.debug("Дубликат по хешу: client={}, hash={}", client_id, content_hash[:8])
            return DeduplicationResult(is_duplicate=True, reason="hash")

        # Уровень 2: semantic similarity
        embedding = await get_embedding(text)
        results = await self._vector_store.query(embedding, n_results=1)

        if results and results[0]["distance"] <= (1.0 - self._threshold):
            similarity = 1.0 - results[0]["distance"]
            logger.debug(
                "Дубликат по семантике: client={}, similarity={:.3f}", client_id, similarity
            )
            return DeduplicationResult(
                is_duplicate=True,
                reason="semantic",
                similarity=similarity,
                embedding=embedding,
            )

        return DeduplicationResult(is_duplicate=False, reason="unique", embedding=embedding)
