"""
Обёртка над ChromaDB для хранения и поиска эмбеддингов.

Коллекции изолированы по клиенту: `client_{client_id}`.
Все тяжёлые операции выполняются в asyncio.to_thread.
"""

import asyncio
from pathlib import Path
from typing import Any, Optional

import chromadb
from loguru import logger


class VectorStore:
    """Клиентская коллекция в ChromaDB.

    Args:
        client_id: Идентификатор клиента (определяет имя коллекции).
        persist_directory: Путь к директории хранилища ChromaDB.
    """

    def __init__(self, client_id: str, persist_directory: Path) -> None:
        self._client_id = client_id
        self._collection_name = f"client_{client_id}"
        self._persist_dir = str(persist_directory)
        self._chroma: Optional[chromadb.PersistentClient] = None
        self._collection: Optional[Any] = None

    def _get_collection(self) -> Any:
        """Лениво инициализировать ChromaDB и получить коллекцию."""
        if self._chroma is None:
            self._chroma = chromadb.PersistentClient(path=self._persist_dir)
            logger.info("ChromaDB инициализирован: {}", self._persist_dir)

        if self._collection is None:
            self._collection = self._chroma.get_or_create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(
                "Коллекция ChromaDB: {} (документов: {})",
                self._collection_name,
                self._collection.count(),
            )

        return self._collection

    def _add_sync(
        self,
        doc_id: str,
        embedding: list[float],
        document: str,
        metadata: dict,
    ) -> None:
        """Синхронное добавление документа."""
        collection = self._get_collection()
        collection.add(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[document],
            metadatas=[metadata],
        )

    def _query_sync(
        self,
        embedding: list[float],
        n_results: int,
        where: Optional[dict] = None,
    ) -> list[dict]:
        """Синхронный поиск ближайших соседей."""
        collection = self._get_collection()
        total = collection.count()
        if total == 0:
            return []

        kwargs: dict[str, Any] = {
            "query_embeddings": [embedding],
            "n_results": min(n_results, total),
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        results = collection.query(**kwargs)

        if not results["ids"] or not results["ids"][0]:
            return []

        output = []
        for i, doc_id in enumerate(results["ids"][0]):
            output.append(
                {
                    "id": doc_id,
                    "document": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i],
                }
            )
        return output

    async def add(
        self,
        doc_id: str,
        embedding: list[float],
        document: str,
        metadata: Optional[dict] = None,
    ) -> None:
        """Добавить документ с эмбеддингом в коллекцию.

        Args:
            doc_id: Уникальный идентификатор документа (например, SHA-256 хеш).
            embedding: Вектор эмбеддинга.
            document: Исходный текст (хранится в ChromaDB для отладки).
            metadata: Произвольные метаданные (client_id, news_id и т.д.).
        """
        meta = metadata or {}
        meta.setdefault("client_id", self._client_id)
        await asyncio.to_thread(self._add_sync, doc_id, embedding, document, meta)
        logger.debug("VectorStore.add: id={}, client={}", doc_id[:8], self._client_id)

    async def query(
        self,
        embedding: list[float],
        n_results: int = 5,
        where: Optional[dict] = None,
    ) -> list[dict]:
        """Найти n_results ближайших документов по косинусному сходству.

        Args:
            embedding: Вектор запроса.
            n_results: Количество результатов.
            where: Фильтр по метаданным (ChromaDB where-синтаксис).

        Returns:
            Список словарей с ключами: id, document, metadata, distance.
            distance в пространстве cosine: 0 = идентичный, 1 = ортогональный.
        """
        return await asyncio.to_thread(self._query_sync, embedding, n_results, where)

    async def count(self) -> int:
        """Вернуть количество документов в коллекции."""
        def _count() -> int:
            return self._get_collection().count()

        return await asyncio.to_thread(_count)
